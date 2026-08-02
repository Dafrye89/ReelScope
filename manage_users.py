from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from auth_store import AuthStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ReelScope local users.")
    parser.add_argument("username")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("VIDEO_FRAMES_DATA_DIR", "web_data")))
    parser.add_argument("--password-stdin", action="store_true", required=True)
    parser.add_argument("--claim-existing", action="store_true")
    args = parser.parse_args()

    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise SystemExit("password input was empty")
    data_dir = args.data_dir.resolve()
    store = AuthStore(data_dir / "reelscope.sqlite3")
    user = store.upsert_admin(args.username, password, utc_now())
    claimed = 0
    if args.claim_existing:
        jobs_dir = data_dir / "jobs"
        job_ids = [path.name for path in jobs_dir.iterdir() if path.is_dir()] if jobs_dir.is_dir() else []
        claimed = store.assign_unowned_jobs(user.id, job_ids, utc_now())
    print(f"admin ready: {user.username}; existing jobs assigned: {claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
