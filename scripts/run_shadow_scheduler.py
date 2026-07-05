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
LATEST_RUN_LOG = ROOT / "output" / "operations" / "latest_company_bot_run.json"
SCHEDULER_STATE_LOG = ROOT / "output" / "operations" / "company_bot_state.json"
DISCORD_DAILY_SLOTS = (
    (7, 0), (8, 30), (10, 0), (11, 30), (13, 0), (14, 30),
    (16, 0), (17, 30), (19, 0), (20, 30), (22, 0), (23, 30),
)


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
            [py, "-m", "trend_commerce", "affiliate-program-scan"],
            # Discord is the safe review channel. Prepare enough approved A
            # variants for all 12 daily slots; B variants remain on experiment
            # hold and external SNS still requires an explicit --live run.
            [py, "-m", "trend_commerce", "trend-screen", "--max-items", "12", "--approve", "--build-site"],
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


def _send_discord_post() -> None:
    _run([
        sys.executable, "-m", "trend_commerce", "social-discord",
        "--platform", "x", "--limit", "1", "--send",
    ])


def _latest_due_discord_slot(now: datetime) -> datetime:
    due = [
        now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        for hour, minute in DISCORD_DAILY_SLOTS
        if now.replace(hour=hour, minute=minute, second=0, microsecond=0) <= now
    ]
    if due:
        return due[-1]
    yesterday = now - timedelta(days=1)
    hour, minute = DISCORD_DAILY_SLOTS[-1]
    return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _next_discord_slot(now: datetime) -> datetime:
    for hour, minute in DISCORD_DAILY_SLOTS:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target > now:
            return target
    tomorrow = now + timedelta(days=1)
    hour, minute = DISCORD_DAILY_SLOTS[0]
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _discord_delivery_due(now: datetime, last_sent_slot: Optional[datetime]) -> bool:
    latest = _latest_due_discord_slot(now)
    return last_sent_slot is None or last_sent_slot < latest


def _seconds_until_next_discord(now: datetime, last_sent_slot: Optional[datetime]) -> float:
    if _discord_delivery_due(now, last_sent_slot):
        return 5.0
    return max(5.0, (_next_discord_slot(now) - now).total_seconds())


def _load_last_full_cycle(
    state_path: Path = SCHEDULER_STATE_LOG,
    latest_path: Path = LATEST_RUN_LOG,
) -> Optional[datetime]:
    for log_path, key in ((state_path, "last_full_cycle_at"), (latest_path, "finished_at")):
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            if log_path == latest_path and not payload.get("full_cycle"):
                continue
            return datetime.fromisoformat(str(payload[key]))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _save_last_full_cycle(value: datetime, state_path: Path = SCHEDULER_STATE_LOG) -> None:
    _save_scheduler_state(value, _load_last_discord_slot(state_path), state_path)


def _load_last_discord_slot(state_path: Path = SCHEDULER_STATE_LOG) -> Optional[datetime]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(str(payload["last_discord_slot_at"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_scheduler_state(
    last_full_cycle: Optional[datetime],
    last_discord_slot: Optional[datetime],
    state_path: Path = SCHEDULER_STATE_LOG,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, str] = {}
    if last_full_cycle is not None:
        payload["last_full_cycle_at"] = last_full_cycle.isoformat(timespec="seconds")
    if last_discord_slot is not None:
        payload["last_discord_slot_at"] = last_discord_slot.isoformat(timespec="seconds")
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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

    # DockerやPCの再起動直後に全商品監査を重ねないよう、直近の完了時刻を復元する。
    last_full = _load_last_full_cycle()
    last_discord_slot = _load_last_discord_slot()
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
            last_full = datetime.now()
            _save_last_full_cycle(last_full)
        if _discord_delivery_due(now, last_discord_slot):
            _send_discord_post()
            # Missed slots are skipped instead of being burst-posted after a restart.
            last_discord_slot = _latest_due_discord_slot(now)
            _save_scheduler_state(last_full, last_discord_slot)
        regular_sleep = max(5, args.interval_minutes) * 60
        time.sleep(min(regular_sleep, _seconds_until_next_discord(now, last_discord_slot)))


if __name__ == "__main__":
    main()
