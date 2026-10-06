"""The model layer: provider selection, model resolution, and the preflight check.

The provider is configuration, so the thing worth testing is that a change to the
environment lands where it should — official OpenAI, an Azure resource, or a gateway —
without any of it reaching the network. Clients are inspected, never called; every call
in these tests goes to a fake.

Offline mode gets the same attention. It is what lets the whole pipeline run without a
key, so "no key configured" must stay a supported state rather than an error path.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

from src.agent import models as m

REQUEST = httpx.Request("POST", "https://gw.example.com/v1/chat/completions")


def connection_error() -> Exception:
    return openai.APIConnectionError(message="Connection error.", request=REQUEST)


def auth_error() -> Exception:
    return openai.AuthenticationError(
        "Incorrect API key provided: sk-secret-value",
        response=httpx.Response(401, request=REQUEST),
        body=None,
    )


def missing_model_error() -> Exception:
    return openai.NotFoundError(
        "The model `house-narrative` does not exist",
        response=httpx.Response(404, request=REQUEST),
        body=None,
    )


@pytest.fixture
def configure(monkeypatch):
    """Set values on the shared Settings singleton for one test.

    ``settings`` is a module-level object every module imported by name, so patching its
    attributes reaches all of them at once; monkeypatch puts them back afterwards.
    """

    def _configure(**values):
        for key, value in values.items():
            monkeypatch.setattr(m.settings, key, value)

    return _configure


@pytest.fixture
def offline(configure):
    configure(openai_api_key="", embedding_api_key="", llm_provider="openai")
    return m.ModelRouter()


class FakeClient:
    """Stands in for the SDK client: the four calls the router makes, and nothing else."""

    def __init__(
        self,
        model_ids: list[str] | None = None,
        *,
        list_error: Exception | None = None,
        chat_error: Exception | None = None,
        embed_error: Exception | None = None,
        embed_dims: int | None = None,
    ) -> None:
        self.model_ids = list(model_ids or [])
        self.list_error = list_error
        self.chat_error = chat_error
        self.embed_error = embed_error
        self.embed_dims = embed_dims
        self.calls: list[str] = []
        self.chat_kwargs: list[dict] = []
        self.models = SimpleNamespace(list=self._list)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._chat, parse=self._parse)
        )
        self.embeddings = SimpleNamespace(create=self._embed)

    async def _list(self):
        self.calls.append("models.list")
        if self.list_error:
            raise self.list_error
        return SimpleNamespace(data=[SimpleNamespace(id=i) for i in self.model_ids])

    async def _chat(self, **kwargs):
        self.calls.append("chat")
        self.chat_kwargs.append(kwargs)
        if self.chat_error:
            raise self.chat_error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    async def _parse(self, **kwargs):
        self.calls.append("parse")
        if self.chat_error:
            raise self.chat_error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    async def _embed(self, **kwargs):
        self.calls.append("embeddings")
        if self.embed_error:
            raise self.embed_error
        dims = self.embed_dims or kwargs.get("dimensions") or 1536
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * dims) for _ in kwargs.get("input", [])],
            usage=SimpleNamespace(prompt_tokens=1),
        )


def use(router: m.ModelRouter, client: FakeClient, monkeypatch, *, embeddings=True) -> FakeClient:
    """Wire a fake in place of the factory, leaving the factory itself untested here."""
    monkeypatch.setattr(router, "client", lambda: client)
    if embeddings:
        monkeypatch.setattr(router, "embeddings_client", lambda: client)
    return client


class TestOfflineMode:
    """No key is a supported configuration, not a broken one."""

    def test_an_absent_key_means_offline(self, offline):
        assert offline.offline is True
        assert offline.embeddings_offline is True

    async def test_completions_are_labelled_placeholders(self, offline):
        usage = m.Usage()
        text = await offline.complete(
            "narrative", system="s", user="u", usage=usage, label="profitability"
        )
        # Readers get a plain placeholder; the label in usage says why.
        assert "not available" in text
        assert "unaffected" in text
        assert "OPENAI_API_KEY" not in text
        # The trace has to say so too, or the memo would read as model output.
        assert usage.calls[0]["label"].endswith("(offline)")

    async def test_structured_calls_return_the_supplied_fallback(self, offline):
        class Verdict(BaseModel):
            call: str

        fallback = Verdict(call="hold")
        got = await offline.structured(
            "rag", system="s", user="u", schema=Verdict, usage=m.Usage(),
            label="scorecard", fallback=fallback,
        )
        assert got is fallback

    async def test_structured_calls_without_a_fallback_say_why(self, offline):
        class Verdict(BaseModel):
            call: str

        with pytest.raises(RuntimeError, match="offline"):
            await offline.structured(
                "rag", system="s", user="u", schema=Verdict, usage=m.Usage(), label="x"
            )

    async def test_json_calls_return_the_supplied_fallback(self, offline):
        got = await offline.json_call(
            "rag", system="s", user="u", usage=m.Usage(), label="x", fallback={"a": 1}
        )
        assert got == {"a": 1}

    async def test_embeddings_are_the_configured_width_and_normalised(self, offline, configure):
        configure(embedding_dims=16)
        vectors = await offline.embed(["alpha", "beta"])
        assert len(vectors) == 2
        for v in vectors:
            assert len(v) == 16
            assert math.sqrt(sum(x * x for x in v)) == pytest.approx(1.0)

    async def test_offline_embeddings_are_deterministic_and_text_dependent(self, offline):
        first, second = await offline.embed(["alpha", "beta"])
        again, _ = await offline.embed(["alpha", "gamma"])
        assert first == again
        assert first != second

    async def test_no_client_is_ever_constructed(self, offline, monkeypatch):
        def explode(spec):
            raise AssertionError("offline mode must not build a client")

        monkeypatch.setattr(m, "build_client", explode)
        await offline.complete("narrative", system="s", user="u", usage=m.Usage(), label="l")
        await offline.embed(["a"])
        assert await offline.resolve() == m.configured()


class TestClientFactory:
    def test_official_openai_uses_the_sdk_default_endpoint(self, configure):
        configure(llm_provider="openai", openai_api_key="sk-test", openai_base_url="")
        client = m.build_client(m.chat_spec())
        assert str(client.base_url).startswith("https://api.openai.com")
        assert client.api_key == "sk-test"

    def test_a_base_url_on_the_openai_provider_is_honoured(self, configure):
        configure(llm_provider="openai", openai_api_key="sk-test", openai_base_url="http://localhost:8000/v1")
        assert str(m.build_client(m.chat_spec()).base_url).rstrip("/") == "http://localhost:8000/v1"

    def test_a_compatible_gateway_gets_its_base_url(self, configure):
        from openai import AsyncAzureOpenAI, AsyncOpenAI

        configure(
            llm_provider="compatible",
            openai_api_key="gw-key",
            openai_base_url="https://aicredits.in/v1",
        )
        client = m.build_client(m.chat_spec())
        assert isinstance(client, AsyncOpenAI) and not isinstance(client, AsyncAzureOpenAI)
        assert str(client.base_url).rstrip("/") == "https://aicredits.in/v1"

    def test_azure_builds_an_azure_client_against_the_resource(self, configure):
        from openai import AsyncAzureOpenAI

        configure(
            llm_provider="azure",
            openai_api_key="azure-key",
            azure_openai_endpoint="https://my-resource.openai.azure.com",
            azure_openai_api_version="2024-10-21",
        )
        client = m.build_client(m.chat_spec())
        assert isinstance(client, AsyncAzureOpenAI)
        assert "my-resource.openai.azure.com" in str(client.base_url)
        assert client._api_version == "2024-10-21"

    def test_compatible_without_a_base_url_names_the_missing_variable(self, configure):
        configure(llm_provider="compatible", openai_api_key="gw-key", openai_base_url="")
        with pytest.raises(m.ProviderConfigurationError) as exc:
            m.build_client(m.chat_spec())
        assert "OPENAI_BASE_URL" in str(exc.value)

    def test_azure_without_an_endpoint_names_the_missing_variable(self, configure):
        configure(llm_provider="azure", openai_api_key="k", azure_openai_endpoint="")
        with pytest.raises(m.ProviderConfigurationError) as exc:
            m.build_client(m.chat_spec())
        assert "AZURE_OPENAI_ENDPOINT" in str(exc.value)

    def test_an_unknown_provider_says_what_the_choices_are(self, configure):
        configure(llm_provider="anthropic", openai_api_key="k")
        with pytest.raises(m.ProviderConfigurationError) as exc:
            m.build_client(m.chat_spec())
        message = str(exc.value)
        assert "LLM_PROVIDER" in message
        assert "compatible" in message

    def test_the_client_is_built_once(self, configure):
        configure(llm_provider="openai", openai_api_key="sk-test")
        router = m.ModelRouter()
        assert router.client() is router.client()


class TestEmbeddingsClient:
    def test_blank_embedding_settings_reuse_the_chat_client(self, configure):
        configure(
            llm_provider="compatible",
            openai_api_key="gw-key",
            openai_base_url="https://aicredits.in/v1",
            embedding_provider="",
            embedding_api_key="",
            embedding_base_url="",
        )
        router = m.ModelRouter()
        assert router.embeddings_client() is router.client()

    def test_its_own_url_and_key_win(self, configure):
        configure(
            llm_provider="compatible",
            openai_api_key="gw-key",
            openai_base_url="https://aicredits.in/v1",
            embedding_provider="openai",
            embedding_api_key="sk-real",
            embedding_base_url="",
        )
        router = m.ModelRouter()
        embeddings = router.embeddings_client()
        assert embeddings is not router.client()
        assert embeddings.api_key == "sk-real"
        # The gateway serves chat but not embeddings; inheriting its URL would defeat
        # the point of pointing EMBEDDING_PROVIDER somewhere else.
        assert str(embeddings.base_url).startswith("https://api.openai.com")

    def test_an_explicit_embedding_base_url_is_used(self, configure):
        configure(
            llm_provider="openai",
            openai_api_key="sk-chat",
            openai_base_url="",
            embedding_provider="compatible",
            embedding_api_key="",
            embedding_base_url="https://embeddings.example.com/v1",
        )
        router = m.ModelRouter()
        embeddings = router.embeddings_client()
        assert str(embeddings.base_url).rstrip("/") == "https://embeddings.example.com/v1"
        assert embeddings.api_key == "sk-chat"  # the key still falls back

    async def test_embeddings_can_be_live_while_chat_is_offline(self, configure, monkeypatch):
        configure(
            openai_api_key="", embedding_api_key="sk-embed", embedding_dims=4, llm_provider="openai"
        )
        router = m.ModelRouter()
        assert router.offline is True
        assert router.embeddings_offline is False
        fake = use(router, FakeClient(), monkeypatch)
        assert await router.embed(["a"]) == [[0.1] * 4]
        assert fake.calls == ["embeddings"]

    async def test_embed_asks_the_embeddings_endpoint_for_the_configured_width(
        self, configure, monkeypatch
    ):
        configure(openai_api_key="sk-chat", embedding_dims=32, embedding_model="emb-1")
        router = m.ModelRouter()
        fake = use(router, FakeClient(), monkeypatch)
        await router.embed(["a", "b"])
        assert fake.calls == ["embeddings"]


class TestModelResolution:
    CONFIGURED = {
        "model_narrative": "house-narrative",
        "model_rag": "house-rag",
        "model_memo": "house-memo",
        "model_critic": "house-critic",
    }

    @pytest.fixture
    def live(self, configure):
        configure(llm_provider="openai", openai_api_key="sk-test", **self.CONFIGURED)
        return m.ModelRouter()

    async def test_a_model_the_provider_lists_is_kept(self, live, configure, monkeypatch):
        configure(model_fallbacks=["gpt-4.1-mini"])
        use(live, FakeClient(["house-narrative", "house-rag", "house-memo", "house-critic"]), monkeypatch)
        assert await live.resolve() == m.configured()
        assert live.substitutions == {}

    async def test_a_missing_model_takes_the_first_available_fallback(self, live, configure, monkeypatch):
        configure(model_fallbacks=["absent-one", "present-two", "present-three"])
        use(live, FakeClient(["present-two", "present-three"]), monkeypatch)
        resolved = await live.resolve()
        assert resolved["narrative"] == "present-two"
        assert live.substitutions["house-narrative"] == "present-two"

    async def test_the_chain_order_is_the_operators(self, live, configure, monkeypatch):
        configure(model_fallbacks=["second-choice", "first-choice"])
        use(live, FakeClient(["first-choice", "second-choice"]), monkeypatch)
        assert (await live.resolve())["rag"] == "second-choice"

    async def test_a_fallback_never_silently_costs_more_than_what_was_configured(
        self, live, configure, monkeypatch
    ):
        """The memo used to prefer the largest entry in the chain, which meant a missing
        top-tier ID fell back to a model costing more than the one it stood in for, with
        nothing in the interface saying so."""
        configure(
            model_memo="gpt-5.6-sol",          # $1.25/M in
            model_fallbacks=["gpt-4.1", "gpt-4.1-mini"],  # $2.00 and $0.40
        )
        use(live, FakeClient(["gpt-4.1", "gpt-4.1-mini"]), monkeypatch)
        resolved = await live.resolve()
        assert resolved["memo"] == "gpt-4.1-mini", "took the dearer model"

    async def test_the_fallback_lands_nearest_the_configured_price(
        self, live, configure, monkeypatch
    ):
        configure(
            model_memo="gpt-5.6-terra",        # $0.40/M in
            model_fallbacks=["gpt-4o", "gpt-4.1-mini", "gpt-4o-mini"],
        )
        use(live, FakeClient(["gpt-4o", "gpt-4.1-mini", "gpt-4o-mini"]), monkeypatch)
        # gpt-4.1-mini is priced identically to the configured model.
        assert (await live.resolve())["memo"] == "gpt-4.1-mini"

    async def test_an_empty_listing_is_not_evidence_of_anything(self, live, configure, monkeypatch):
        configure(model_fallbacks=["gpt-4.1-mini"])
        use(live, FakeClient([]), monkeypatch)
        assert await live.resolve() == m.configured()
        assert live.substitutions == {}

    async def test_a_failed_listing_keeps_the_configured_ids(self, live, configure, monkeypatch):
        configure(model_fallbacks=["gpt-4.1-mini"])
        use(live, FakeClient(list_error=ConnectionError("no route to host")), monkeypatch)
        assert await live.resolve() == m.configured()

    async def test_a_chain_with_nothing_available_leaves_the_configuration_alone(
        self, live, configure, monkeypatch
    ):
        configure(model_fallbacks=["nowhere-mini", "nowhere-large"])
        use(live, FakeClient(["something-else"]), monkeypatch)
        assert await live.resolve() == m.configured()
        assert live.substitutions == {}

    async def test_azure_never_lists_because_those_are_deployment_names(self, live, configure, monkeypatch):
        configure(
            llm_provider="azure",
            azure_openai_endpoint="https://my-resource.openai.azure.com",
            model_fallbacks=["gpt-4.1-mini"],
        )
        fake = use(live, FakeClient(["gpt-4.1-mini"]), monkeypatch)
        assert await live.resolve() == m.configured()
        assert fake.calls == []

    async def test_resolution_happens_once(self, live, configure, monkeypatch):
        configure(model_fallbacks=["gpt-4.1-mini"])
        fake = use(live, FakeClient(["house-narrative"]), monkeypatch)
        await live.resolve()
        await live.resolve()
        assert fake.calls.count("models.list") == 1


class TestProbe:
    @pytest.fixture
    def live(self, configure):
        configure(
            llm_provider="compatible",
            openai_api_key="sk-secret-value",
            openai_base_url="https://aicredits.in/v1",
            embedding_api_key="",
            embedding_base_url="",
            embedding_dims=8,
            model_fallbacks=["gpt-4.1-mini"],
        )
        return m.ModelRouter()

    async def test_a_working_provider_reports_ok(self, live, monkeypatch):
        use(live, FakeClient(list(m.configured().values())), monkeypatch)
        report = await live.probe()
        assert report["ok"] is True
        assert report["error"] is None
        assert report["provider"] == "compatible"
        assert report["base_url"] == "https://aicredits.in/v1"
        assert report["api_key_set"] is True
        assert report["offline"] is False
        assert report["resolved"] == m.configured()
        assert report["substitutions"] == {}
        assert all(c["ok"] for c in report["checks"].values())
        assert report["checks"]["embeddings"]["dims"] == 8

    async def test_every_check_is_ok_plus_error(self, live, monkeypatch):
        use(live, FakeClient([]), monkeypatch)
        report = await live.probe()
        assert {"models", "chat", "embeddings"} <= set(report["checks"])
        for check in report["checks"].values():
            assert isinstance(check["ok"], bool)
            assert check["error"] is None or isinstance(check["error"], str)

    async def test_substitutions_are_reported(self, live, configure, monkeypatch):
        configure(model_fallbacks=["stand-in"])
        use(live, FakeClient(["stand-in"]), monkeypatch)
        report = await live.probe()
        assert report["substitutions"][m.configured()["narrative"]] == "stand-in"

    async def test_an_unreachable_provider_does_not_raise(self, live, monkeypatch):
        broken = ConnectionError("connection refused")
        use(
            live,
            FakeClient(list_error=broken, chat_error=broken, embed_error=broken),
            monkeypatch,
        )
        report = await live.probe()
        assert report["ok"] is False
        assert isinstance(report["error"], str)
        assert report["checks"]["chat"]["ok"] is False
        assert "connection refused" in report["checks"]["chat"]["error"]
        # A listing that cannot be reached is not itself a failure: the configured IDs
        # are used as-is and the report says they were not verified.
        assert report["checks"]["models"]["ok"] is True
        assert report["checks"]["models"]["verified"] is False

    async def test_a_dimension_mismatch_is_a_failure_not_a_shrug(self, live, monkeypatch):
        # The pgvector column is declared at EMBEDDING_DIMS, so this breaks writes later.
        use(live, FakeClient(list(m.configured().values()), embed_dims=1536), monkeypatch)
        report = await live.probe()
        assert report["checks"]["embeddings"]["ok"] is False
        assert "1536" in report["checks"]["embeddings"]["error"]

    async def test_offline_is_reported_as_offline(self, configure):
        configure(openai_api_key="", embedding_api_key="", llm_provider="openai")
        report = await m.ModelRouter().probe()
        assert report["offline"] is True
        assert report["ok"] is False
        assert report["api_key_set"] is False
        assert report["resolved"] == m.configured()
        assert "OPENAI_API_KEY" in report["checks"]["chat"]["error"]

    async def test_the_key_never_appears_in_the_report(self, live, configure, monkeypatch):
        configure(openai_base_url="https://user:sk-secret-value@gw.example.com/v1?api_key=sk-secret-value")
        # Providers quote the failing request back at you, key and all.
        boom = RuntimeError("401 unauthorized for key sk-secret-value")
        use(live, FakeClient(list_error=boom, chat_error=boom, embed_error=boom), monkeypatch)
        report = await live.probe()
        assert "sk-secret-value" not in json.dumps(report)
        assert "***" in report["base_url"]

    async def test_a_probe_that_blows_up_still_returns_a_result(self, live, monkeypatch):
        def explode():
            raise RuntimeError("client construction failed")

        monkeypatch.setattr(live, "client", explode)
        report = await live.probe()
        assert report["ok"] is False
        assert "client construction failed" in report["error"]


class TestDegradedProvider:
    """A provider that is configured but broken costs the prose, not the analysis.

    Every figure in a memo is computed in Python from the filings, so an unreachable
    model has no bearing on any of them. Aborting the run over it would throw away work
    that is already correct and complete.
    """

    @pytest.fixture
    def live(self, configure):
        configure(
            llm_provider="compatible",
            openai_api_key="sk-secret-value",
            openai_base_url="https://gw.example.com/v1",
            model_narrative="house-narrative",
            model_fallbacks=["house-narrative"],
        )
        router = m.ModelRouter()
        router._resolved = m.configured()  # the listing is not what is under test here
        return router

    async def test_an_unreachable_provider_yields_placeholder_prose(
        self, live, monkeypatch
    ):
        use(live, FakeClient(chat_error=connection_error()), monkeypatch)
        usage = m.Usage()
        text = await live.complete(
            "narrative", system="s", user="u", usage=usage, label="profitability"
        )
        # The reader is told the section is missing and the numbers stand; the
        # technical reason goes to router.degraded, the logs and doctor.py instead.
        assert "not available" in text
        assert "unaffected" in text
        assert "could not be reached" not in text
        assert "could not be reached" in live.degraded
        assert usage.calls[0]["label"] == "profitability (provider-error)"

    async def test_the_reason_is_recorded_once_for_the_whole_run(self, live, monkeypatch):
        use(live, FakeClient(chat_error=connection_error()), monkeypatch)
        assert live.degraded is None
        for label in ("profitability", "liquidity"):
            await live.complete("narrative", system="s", user="u", usage=m.Usage(), label=label)
        assert "could not be reached" in live.degraded
        assert "OPENAI_BASE_URL" in live.degraded

    async def test_the_first_reason_is_the_one_kept(self, live, monkeypatch):
        client = FakeClient(chat_error=connection_error())
        use(live, client, monkeypatch)
        await live.complete("narrative", system="s", user="u", usage=m.Usage(), label="a")
        client.chat_error = auth_error()
        await live.complete("narrative", system="s", user="u", usage=m.Usage(), label="b")
        assert "could not be reached" in live.degraded

    async def test_a_rejected_key_says_so(self, live, monkeypatch):
        use(live, FakeClient(chat_error=auth_error()), monkeypatch)
        text = await live.complete(
            "narrative", system="s", user="u", usage=m.Usage(), label="growth"
        )
        assert "API key" not in text
        assert "rejected the API key" in live.degraded
        assert "OPENAI_API_KEY" in live.degraded

    async def test_a_model_the_provider_does_not_have_says_so(self, live, monkeypatch):
        use(live, FakeClient(chat_error=missing_model_error()), monkeypatch)
        text = await live.complete(
            "narrative", system="s", user="u", usage=m.Usage(), label="growth"
        )
        assert "house-narrative" not in text
        assert "house-narrative" in live.degraded
        assert "MODEL_FALLBACKS" in live.degraded

    async def test_the_three_failures_are_told_apart(self, live):
        reasons = [
            m.failure_reason(connection_error()),
            m.failure_reason(auth_error()),
            m.failure_reason(missing_model_error(), "house-narrative"),
        ]
        assert len(set(reasons)) == 3
        assert "OPENAI_BASE_URL" in reasons[0]
        assert "OPENAI_API_KEY" in reasons[1]
        assert "MODEL_" in reasons[2]

    async def test_the_key_is_not_quoted_back_in_the_prose(self, live, monkeypatch):
        # Providers echo the offending request, key included, in the error message.
        use(live, FakeClient(chat_error=auth_error()), monkeypatch)
        text = await live.complete(
            "narrative", system="s", user="u", usage=m.Usage(), label="growth"
        )
        assert "sk-secret-value" not in text
        assert "sk-secret-value" not in live.degraded

    async def test_json_calls_fall_back_on_a_connection_error(self, live, monkeypatch):
        use(live, FakeClient(chat_error=connection_error()), monkeypatch)
        got = await live.json_call(
            "rag", system="s", user="u", usage=m.Usage(), label="citations", fallback={"a": 1}
        )
        assert got == {"a": 1}
        assert live.degraded is not None

    async def test_structured_calls_fall_back_on_a_rejected_key(self, live, monkeypatch):
        class Verdict(BaseModel):
            call: str

        use(live, FakeClient(chat_error=auth_error()), monkeypatch)
        fallback = Verdict(call="hold")
        got = await live.structured(
            "memo", system="s", user="u", schema=Verdict, usage=m.Usage(),
            label="verdict", fallback=fallback,
        )
        assert got is fallback
        assert "rejected the API key" in live.degraded

    async def test_a_structured_call_with_no_fallback_still_raises(self, live, monkeypatch):
        class Verdict(BaseModel):
            call: str

        use(live, FakeClient(chat_error=connection_error()), monkeypatch)
        with pytest.raises(openai.APIConnectionError):
            await live.structured(
                "memo", system="s", user="u", schema=Verdict, usage=m.Usage(), label="verdict"
            )
        assert live.degraded is not None

    async def test_the_probe_surfaces_it(self, live, monkeypatch):
        use(live, FakeClient(chat_error=connection_error()), monkeypatch)
        await live.complete("narrative", system="s", user="u", usage=m.Usage(), label="a")
        report = await live.probe()
        assert report["degraded"] == live.degraded


class TestRedaction:
    def test_credentials_in_the_url_are_stripped(self):
        redacted = m._redact_url("https://user:sk-live-abc@gw.example.com/v1?api_key=sk-live-abc&x=1")
        assert "sk-live-abc" not in redacted
        assert redacted.startswith("https://***@gw.example.com/v1")
        assert "x=1" in redacted

    def test_an_ordinary_url_is_left_readable(self):
        assert m._redact_url("https://aicredits.in/v1") == "https://aicredits.in/v1"

    def test_a_blank_url_stays_blank(self):
        assert m._redact_url("") == ""


def unsupported_temperature_error() -> Exception:
    """What a reasoning-family model answers when it is handed a temperature."""
    return openai.BadRequestError(
        "Error code: 400 - {'error': {'message': \"Unsupported value: 'temperature' does "
        "not support 0.0 with this model. Only the default (1) value is supported.\", "
        "'type': 'invalid_request_error', 'param': 'temperature', "
        "'code': 'unsupported_value'}}",
        response=httpx.Response(400, request=REQUEST),
        body={
            "error": {
                "message": "Unsupported value: 'temperature' is not supported.",
                "type": "invalid_request_error",
                "param": "temperature",
                "code": "unsupported_value",
            }
        },
    )


class TemperatureRefusingClient(FakeClient):
    """Rejects any call carrying ``temperature`` and accepts the same call without it."""

    async def _chat(self, **kwargs):
        self.calls.append("chat")
        self.chat_kwargs.append(kwargs)
        if "temperature" in kwargs:
            raise unsupported_temperature_error()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


class TestTemperatureRefusal:
    """A model that only accepts its default temperature must not cost us the prose.

    This was a live defect: every narrative, the sentiment call and both critic passes
    came back as placeholder text reading "[provider unavailable] … BadRequestError",
    and that text was rendered in the memo on the landing page. The figures were never
    affected — they are computed in Python — but the writing was gone.
    """

    @pytest.fixture
    def router(self, configure, monkeypatch):
        configure(openai_api_key="sk-test", llm_provider="openai")
        r = m.ModelRouter()
        monkeypatch.setattr(r, "model_for", _const("gpt-5.6-terra"))
        return r

    @pytest.mark.asyncio
    async def test_complete_retries_without_temperature(self, router, monkeypatch):
        client = use(router, TemperatureRefusingClient(), monkeypatch)

        text = await router.complete(
            "memo", system="s", user="u", usage=m.Usage(), label="memo"
        )

        assert text == '{"ok": true}'
        assert "temperature" in client.chat_kwargs[0]
        assert "temperature" not in client.chat_kwargs[1]
        assert router.degraded is None, "a recovered call is not a degraded run"

    @pytest.mark.asyncio
    async def test_json_call_retries_without_temperature(self, router, monkeypatch):
        client = use(router, TemperatureRefusingClient(), monkeypatch)

        out = await router.json_call(
            "critic", system="s", user="u", usage=m.Usage(), label="critic", fallback={}
        )

        assert out == {"ok": True}
        assert "temperature" not in client.chat_kwargs[1]

    @pytest.mark.asyncio
    async def test_the_refusal_is_remembered_for_later_calls(self, router, monkeypatch):
        client = use(router, TemperatureRefusingClient(), monkeypatch)

        await router.complete("memo", system="s", user="u", usage=m.Usage(), label="a")
        first_round = len(client.chat_kwargs)
        await router.complete("memo", system="s", user="u", usage=m.Usage(), label="b")

        # One probe for the whole process, not one failed request per call.
        assert first_round == 2
        assert len(client.chat_kwargs) == 3
        assert "temperature" not in client.chat_kwargs[2]

    @pytest.mark.asyncio
    async def test_an_unrelated_bad_request_still_degrades(self, router, monkeypatch):
        other = openai.BadRequestError(
            "Error code: 400 - {'error': {'message': 'context length exceeded', "
            "'param': 'messages', 'code': 'context_length_exceeded'}}",
            response=httpx.Response(400, request=REQUEST),
            body={"error": {"param": "messages", "code": "context_length_exceeded"}},
        )
        client = use(router, FakeClient(chat_error=other), monkeypatch)

        text = await router.complete(
            "memo", system="s", user="u", usage=m.Usage(), label="memo"
        )

        assert "not available" in text
        assert len(client.chat_kwargs) == 1, "no retry for an error about something else"


def _const(value):
    async def _f(_role):
        return value

    return _f
