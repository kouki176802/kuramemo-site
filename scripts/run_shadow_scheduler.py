"""くらメモ会社BOTのローカル運用スケジューラー。

既定は外部SNSへ投稿しない安全運用です。トレンド・商品・サイト・
WordPress・SNS学習を一巡させ、実投稿だけは明示フラグを必須にします。
Ctrl-Cで停止できます。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parent.parent


def cycle_commands(
    full_cycle: bool,
    dispatch: bool = False,
    live: bool = False,
    platform: str = "",
    limit: int = 1,
    sync_wordpress: bool = True,
) -> List[List[str]]:
    py = sys.executable
    commands: List[List[str]] = [
        [py, "-m", "trend_commerce", "collect"],
        [py, "-m", "trend_commerce", "run"],
    ]
    if full_cycle:
        commands.extend([
            [py, "-m", "trend_commerce", "trend-screen", "--build-site"],
            [py, "-m", "trend_commerce", "product-ops", "--mode", "daily"],
            [py, "-m", "trend_commerce", "product-expand-cache", "--target", "8", "--refresh", "--build-site"],
            [py, "-m", "trend_commerce", "social-ab-release", "--minimum-impressions", "500"],
            [py, "-m", "trend_commerce", "social-learning-report"],
        ])
        if sync_wordpress:
            commands.append([
                py, "-m", "trend_commerce", "wordpress-sync",
                "--site-dir", "output/site", "--status", "publish",
            ])
    if dispatch:
        command = [py, "-m", "trend_commerce", "social-dispatch", "--limit", str(max(1, limit))]
        if platform:
            command.extend(["--platform", platform])
        if live:
            command.append("--live")
        commands.append(command)
    commands.append([py, "-m", "trend_commerce", "report"])
    return commands


def _run(command: Sequence[str]) -> Dict[str, object]:
    started = datetime.now().isoformat(timespec="seconds")
    command_text = " ".join(command)
    timeout = 1800 if "product-ops" in command_text else (600 if "trend-screen" in command_text else 300)
    try:
        result = subprocess.run(list(command), cwd=str(ROOT), check=False, timeout=timeout)
        returncode = result.returncode
        error = ""
    except subprocess.TimeoutExpired:
        returncode = 124
        error = "timeout after %s seconds" % timeout
    return {
        "command": " ".join(command[1:]),
        "started_at": started,
        "returncode": returncode,
        "error": error,
    }


def run_once(
    full_cycle: bool = True,
    dispatch: bool = False,
    live: bool = False,
    platform: str = "",
    limit: int = 1,
    sync_wordpress: bool = True,
) -> int:
    results: List[Dict[str, object]] = []
    critical_failed = False
    for command in cycle_commands(full_cycle, dispatch, live, platform, limit, sync_wordpress):
        result = _run(command)
        results.append(result)
        # 収集先や楽天APIの一時障害で全社BOTを止めない。記事生成だけは重大失敗扱い。
        if result["returncode"] and command[-1] == "run":
            critical_failed = True
    log_dir = ROOT / "output" / "operations"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "latest_company_bot_run.json"
    log_path.write_text(
        json.dumps({
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "full_cycle": full_cycle,
            "results": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 1 if critical_failed else 0


def _send_morning_discord() -> None:
    _run([
        sys.executable, "-m", "trend_commerce", "social-discord",
        "--platform", "x", "--limit", "1", "--send",
    ])


def _seconds_until_next_morning(now: datetime, last_sent_date: str) -> float:
    target = now.replace(hour=7, minute=30, second=0, microsecond=0)
    if last_sent_date == now.date().isoformat() or now >= target:
        target += timedelta(days=1)
    return max(5.0, (target - now).total_seconds())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--full-cycle-hours", type=int, default=24)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--light", action="store_true", help="ネット調査・商品入替・WordPress同期を省略")
    parser.add_argument("--no-wordpress-sync", action="store_true")
    parser.add_argument("--dispatch", action="store_true", help="承認済み期限到来投稿を処理。既定はdry-run")
    parser.add_argument("--platform", choices=["x", "threads", "instagram"], help="投稿対象SNSを限定")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--live", action="store_true", help="実投稿。認証と明示同意が必須")
    parser.add_argument("--i-understand-paid-api", action="store_true")
    args = parser.parse_args()
    if args.live and not args.dispatch:
        parser.error("--liveには--dispatchが必要です")
    if args.live and not args.i_understand_paid_api:
        parser.error("--liveには--i-understand-paid-api が必要です")
    if args.live and not args.platform:
        parser.error("--liveでは--platformで投稿先を限定してください")
    if args.once:
        raise SystemExit(run_once(
            full_cycle=not args.light,
            dispatch=args.dispatch,
            live=args.live,
            platform=args.platform or "",
            limit=args.limit,
            sync_wordpress=not args.no_wordpress_sync,
        ))

    last_full: Optional[datetime] = None
    last_discord_date = ""
    while True:
        now = datetime.now()
        full_due = not args.light and (
            last_full is None or now - last_full >= timedelta(hours=max(1, args.full_cycle_hours))
        )
        run_once(
            full_cycle=full_due,
            dispatch=args.dispatch,
            live=args.live,
            platform=args.platform or "",
            limit=args.limit,
            sync_wordpress=not args.no_wordpress_sync,
        )
        if full_due:
            last_full = now
        morning_due = (now.hour == 7 and now.minute >= 30) or now.hour == 8
        if morning_due and last_discord_date != now.date().isoformat():
            _send_morning_discord()
            last_discord_date = now.date().isoformat()
        regular_sleep = max(5, args.interval_minutes) * 60
        # 1時間周期で起動しても朝便だけは7:30に合わせる。
        time.sleep(min(regular_sleep, _seconds_until_next_morning(now, last_discord_date)))


if __name__ == "__main__":
    main()
