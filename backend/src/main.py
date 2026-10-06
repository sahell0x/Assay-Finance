"""FastAPI application."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .agent.models import get_router
from .agent.progress import PIPELINE
from .api.analyses import _detail, _owns
from .api.analyses import router as analyses_router
from .api.auth import mount_auth
from .api.billing import router as billing_router
from .api.pdf import build_memo_pdf
from .api.tickers import router as tickers_router
from .api.watchlist import router as watchlist_router
from .config import settings
from .core.budget import public_budget_state
from .core.cache import close_redis, get_redis
from .db import repo
from .db.session import dispose_engine, get_session
from .deps import Requester, get_requester

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting %s (env=%s)", settings.app_name, settings.env)
    if not settings.openai_api_key:
        log.warning(
            "OPENAI_API_KEY is not set. The pipeline will run and every figure will be "
            "computed, but narratives and the memo will be deterministic placeholders."
        )
    try:
        # Resolve model IDs once at boot so any substitution is visible in the startup
        # log rather than surfacing mid-analysis.
        resolved = await get_router().resolve()
        log.info("models: %s", resolved)
    except Exception as exc:
        log.warning("model resolution deferred: %s", exc)
    yield
    await close_redis()
    await dispose_engine()
    log.info("stopped")


settings.check_production()

from .core.monitoring import capture_message, init_monitoring  # noqa: E402

init_monitoring("api")

app = FastAPI(
    title=settings.app_name,
    # The interactive docs are a map of every endpoint. Useful locally, not something to
    # publish on a production site.
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
    version="0.1.0",
    description=(
        "Automated equity research. Financial statements are pulled from public "
        "filings, every ratio is computed in Python, qualitative context is retrieved "
        "from SEC filings and news by vector search, and the recommendation comes from "
        "a deterministic rubric — never from the language model."
    ),
    lifespan=lifespan,
)

# Explicit origins with credentials enabled. A wildcard is not valid for credentialed
# requests and would break the session cookie in the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

mount_auth(app)
app.include_router(analyses_router)
app.include_router(billing_router)
app.include_router(tickers_router)
app.include_router(watchlist_router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/healthz", tags=["meta"])
async def healthz(db: AsyncSession = Depends(get_session)) -> dict:
    """Liveness plus a real check of both datastores."""
    checks: dict[str, str] = {}
    ok = True

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"[:200]
        ok = False

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"[:200]
        ok = False

    checks["models"] = "offline" if get_router().offline else "configured"
    return {"status": "ok" if ok else "degraded", "checks": checks, "version": "0.1.0"}


class ClientError(BaseModel):
    message: str = Field(default="", max_length=2000)
    digest: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=500)


@app.post("/client-errors", status_code=204, tags=["meta"])
async def client_error(report: ClientError) -> Response:
    """Crashes in the browser, reported by the site's error pages.

    Without this a page that breaks for a user is invisible to whoever runs the site.
    Logged, and forwarded to Sentry when it is configured.
    """
    log.warning("browser error on %s: %s (%s)", report.path, report.message[:300], report.digest)
    capture_message(f"Browser error: {report.message[:300]}", path=report.path, digest=report.digest)
    return Response(status_code=204)


@app.get("/meta/pipeline", tags=["meta"])
async def pipeline() -> dict:
    """The node list, so the interface can render the checklist before anything runs."""
    from .analytics.scoring import BUY_THRESHOLD, HOLD_THRESHOLD, WEIGHTS

    return {
        "pipeline": PIPELINE,
        "weights": WEIGHTS,
        "thresholds": {"buy": BUY_THRESHOLD, "hold": HOLD_THRESHOLD},
        "budget": await public_budget_state(),
    }


@app.get("/analyses/{analysis_id}/pdf", tags=["analyses"])
async def analysis_pdf(
    analysis_id: uuid.UUID,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> Response:
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No analysis with that id.")
    if a.status != "complete":
        raise HTTPException(status_code=409, detail="This analysis has not finished yet.")
    if not (_owns(a, requester) or a.public_slug):
        raise HTTPException(status_code=403, detail="This analysis belongs to someone else.")

    detail = await _detail(db, a, owned=True)
    payload = build_memo_pdf(detail.model_dump(mode="json"))
    filename = f"{a.ticker}-memo-{(a.completed_at or a.created_at).date().isoformat()}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
