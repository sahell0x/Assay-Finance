#!/usr/bin/env python
"""Clear the anonymous run counters and today's spend. Development only.

You will exhaust the anonymous caps within an afternoon of working on this: three runs
per cookie, and ANON_IP_DAILY_CAP per network per day. Both live only in Redis, keyed
under ``quota:`` and ``spend:``, so clearing them restores the allowance without
touching a single stored analysis.

    python scripts/reset_quota.py            # clear the counters
    python scripts/reset_quota.py --show     # list them without deleting

Raising ANON_RUN_LIMIT and ANON_IP_DAILY_CAP in backend/.env is the alternative, but
that changes the behaviour you are testing rather than resetting it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.core.cache import close_redis, get_redis  # noqa: E402

PREFIXES = ("quota:*", "spend:*")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="list the keys, delete nothing")
    args = parser.parse_args()

    if settings.is_prod:
        print("Refusing to run: ENV is set to production.", file=sys.stderr)
        return 1

    try:
        redis = get_redis()
        keys: list[str] = []
        for pattern in PREFIXES:
            keys.extend([k async for k in redis.scan_iter(pattern)])

        if not keys:
            print("Nothing to clear — no quota or spend counters are set.")
            return 0

        if args.show:
            for key in sorted(keys):
                print(f"  {key} = {await redis.get(key)}")
            return 0

        await redis.delete(*keys)
        print(f"Cleared {len(keys)} counter(s): " + ", ".join(sorted(keys)[:6]) + (
            f", and {len(keys) - 6} more" if len(keys) > 6 else ""
        ))
        return 0
    except Exception as exc:
        print(f"Could not reach Redis at {settings.redis_url}: {exc}", file=sys.stderr)
        return 1
    finally:
        await close_redis()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
