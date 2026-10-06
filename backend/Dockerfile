FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the container healthcheck; build-essential is not needed because
# every wheel in the dependency set ships manylinux binaries.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer, and the expensive one. It installs from requirements.lock rather
# than from pyproject.toml's version ranges: the ranges are deliberately loose for
# local development, but an image rebuilt in six months would happily resolve pandas 4
# or langgraph 2 and break the "add your API key and go" promise with no source change
# to blame. The lock is regenerated with:
#     uv pip compile pyproject.toml -o requirements.lock
#
# src/ is deliberately absent here so that editing a Python file does not re-download
# the whole dependency set.
COPY pyproject.toml requirements.lock README.md ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY scripts ./scripts

# Install the project itself, and note that this must happen HERE, after the source
# COPYs -- not up in the dependency layer next to the lock install.
#
# hatchling's `packages = ["src"]` silently emits a wheel containing nothing but
# dist-info metadata when src/ is not in the build context; it does not treat the
# missing directory as an error. Verified: 3 files in the wheel without src/ present
# versus 55 with it. Run against the dependency layer above, this would install an
# empty distribution, and `import src` would then resolve only because WORKDIR happens
# to sit on sys.path -- fine under uvicorn/arq/alembic from /app, broken the moment
# anything runs from another directory.
#
# --no-deps makes requirements.lock the single source of truth for versions: pip is
# not allowed to quietly upgrade a pinned package to satisfy a pyproject range.
RUN pip install --no-cache-dir --no-deps .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as a normal user. HOME is set explicitly because yfinance resolves its timezone
# cache through platformdirs, which falls back to HOME -- and an unset HOME would put
# it at /.cache, which this user cannot write.
RUN useradd --create-home --uid 1001 appuser
ENV HOME=/home/appuser
USER appuser

EXPOSE 8000

# /healthz returns 200 even when a datastore is down -- it reports {"status":
# "degraded"} in the body rather than failing the request -- so `curl -f` alone would
# call a container with a dead database healthy. Hence the grep on the body.
# The worker uses this same image but serves no HTTP; it disables this check in compose.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz | grep -q '"status": *"ok"' || exit 1

# The entrypoint waits for the datastores, optionally migrates, then execs CMD so the
# real process gets PID 1 and a clean SIGTERM. See docker-entrypoint.sh.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
