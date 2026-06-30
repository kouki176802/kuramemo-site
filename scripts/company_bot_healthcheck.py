from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "output" / "operations" / "latest_company_bot_run.json"


def check_health(log_path: Path, max_age_seconds: int, now: Optional[float] = None) -> Tuple[bool, str]:
    if not log_path.exists():
        return False, "company bot has not completed a cycle"
    current = time.time() if now is None else now
    age = max(0.0, current - log_path.stat().st_mtime)
    if age > max_age_seconds:
        return False, f"company bot result is stale ({int(age)} seconds)"
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid company bot result: {exc}"
    results = {row.get("command", ""): row for row in payload.get("results", [])}
    required = {"-m trend_commerce run"}
    if payload.get("full_cycle"):
        required.add("-m trend_commerce wordpress-sync --site-dir output/site --status publish")
    missing = sorted(required.difference(results))
    if missing:
        return False, "critical task missing: " + ", ".join(missing)
    failures = [
        command for command in sorted(required)
        if int(results[command].get("returncode", 1)) != 0
    ]
    if failures:
        return False, "critical task failed: " + ", ".join(failures)
    return True, "company bot is healthy"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--max-age-minutes", type=int, default=130)
    args = parser.parse_args()
    healthy, message = check_health(args.log, max(1, args.max_age_minutes) * 60)
    print(message)
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
