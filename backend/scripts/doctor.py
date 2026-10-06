#!/usr/bin/env python
"""Preflight doctor: will this configuration actually work?

    python scripts/doctor.py             # everything, including the two network probes
    python scripts/doctor.py --offline   # skip anything that needs the internet
    python scripts/doctor.py --json      # machine-readable, for CI

This exists to keep one promise: *change the API key and you are good to go*. It checks
the things that otherwise fail silently or late — a database that was never migrated, a
pgvector too old for ``halfvec``, a SEC User-Agent with no contact address (EDGAR answers
403), a CORS list that does not contain the frontend — and every failure prints the
command that fixes it.

Exit code is 0 when everything critical passes. Warnings never fail: running without an
API key is a legitimate mode (all figures are still computed from the filings, only the
prose is a placeholder) and so is an empty retrieval corpus.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    from src.config import settings  # noqa: E402
    from src.core.cache import close_redis, get_redis  # noqa: E402
    from src.db.session import SessionLocal, dispose_engine  # noqa: E402
except Exception as _exc:  # pragma: no cover - only reachable on a broken install
    print(f"FAIL  the application would not import: {_exc}")
    print("      fix: cd backend && uv venv && uv pip install -e '.[dev]'")
    raise SystemExit(1) from None

log = logging.getLogger("doctor")

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"

SECTIONS = (
    "Configuration",
    "Postgres",
    "Redis",
    "LLM provider",
    "Market data",
    "Retrieval corpus",
)

# Tables the application expects once `alembic upgrade head` has run.
EXPECTED_TABLES = {
    "users", "accounts", "sessions", "analyses", "analysis_events",
    "evidence", "watchlists", "watchlist_items", "usage_ledger", "news_chunks",
}

# halfvec — the column type the chunk store uses — arrived in pgvector 0.7.0.
MIN_PGVECTOR = (0, 7, 0)

INSECURE_SECRETS = {"", "change-me", "changeme", "secret", "dev-secret"}
SECRETISH = re.compile(r"key|token|secret|password|passwd|sig|credential", re.IGNORECASE)

COLORS = {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m", SKIP: "\033[90m"}
RESET = "\033[0m"


# --------------------------------------------------------------------------- results


@dataclass
class Check:
    section: str
    name: str
    status: str
    detail: str = ""
    fix: str = ""

    def as_dict(self) -> dict:
        out = {"section": self.section, "name": self.name, "status": self.status}
        if self.detail:
            out["detail"] = self.detail
        if self.fix:
            out["fix"] = self.fix
        return out


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def add(self, section: str, name: str, status: str, detail: str = "", fix: str = "") -> Check:
        check = Check(section, name, status, detail, fix)
        self.checks.append(check)
        return check

    def crashed(self, section: str, name: str, exc: BaseException, fix: str = "") -> Check:
        """Any unexpected exception becomes a failed check, never a traceback."""
        detail = " ".join(f"{type(exc).__name__}: {exc}".split())
        return self.add(section, name, FAIL, detail[:220], fix)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def ok(self) -> bool:
        return not self.failures


# --------------------------------------------------------------------------- helpers


def mask(secret: str | None) -> str:
    """Never print a credential. Enough characters to recognise it, not to use it."""
    s = (secret or "").strip()
    if not s:
        return "not set"
    if len(s) <= 10:
        return f"{'*' * len(s)} ({len(s)} chars)"
    return f"{s[:3]}…{s[-4:]} ({len(s)} chars)"


def redact_url(url: str | None) -> str:
    """Strip userinfo and any credential-shaped query parameter from a URL or DSN."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return "<unparseable>"
    netloc = parts.netloc
    if "@" in netloc:
        netloc = "***@" + netloc.rsplit("@", 1)[1]
    query = parts.query
    if query:
        query = urlencode(
            [(k, "***" if SECRETISH.search(k) else v) for k, v in parse_qsl(query, True)]
        )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)) or raw


def version_tuple(raw: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", raw or "")[:3])


def pick(data: dict, *names: str, default: Any = None) -> Any:
    """Read the first key that exists. The probe's exact field names are not ours."""
    for name in names:
        if isinstance(data, dict) and name in data and data[name] is not None:
            return data[name]
    return default


def okness(value: Any) -> tuple[bool | None, str]:
    """Normalise a probe result that may be a bool, a string, or a nested dict."""
    if isinstance(value, bool):
        return value, ""
    if isinstance(value, str):
        return (value.lower() in {"ok", "pass", "true", "yes"}), value
    if isinstance(value, dict):
        flag = pick(value, "ok", "success", "healthy", "passed")
        note = str(pick(value, "error", "detail", "message", "note", default="") or "")
        if isinstance(flag, bool):
            return flag, note
        return (None if flag is None else bool(flag)), note
    return None, ""


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


# ------------------------------------------------------------------- configuration


def check_configuration(report: Report) -> None:
    section = "Configuration"

    # ---- the API key, the one thing a new user is expected to change ----------
    api_key = str(getattr(settings, "openai_api_key", "") or "").strip()
    provider = str(getattr(settings, "llm_provider", "openai") or "openai").strip()
    embed_key = str(getattr(settings, "embedding_api_key", "") or "").strip()

    if api_key:
        report.add(section, "API key", PASS, f"OPENAI_API_KEY {mask(api_key)}")
    elif embed_key:
        report.add(
            section, "API key", WARN,
            "OPENAI_API_KEY not set (an embedding key is)",
            "chat calls will return placeholders; set OPENAI_API_KEY in backend/.env",
        )
    else:
        report.add(
            section, "API key", WARN,
            "OPENAI_API_KEY not set — offline mode",
            "set OPENAI_API_KEY=sk-... in backend/.env. Without it every ratio, score and "
            "chart is still computed from the filings, but narratives and the memo are "
            "labelled placeholders and embeddings are a deterministic hash, so retrieval "
            "returns arbitrary chunks.",
        )

    embed_provider = str(getattr(settings, "embedding_provider", "") or "").strip()
    detail = provider + (f", embeddings via {embed_provider}" if embed_provider and embed_provider != provider else "")
    report.add(section, "provider", PASS, detail)

    # ---- where calls are sent -------------------------------------------------
    base_url = str(getattr(settings, "openai_base_url", "") or "").strip()
    azure_endpoint = str(getattr(settings, "azure_openai_endpoint", "") or "").strip()
    embed_base = str(getattr(settings, "embedding_base_url", "") or "").strip()

    if provider.lower().startswith("azure"):
        if azure_endpoint:
            api_version = str(getattr(settings, "azure_openai_api_version", "") or "")
            suffix = f"  (api-version {api_version})" if api_version else ""
            report.add(section, "base URL", PASS, redact_url(azure_endpoint) + suffix)
        else:
            report.add(
                section, "base URL", FAIL,
                "LLM_PROVIDER=azure but AZURE_OPENAI_ENDPOINT is empty",
                "set AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com and "
                "AZURE_OPENAI_API_VERSION in backend/.env",
            )
    elif provider.lower() == "compatible" and not base_url:
        # `compatible` exists precisely to point at a gateway. Without a URL it would
        # silently fall through to api.openai.com, and the first symptom would be an
        # authentication failure against a provider the user never meant to call.
        report.add(
            section, "base URL", FAIL,
            "LLM_PROVIDER=compatible but OPENAI_BASE_URL is empty",
            "set OPENAI_BASE_URL to your gateway, e.g. https://aicredits.in/v1 — or set "
            "LLM_PROVIDER=openai to use api.openai.com",
        )
    else:
        shown = redact_url(base_url) if base_url else "https://api.openai.com/v1 (default)"
        if embed_base and embed_base != base_url:
            shown += f"  (embeddings: {redact_url(embed_base)})"
        report.add(section, "base URL", PASS, shown)

    # ---- google oauth ---------------------------------------------------------
    gid = str(getattr(settings, "google_client_id", "") or "").strip()
    gsecret = str(getattr(settings, "google_client_secret", "") or "").strip()
    redirect = str(getattr(settings, "oauth_redirect_url", "") or "")
    origin = str(getattr(settings, "frontend_url", "") or "").rstrip("/")

    if not gid and not gsecret:
        report.add(
            section, "Google sign-in", WARN,
            "not configured — email and password still work",
            (
                "to enable it, register a Web application client in the Google console "
                f"with JavaScript origin {origin} and redirect URI {redirect}, then set "
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env"
            ),
        )
    elif not (gid and gsecret):
        missing = "GOOGLE_CLIENT_SECRET" if gid else "GOOGLE_CLIENT_ID"
        report.add(
            section, "Google sign-in", FAIL,
            f"half configured — {missing} is empty",
            f"set {missing} in backend/.env, or clear both to disable Google sign-in",
        )
    else:
        report.add(section, "Google sign-in", PASS, "configured")
        report.add(
            section, "  JS origin", PASS,
            f"{origin}   <- 'Authorized JavaScript origins'",
        )
        report.add(
            section, "  redirect URI", PASS,
            f"{redirect}   <- 'Authorized redirect URIs'",
        )

    # ---- auth -----------------------------------------------------------------
    is_prod = bool(getattr(settings, "is_prod", False))
    secret = str(getattr(settings, "auth_secret", "") or "")
    weak = (
        secret.strip().lower() in INSECURE_SECRETS
        or "change" in secret.lower()
        or "do-not-use" in secret.lower()
        or secret.lower().startswith("dev-")
        or len(secret) < 32
    )
    if not weak:
        report.add(section, "AUTH_SECRET", PASS, f"set ({len(secret)} chars)")
    else:
        report.add(
            section, "AUTH_SECRET", FAIL if is_prod else WARN,
            "still the shipped placeholder" if secret else "empty",
            "every session token is forgeable with a value anyone can read in the repo — "
            "run `openssl rand -hex 32` and put it in backend/.env as AUTH_SECRET"
            + (" (this is FAIL because ENV=prod)" if is_prod else ""),
        )

    salt = str(getattr(settings, "ip_hash_salt", "") or "")
    if salt and "change" not in salt.lower() and not salt.startswith("dev-"):
        report.add(section, "IP_HASH_SALT", PASS, "set")
    else:
        report.add(
            section, "IP_HASH_SALT", FAIL if is_prod else WARN,
            "still the shipped placeholder",
            "anonymous-visitor IPs are hashed with a known salt, so the hashes are "
            "reversible by lookup — set IP_HASH_SALT to a random value in backend/.env",
        )

    if (
        secret
        and str(getattr(settings, "ip_hash_salt", "") or "") == secret
        and not weak
    ):
        report.add(
            section, "secret reuse", FAIL if is_prod else WARN,
            "AUTH_SECRET and IP_HASH_SALT are the same value",
            "they protect different things — anyone who learns the session secret can "
            "also reverse the anonymous IP hashes. Give IP_HASH_SALT its own "
            "`openssl rand -hex 32`",
        )

    # ---- do the browser-facing settings agree with each other? ----------------
    origins = [str(o).rstrip("/") for o in (getattr(settings, "cors_origins", []) or [])]
    frontend = str(getattr(settings, "frontend_url", "") or "").rstrip("/")
    if not origins:
        report.add(
            section, "CORS_ORIGINS", FAIL, "empty",
            "the browser will block every API call — set CORS_ORIGINS=http://localhost:3000 "
            "(comma-separated for more than one)",
        )
    elif "*" in origins:
        report.add(
            section, "CORS_ORIGINS", WARN, "wildcard",
            "credentialed requests are refused against a wildcard origin — list the exact "
            "frontend origins instead",
        )
    elif frontend and frontend not in origins:
        report.add(
            section, "CORS_ORIGINS", FAIL,
            f"{', '.join(origins)} does not contain FRONTEND_URL ({frontend})",
            f"the browser will block every API call from the app — add {frontend} to "
            "CORS_ORIGINS in backend/.env",
        )
    else:
        report.add(section, "CORS_ORIGINS", PASS, ", ".join(origins))

    cookie_domain = str(getattr(settings, "cookie_domain", "") or "").strip()
    try:
        cookie_attr = settings.cookie_domain_attr
    except Exception:
        cookie_attr = cookie_domain or None
    fe_host = host_of(frontend)
    if cookie_attr is None:
        report.add(
            section, "COOKIE_DOMAIN", PASS,
            f"{cookie_domain or 'unset'} — host-only cookie "
            "(correct unless the app and the API are on different subdomains)",
        )
    elif fe_host and not (
        fe_host == cookie_attr.lstrip(".")
        or fe_host.endswith("." + cookie_attr.lstrip("."))
    ):
        labels = fe_host.split(".")
        suggestion = (
            f"set COOKIE_DOMAIN=.{'.'.join(labels[-2:])} so it is a parent of {fe_host}"
            if len(labels) > 1
            else f"leave COOKIE_DOMAIN=localhost for local development ({fe_host} is a "
                 "single-label host, which must not carry a Domain attribute at all)"
        )
        report.add(
            section, "COOKIE_DOMAIN", FAIL,
            f"{cookie_attr} does not match FRONTEND_URL host ({fe_host})",
            f"the session cookie would never be sent back, so login silently fails — {suggestion}",
        )
    else:
        report.add(section, "COOKIE_DOMAIN", PASS, cookie_attr)

    if is_prod:
        secure = bool(getattr(settings, "cookie_secure", False))
        https = frontend.startswith("https://")
        if secure and https:
            report.add(section, "prod hardening", PASS, "COOKIE_SECURE on, FRONTEND_URL https")
        else:
            problems = []
            if not secure:
                problems.append("COOKIE_SECURE=false")
            if not https:
                problems.append("FRONTEND_URL is not https")
            report.add(
                section, "prod hardening", FAIL, ", ".join(problems),
                "ENV=prod serves the session cookie over plain HTTP — set COOKIE_SECURE=true "
                "and put the app behind TLS",
            )

    # ---- SEC contact address --------------------------------------------------
    ua = str(getattr(settings, "sec_user_agent", "") or "").strip().strip('"')
    if "@" in ua and len(ua) > 5:
        report.add(section, "SEC_USER_AGENT", PASS, ua)
    else:
        report.add(
            section, "SEC_USER_AGENT", FAIL, ua or "empty",
            "EDGAR returns 403 to a User-Agent with no contact address, so no filing is "
            "ever fetched and the corpus stays empty — set SEC_USER_AGENT to something "
            "like 'Your Name you@example.com' in backend/.env",
        )

    # ---- budget ---------------------------------------------------------------
    cap = float(getattr(settings, "daily_cap_usd", 0.0) or 0.0)
    if cap > 0:
        report.add(section, "DAILY_CAP_USD", PASS, f"${cap:.2f}/day")
    else:
        report.add(
            section, "DAILY_CAP_USD", FAIL, f"${cap:.2f}",
            "a cap of zero counts as already exhausted, so every run degrades to cached "
            "results — set DAILY_CAP_USD to the most you are willing to spend in a day",
        )


# ------------------------------------------------------------------------ postgres


async def check_postgres(report: Report) -> None:
    section = "Postgres"
    # Imported here, not at module scope, so an import failure is a failed check.
    from sqlalchemy import text

    dsn = str(getattr(settings, "database_url", "") or "")
    try:
        async with SessionLocal() as db:
            raw_version = str((await db.execute(text("SELECT version()"))).scalar_one())
            server = " ".join(raw_version.split()[:2])
            report.add(section, "connection", PASS, f"{server} at {redact_url(dsn)}")

            # -- pgvector -------------------------------------------------------
            ext = (
                await db.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one_or_none()
            if ext is None:
                report.add(
                    section, "pgvector", FAIL, "extension not installed",
                    "run `cd backend && alembic upgrade head` (the first migration creates "
                    "it), or `CREATE EXTENSION vector;` as a superuser if your host needs it",
                )
            elif version_tuple(ext) < MIN_PGVECTOR:
                report.add(
                    section, "pgvector", FAIL, f"{ext} (halfvec needs >= 0.7)",
                    "the chunk store uses halfvec columns and halfvec_cosine_ops, which do "
                    "not exist before pgvector 0.7 — upgrade the extension (the "
                    "pgvector/pgvector:pg17 image in docker-compose.yml ships a current one)",
                )
            else:
                report.add(section, "pgvector", PASS, f"{ext}")

            # -- schema ---------------------------------------------------------
            rows = (
                await db.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).scalars().all()
            present = set(rows)
            missing = sorted(EXPECTED_TABLES - present)
            if missing:
                report.add(
                    section, "schema", FAIL,
                    f"{len(missing)} of {len(EXPECTED_TABLES)} tables missing: "
                    + ", ".join(missing[:6]) + ("…" if len(missing) > 6 else ""),
                    "the database has not been migrated — run `cd backend && alembic upgrade head`",
                )
            else:
                report.add(section, "schema", PASS, f"all {len(EXPECTED_TABLES)} tables present")

            # -- migration revision ---------------------------------------------
            if "alembic_version" not in present:
                report.add(
                    section, "migrations", FAIL, "no alembic_version table",
                    "this database has never been migrated — run "
                    "`cd backend && alembic upgrade head`",
                )
            else:
                current = (
                    await db.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars().all()
                heads = alembic_heads()
                cur = ", ".join(current) or "none"
                if not current:
                    report.add(
                        section, "migrations", FAIL, "alembic_version is empty",
                        "run `cd backend && alembic upgrade head`",
                    )
                elif not heads:
                    report.add(
                        section, "migrations", PASS,
                        f"at {cur} (could not read alembic/versions to compare)",
                    )
                elif set(current) == heads:
                    report.add(section, "migrations", PASS, f"{cur} (head)")
                else:
                    report.add(
                        section, "migrations", FAIL,
                        f"at {cur}, code expects {', '.join(sorted(heads))}",
                        "run `cd backend && alembic upgrade head`",
                    )

            # -- the embedding column has to match EMBEDDING_DIMS ---------------
            if "news_chunks" in present:
                coltype = (
                    await db.execute(
                        text(
                            """
                            SELECT format_type(a.atttypid, a.atttypmod)
                            FROM pg_attribute a
                            WHERE a.attrelid = 'news_chunks'::regclass
                              AND a.attname = 'embedding'
                            """
                        )
                    )
                ).scalar_one_or_none()
                want = int(getattr(settings, "embedding_dims", 0) or 0)
                found = version_tuple(coltype or "")
                got = found[0] if found else None
                if coltype is None:
                    report.add(
                        section, "embedding column", FAIL, "news_chunks has no embedding column",
                        "run `cd backend && alembic upgrade head`",
                    )
                elif got == want:
                    report.add(section, "embedding column", PASS, f"{coltype} == EMBEDDING_DIMS")
                else:
                    report.add(
                        section, "embedding column", FAIL,
                        f"{coltype} but EMBEDDING_DIMS={want}",
                        "every insert into news_chunks will be rejected by Postgres — either "
                        f"set EMBEDDING_DIMS={got} in backend/.env or write a migration that "
                        "alters the column and re-index the corpus",
                    )
    except Exception as exc:
        report.crashed(
            section, "connection", exc,
            f"could not reach {redact_url(dsn)} — start it with `make up` (or "
            "`docker compose up -d db`) and check DATABASE_URL in backend/.env; the URL "
            "must use the postgresql+asyncpg:// driver",
        )


def alembic_heads() -> set[str]:
    """Revision(s) the code expects. Returns an empty set if alembic cannot be read."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        return set(ScriptDirectory.from_config(cfg).get_heads())
    except Exception as exc:
        log.debug("could not read the migration directory: %s", exc)
        return set()


# --------------------------------------------------------------------------- redis


async def check_redis(report: Report) -> None:
    section = "Redis"
    url = str(getattr(settings, "redis_url", "") or "")
    try:
        client = get_redis()
        await client.ping()
        info = {}
        try:
            info = await client.info("server")
        except Exception as exc:  # a locked-down Redis may refuse INFO
            log.debug("INFO refused: %s", exc)
        version = info.get("redis_version") or "version unknown"
        report.add(section, "connection", PASS, f"{version} at {redact_url(url)}")
    except Exception as exc:
        report.crashed(
            section, "connection", exc,
            f"could not reach {redact_url(url)} — the queue, the SSE progress stream and "
            "the budget guard all need it. Start it with `make up` (or "
            "`docker compose up -d redis`) and check REDIS_URL in backend/.env",
        )
        return

    try:
        from src.core.budget import budget_state

        state = await budget_state()
        detail = f"${state['spent_usd']:.4f} of ${state['cap_usd']:.2f} spent today"
        if state["exhausted"]:
            report.add(
                section, "daily budget", WARN, detail,
                "today's cap is used up, so new analyses fall back to cached results until "
                "UTC midnight — raise DAILY_CAP_USD if that is not what you want",
            )
        else:
            report.add(section, "daily budget", PASS, detail)
    except Exception as exc:
        report.crashed(section, "daily budget", exc)


# -------------------------------------------------------------------- llm provider


async def check_llm(report: Report, *, allow_network: bool) -> None:
    section = "LLM provider"
    try:
        from src.agent.models import get_router

        router = get_router()
    except Exception as exc:
        report.crashed(
            section, "router", exc,
            "src/agent/models.py would not import — the whole pipeline depends on it",
        )
        return

    offline = bool(getattr(router, "offline", not getattr(settings, "openai_api_key", "")))
    if offline:
        report.add(
            section, "mode", WARN, "offline (no API key)",
            "works end to end: filings are fetched, every ratio and score is computed, the "
            "PDF renders. What you do not get: model-written narratives and memo (clearly "
            "labelled placeholders instead) and real embeddings (a deterministic hash, so "
            "retrieved evidence is arbitrary). Set OPENAI_API_KEY to turn all of it on.",
        )
    else:
        report.add(section, "mode", PASS, "live (API key configured)")

    # A live probe needs the network; an offline router's probe does not.
    if not allow_network and not offline:
        report.add(
            section, "probe", SKIP, "--offline: not calling the provider",
            "re-run without --offline to verify the key, the model IDs and the embedding size",
        )
        await report_models_from_settings(report)
        return

    probe: dict[str, Any] | None = None
    probe_fn = getattr(router, "probe", None)
    if callable(probe_fn):
        try:
            result = probe_fn()
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=90)
            probe = result if isinstance(result, dict) else {"result": result}
            report.extra["probe"] = probe
        except Exception as exc:
            report.add(
                section, "probe", WARN, f"probe() raised {type(exc).__name__}: {exc}"[:200],
                "falling back to the router's own resolution below",
            )

    if probe is None:
        await probe_the_hard_way(report, router, offline=offline)
        return

    # The probe's field shape belongs to models.py, not to this script. Results may sit
    # under "checks" or at the top level, so look in both and degrade if neither has them.
    nested = probe.get("checks") if isinstance(probe.get("checks"), dict) else {}

    def sub(*names: str) -> Any:
        for name in names:
            if isinstance(nested, dict) and nested.get(name) is not None:
                return nested[name]
        return pick(probe, *names)

    resolved = pick(probe, "resolved", "models", "resolved_models", default={})
    if isinstance(resolved, dict) and resolved and all(isinstance(v, str) for v in resolved.values()):
        report.add(
            section, "models", PASS,
            ", ".join(f"{role}={mid}" for role, mid in sorted(resolved.items())),
        )
    else:
        await report_models_from_settings(report)

    models_check = sub("models", "model_list")
    models_ok, models_note = okness(models_check)
    verified = pick(models_check, "verified", default=True) if isinstance(models_check, dict) else True
    if models_ok is False and not offline:
        report.add(
            section, "model list", WARN, models_note or "could not list the provider's models",
            "the configured IDs are used as-is, so a model that does not exist on this "
            "account surfaces mid-analysis instead of here — normal for Azure and for "
            "gateways that do not implement /models",
        )

    subs = pick(probe, "substitutions", "fallbacks", default={}) or {}
    if isinstance(subs, dict) and subs:
        report.add(
            section, "substitutions", WARN,
            ", ".join(f"{want} -> {got}" for want, got in sorted(subs.items())),
            "the configured model IDs are not in this account's model list, so the router "
            "picked the nearest available tier. Set MODEL_* in backend/.env to IDs you can "
            "actually call if you want the ones you configured.",
        )
    elif verified:
        report.add(section, "substitutions", PASS, "none — configured models are available")
    else:
        report.add(
            section, "substitutions", PASS,
            "none — the provider returned no model list, so the configured IDs are used as-is",
        )

    chat_ok, chat_note = okness(sub("chat", "chat_ok", "completion", "chat_call"))
    if chat_ok is True:
        report.add(section, "chat call", PASS, chat_note or "a trivial completion succeeded")
    elif chat_ok is False and offline:
        report.add(section, "chat call", WARN, chat_note or "offline placeholder")
    elif chat_ok is False:
        report.add(
            section, "chat call", FAIL, chat_note or "a trivial completion failed",
            "narratives, the memo and the critic all go through this call. Check that the "
            "API key is valid and funded, that the base URL is right, and that the MODEL_* "
            "IDs exist on this account.",
        )
    else:
        report.add(section, "chat call", SKIP, "probe did not report a chat result")

    embed_check = sub("embeddings", "embedding", "embed", "embedding_ok")
    embed_ok, embed_note = okness(embed_check)
    dims = pick(embed_check, "dims", "dimensions", "size") if isinstance(embed_check, dict) else None
    if dims is None:
        config_block = probe.get("embeddings") if isinstance(probe.get("embeddings"), dict) else {}
        dims = pick(config_block, "dims", "dimensions") or pick(
            probe, "embedding_dims", "dims", "dimensions"
        )
    want_dims = int(getattr(settings, "embedding_dims", 0) or 0)

    if embed_ok is not True and (offline or getattr(router, "embeddings_offline", False)):
        # No key, so nothing reached a provider. The placeholder path is still worth
        # checking: it has to produce vectors the halfvec column will accept.
        local = await local_embedding_dims(router)
        report_embedding(report, True, "", local, want_dims, offline=True)
    else:
        report_embedding(report, embed_ok, embed_note, dims, want_dims, offline=offline)


async def local_embedding_dims(router: Any) -> int | None:
    """Width of a vector from the router itself. Free and local when there is no key."""
    try:
        vectors = await asyncio.wait_for(router.embed(["preflight"]), timeout=60)
        return len(vectors[0]) if vectors else 0
    except Exception as exc:
        log.debug("local embedding check failed: %s", exc)
        return None


async def report_models_from_settings(report: Report) -> None:
    """Fallback view of the model configuration that makes no network call."""
    roles = {
        "narrative": getattr(settings, "model_narrative", ""),
        "rag": getattr(settings, "model_rag", ""),
        "memo": getattr(settings, "model_memo", ""),
        "critic": getattr(settings, "model_critic", ""),
        "embedding": getattr(settings, "embedding_model", ""),
    }
    report.add(
        "LLM provider", "models", PASS,
        ", ".join(f"{k}={v}" for k, v in roles.items() if v) + "  (configured, not verified)",
    )


async def probe_the_hard_way(report: Report, router: Any, *, offline: bool) -> None:
    """Used when ModelRouter has no probe(): resolve IDs and embed one string."""
    section = "LLM provider"
    resolved: dict[str, str] = {}
    try:
        resolve = getattr(router, "resolve", None)
        if callable(resolve):
            out = resolve()
            if inspect.isawaitable(out):
                out = await asyncio.wait_for(out, timeout=60)
            resolved = out if isinstance(out, dict) else {}
    except Exception as exc:
        report.add(
            section, "models", WARN, f"could not resolve model IDs: {exc}"[:200],
            "the router falls back to the configured IDs as-is, so a wrong ID surfaces "
            "mid-analysis instead of here",
        )

    if resolved:
        report.add(
            section, "models", PASS,
            ", ".join(f"{role}={mid}" for role, mid in sorted(resolved.items())),
        )
    else:
        await report_models_from_settings(report)

    subs = getattr(router, "substitutions", {}) or {}
    if subs:
        report.add(
            section, "substitutions", WARN,
            ", ".join(f"{want} -> {got}" for want, got in sorted(subs.items())),
            "the configured model IDs are not available on this account; set MODEL_* in "
            "backend/.env to IDs you can call",
        )
    else:
        report.add(section, "substitutions", PASS, "none")

    report.add(
        section, "chat call", SKIP, "ModelRouter has no probe(); not spending a token to test",
        "",
    )

    want_dims = int(getattr(settings, "embedding_dims", 0) or 0)
    try:
        vectors = await asyncio.wait_for(router.embed(["preflight"]), timeout=60)
        got = len(vectors[0]) if vectors else 0
        report_embedding(report, True, "", got, want_dims, offline=offline)
    except Exception as exc:
        report_embedding(report, False, f"{type(exc).__name__}: {exc}"[:160], None, want_dims,
                         offline=offline)


def report_embedding(
    report: Report,
    ok: bool | None,
    note: str,
    dims: Any,
    want_dims: int,
    *,
    offline: bool,
) -> None:
    section = "LLM provider"
    try:
        got = int(dims) if dims is not None else None
    except (TypeError, ValueError):
        got = None

    if ok is False:
        report.add(
            section, "embedding call", FAIL, note or "an embedding call failed",
            "without embeddings nothing can be indexed and news RAG returns nothing — check "
            f"that EMBEDDING_MODEL ({getattr(settings, 'embedding_model', '?')}) exists on "
            "this account and that the key has access to the embeddings endpoint",
        )
        return
    if ok is None and got is None:
        report.add(section, "embedding call", SKIP, "probe did not report an embedding result")
        return

    label = "hash placeholder" if offline else "live"
    if got is None:
        report.add(section, "embedding call", PASS, f"{label}, dimensions not reported")
    elif got == want_dims:
        report.add(section, "embedding call", PASS, f"{label}, {got} dimensions == EMBEDDING_DIMS")
    else:
        report.add(
            section, "embedding call", FAIL, f"{label}, returned {got} dimensions, want {want_dims}",
            "the news_chunks.embedding column is fixed-width, so a mismatched vector is "
            f"rejected on insert — set EMBEDDING_DIMS={got} in backend/.env, or choose an "
            "embedding model that supports the dimensions you configured",
        )


# --------------------------------------------------------------------- market data


async def check_market_data(report: Report, *, allow_network: bool) -> None:
    section = "Market data"
    if not allow_network:
        report.add(section, "yfinance", SKIP, "--offline")
        report.add(section, "SEC EDGAR", SKIP, "--offline")
        return

    # -- yfinance ---------------------------------------------------------------
    def fetch_price() -> Any:
        import yfinance as yf

        return getattr(yf.Ticker("AAPL").fast_info, "last_price", None)

    try:
        price = await asyncio.wait_for(asyncio.to_thread(fetch_price), timeout=45)
        if price:
            report.add(section, "yfinance", PASS, f"AAPL last price {float(price):,.2f}")
        else:
            report.add(
                section, "yfinance", FAIL, "fast_info returned no price",
                "yfinance scrapes an undocumented endpoint that changes without notice — "
                "try `uv pip install -U yfinance`; fundamentals come from here, so an "
                "analysis would run with no market data",
            )
    except TimeoutError:
        report.add(
            section, "yfinance", FAIL, "timed out after 45s",
            "check outbound network access, or re-run with --offline to skip this",
        )
    except Exception as exc:
        report.crashed(
            section, "yfinance", exc,
            "fundamentals and the price snapshot come from here — try "
            "`uv pip install -U yfinance`",
        )

    # -- SEC EDGAR --------------------------------------------------------------
    try:
        import httpx

        from src.data.news.edgar import TICKER_MAP, headers

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(TICKER_MAP, headers=headers())
        if resp.status_code == 403:
            report.add(
                section, "SEC EDGAR", FAIL, "403 Forbidden",
                "EDGAR rejects requests whose User-Agent has no contact address — set "
                "SEC_USER_AGENT to something like 'Your Name you@example.com' in backend/.env",
            )
        elif resp.status_code != 200:
            report.add(
                section, "SEC EDGAR", FAIL, f"HTTP {resp.status_code}",
                "EDGAR rate-limits at 10 requests/second and blocks abusers for a while — "
                "wait a minute and re-run; if it persists check outbound network access",
            )
        else:
            count = len(resp.json())
            report.add(section, "SEC EDGAR", PASS, f"ticker map OK, {count:,} symbols")
    except Exception as exc:
        report.crashed(
            section, "SEC EDGAR", exc,
            "filings are the highest-signal source in the system; without EDGAR the corpus "
            "is RSS only. Check outbound network access to www.sec.gov.",
        )


# ----------------------------------------------------------------- retrieval corpus


async def check_corpus(report: Report) -> None:
    section = "Retrieval corpus"
    blockers = {
        c.name for c in report.checks
        if c.section == "Postgres" and c.status == FAIL and c.name in {"connection", "schema"}
    }
    if blockers:
        reason = (
            "Postgres is not reachable"
            if "connection" in blockers
            else "news_chunks does not exist yet"
        )
        report.add(
            section, "news_chunks", SKIP, reason,
            "nothing can be indexed until the Postgres failures above are fixed",
        )
        return

    try:
        from src.data.news.store import indexed_tickers

        async with SessionLocal() as db:
            rows = await indexed_tickers(db)
        tickers = len(rows)
        chunks = sum(int(r.get("chunks") or 0) for r in rows)
        if tickers:
            sample = ", ".join(str(r["ticker"]) for r in rows[:8])
            more = "…" if tickers > 8 else ""
            report.add(
                section, "news_chunks", PASS,
                f"{tickers} tickers, {chunks:,} chunks  ({sample}{more})",
            )
        else:
            report.add(
                section, "news_chunks", WARN, "empty",
                "the first analysis of each ticker will pay for the EDGAR fetch, the "
                "chunking and the embedding inline — pre-warm it with "
                "`make seed` (python scripts/seed_index.py --popular)",
            )
    except Exception as exc:
        report.crashed(
            section, "news_chunks", exc,
            "the table is created by `alembic upgrade head`",
        )


# -------------------------------------------------------------------------- output


def render(report: Report, *, color: bool) -> str:
    width = max((len(c.name) for c in report.checks), default=10)
    lines: list[str] = []

    def tag(status: str) -> str:
        text = status.upper()
        return f"{COLORS[status]}{text}{RESET}" if color else text

    for section in SECTIONS:
        checks = [c for c in report.checks if c.section == section]
        if not checks:
            continue
        lines.append("")
        lines.append(section)
        for check in checks:
            lines.append(f"  {tag(check.status)}  {check.name:<{width}}  {check.detail}".rstrip())
            if check.fix and check.status in (FAIL, WARN, SKIP):
                indent = " " * (width + 10)
                label = "fix:" if check.status == FAIL else "note:"
                lines.append(
                    textwrap.fill(
                        check.fix, width=96, initial_indent=f"{indent}{label} ",
                        subsequent_indent=indent + " " * (len(label) + 1),
                    )
                )

    passed = sum(1 for c in report.checks if c.status == PASS)
    skipped = sum(1 for c in report.checks if c.status == SKIP)
    parts = [f"{passed} passed"]
    if report.warnings:
        parts.append(f"{len(report.warnings)} warning{'s' if len(report.warnings) != 1 else ''}")
    if report.failures:
        parts.append(f"{len(report.failures)} failed")
    if skipped:
        parts.append(f"{skipped} skipped")

    verdict = "ready" if report.ok else "not ready"
    if color:
        verdict = f"{COLORS[PASS if report.ok else FAIL]}{verdict}{RESET}"
    lines.append("")
    lines.append(f"{', '.join(parts)} — {verdict}")
    if report.failures:
        lines.append("Fix the failures above, then re-run `make doctor`.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- main


async def run(args: argparse.Namespace) -> Report:
    report = Report()
    allow_network = not args.offline

    steps = (
        ("Configuration", lambda: check_configuration(report)),
        ("Postgres", lambda: check_postgres(report)),
        ("Redis", lambda: check_redis(report)),
        ("LLM provider", lambda: check_llm(report, allow_network=allow_network)),
        ("Market data", lambda: check_market_data(report, allow_network=allow_network)),
        ("Retrieval corpus", lambda: check_corpus(report)),
    )
    for section, step in steps:
        try:
            outcome = step()
            if inspect.isawaitable(outcome):
                await outcome
        except Exception as exc:  # belt and braces: one check must never end the run
            report.crashed(section, "checks", exc)
    return report


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that this configuration will actually work.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit code is 0 when everything critical passes. Warnings do not fail.",
    )
    parser.add_argument("--offline", action="store_true", help="skip the checks that need network")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--no-color", action="store_true", help="plain output")
    parser.add_argument("-v", "--verbose", action="store_true", help="show library log output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.ERROR,
        format="%(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        report = await run(args)
    finally:
        try:
            await close_redis()
        except Exception as exc:
            log.debug("closing redis: %s", exc)
        try:
            await dispose_engine()
        except Exception as exc:
            log.debug("disposing the engine: %s", exc)

    if args.json:
        payload = {
            "ok": report.ok,
            "offline": args.offline,
            "summary": {
                "passed": sum(1 for c in report.checks if c.status == PASS),
                "warnings": len(report.warnings),
                "failed": len(report.failures),
                "skipped": sum(1 for c in report.checks if c.status == SKIP),
            },
            "checks": [c.as_dict() for c in report.checks],
        }
        payload.update(report.extra)
        print(json.dumps(payload, indent=2, default=str))
    else:
        color = not args.no_color and sys.stdout.isatty()
        print(f"{getattr(settings, 'app_name', 'app')} — preflight doctor")
        print(f"env={getattr(settings, 'env', '?')}  backend={BACKEND}")
        print(render(report, color=color))

    return 0 if report.ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
