#!/bin/zsh
set -euo pipefail
ROOT_DIR="${0:A:h:h}"
docker compose --env-file "$ROOT_DIR/.env.wordpress" -f "$ROOT_DIR/docker-compose.wordpress.yml" stop
