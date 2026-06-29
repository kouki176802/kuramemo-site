#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
PID_FILE="$ROOT_DIR/var/company_bot.pid"
OUT_LOG="$ROOT_DIR/output/operations/company_bot.stdout.log"
ERR_LOG="$ROOT_DIR/output/operations/company_bot.stderr.log"

mkdir -p "$ROOT_DIR/var" "$ROOT_DIR/output/operations"
if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(<"$PID_FILE")"
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    print "くらメモ会社BOTは起動済みです（PID: $EXISTING_PID）"
    exit 0
  fi
fi

nohup /bin/zsh "$ROOT_DIR/scripts/run_company_bot.command" >>"$OUT_LOG" 2>>"$ERR_LOG" </dev/null &
BOT_PID=$!
print "$BOT_PID" > "$PID_FILE"
disown "$BOT_PID" 2>/dev/null || true
print "くらメモ会社BOTをバックグラウンド起動しました（PID: $BOT_PID）"
print "停止: zsh $ROOT_DIR/scripts/stop_company_bot_background.sh"
