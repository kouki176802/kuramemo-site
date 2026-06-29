#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
PID_FILE="$ROOT_DIR/var/company_bot.pid"

if [[ ! -f "$PID_FILE" ]]; then
  print "起動中の会社BOTは記録されていません。"
  exit 0
fi
BOT_PID="$(<"$PID_FILE")"
if kill -0 "$BOT_PID" 2>/dev/null; then
  kill "$BOT_PID"
fi
rm "$PID_FILE"
print "くらメモ会社BOTを停止しました。"
