#!/bin/zsh
set -euo pipefail
ROOT_DIR="${0:A:h:h}"
export DOCKER_CONFIG="$ROOT_DIR/config/docker-anonymous"
export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"
if command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
else
  DOCKER_BIN="/Applications/Docker.app/Contents/Resources/bin/docker"
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi
"$DOCKER_BIN" compose --env-file "$ROOT_DIR/.env.wordpress" -f "$ROOT_DIR/docker-compose.wordpress.yml" stop
