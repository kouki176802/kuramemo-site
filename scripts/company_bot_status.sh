#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
DOCKER_BIN="/Applications/Docker.app/Contents/Resources/bin/docker"
export DOCKER_CONFIG="$ROOT_DIR/config/docker-anonymous"
export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"

if [[ ! -x "$DOCKER_BIN" ]]; then
  print -u2 "Docker Desktopが見つかりません"
  exit 1
fi

"$DOCKER_BIN" compose \
  --env-file "$ROOT_DIR/.env.wordpress" \
  -f "$ROOT_DIR/docker-compose.wordpress.yml" \
  ps company-bot wordpress database

print "\n直近の会社BOTログ"
"$DOCKER_BIN" compose \
  --env-file "$ROOT_DIR/.env.wordpress" \
  -f "$ROOT_DIR/docker-compose.wordpress.yml" \
  logs --tail 30 company-bot
