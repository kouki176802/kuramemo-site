#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
cd "$ROOT_DIR"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/private/tmp}/kuramemo_company_bot_cache"

print "くらメモ会社BOTを開始します。停止は Ctrl-C です。"
print "外部SNSへの実投稿は行いません。"
python3 scripts/run_shadow_scheduler.py --interval-minutes 60 --full-cycle-hours 24
