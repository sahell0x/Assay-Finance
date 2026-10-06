#!/bin/sh
# Entrypoint shared by the api and the worker containers.
#
# This replaces the older `sh -c "alembic upgrade head && uvicorn ..."` for three
# reasons, all of which only bite in production:
#
#   1. Signals. `exec "$@"` hands PID 1 to uvicorn/arq, so `docker compose stop`
#      delivers SIGTERM to the real process. With `sh -c "a && b"` the shell is PID 1
#      and /bin/sh does not forward signals to its child, so every shutdown burns the
#      full 10s grace period and then gets SIGKILLed mid-request.
#   2. Migrations belong to exactly one container. RUN_MIGRATIONS=1 is set on the api
#      only; two containers racing `alembic upgrade head` against one database is a
#      lock fight that eventually loses.
#   3. The wait below is belt-and-braces behind compose's `condition: service_healthy`.
#      That condition is the right primary mechanism, but a restarted db container can
#      flap back to accepting connections a moment after the dependent process has
#      already given up, and `depends_on` is not re-evaluated on restart.
#
# Everything here is intentionally dependency-free: python is the only interpreter in
# the image, and there is no postgres or redis client installed to probe with.

set -e

# Block until every datastore named in the environment accepts a TCP connection.
# Parsing the URLs rather than hardcoding host:port keeps this correct whether the
# process is running inside compose (db/redis) or against a tunnel or managed service.
python3 - <<'PY'
import os
import socket
import sys
import time
from urllib.parse import urlsplit

targets = []
for var, default_port in (("DATABASE_URL", 5432), ("REDIS_URL", 6379)):
    raw = os.environ.get(var, "").strip()
    if not raw:
        continue
    parts = urlsplit(raw)
    if not parts.hostname:
        print(f"entrypoint: cannot parse a host out of {var}, skipping wait", flush=True)
        continue
    targets.append((var, parts.hostname, parts.port or default_port))

timeout = float(os.environ.get("WAIT_FOR_TIMEOUT", "60"))
deadline = time.monotonic() + timeout

for var, host, port in targets:
    while True:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"entrypoint: {var} -> {host}:{port} ready", flush=True)
                break
        except OSError as exc:
            if time.monotonic() >= deadline:
                sys.exit(
                    f"entrypoint: gave up after {timeout:.0f}s waiting for "
                    f"{var} at {host}:{port} ({exc})"
                )
            time.sleep(1)
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "entrypoint: alembic upgrade head" >&2
    alembic upgrade head
    echo "entrypoint: migrations applied" >&2
fi

exec "$@"
