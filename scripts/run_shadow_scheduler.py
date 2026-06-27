"""Local scheduler. Stop with Ctrl-C.

Default mode is free/safe dry-run. Live posting requires explicit flags and
social API credentials.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run_once(dispatch: bool = False, live: bool = False, platform: str = "", limit: int = 1) -> int:
    command = [sys.executable, "-m", "trend_commerce", "collect"]
    first = subprocess.run(command, cwd=str(ROOT), check=False)
    if first.returncode:
        return first.returncode
    second = subprocess.run([sys.executable, "-m", "trend_commerce", "run"], cwd=str(ROOT), check=False)
    if dispatch:
        command = [sys.executable, "-m", "trend_commerce", "social-dispatch", "--limit", str(max(1, limit))]
        if platform:
            command.extend(["--platform", platform])
        if live:
            command.append("--live")
        subprocess.run(command, cwd=str(ROOT), check=False)
    subprocess.run([sys.executable, "-m", "trend_commerce", "report"], cwd=str(ROOT), check=False)
    return second.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dispatch", action="store_true", help="承認済み期限到来投稿を処理。既定はdry-run")
    parser.add_argument("--platform", choices=["x", "threads", "instagram"], help="投稿対象SNSを限定")
    parser.add_argument("--limit", type=int, default=1, help="1回のdispatchで処理する最大投稿数")
    parser.add_argument("--live", action="store_true", help="実投稿。--dispatchと認証情報が必須")
    parser.add_argument(
        "--i-understand-paid-api",
        action="store_true",
        help="X/Meta等の有料・外部APIを使うリスクを理解して実投稿を許可",
    )
    args = parser.parse_args()
    if args.live and not args.dispatch:
        parser.error("--liveには--dispatchが必要です")
    if args.live and not args.i_understand_paid_api:
        parser.error("--liveには--i-understand-paid-api が必要です")
    if args.live and not args.platform:
        parser.error("--liveでは--platformで投稿先を限定してください")
    if args.once:
        raise SystemExit(run_once(dispatch=args.dispatch, live=args.live, platform=args.platform or "", limit=args.limit))
    while True:
        run_once(dispatch=args.dispatch, live=args.live, platform=args.platform or "", limit=args.limit)
        time.sleep(max(5, args.interval_minutes) * 60)


if __name__ == "__main__":
    main()
