#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
ENV_FILE="$ROOT_DIR/.env.wordpress"
COMPOSE_FILE="$ROOT_DIR/docker-compose.wordpress.yml"
export DOCKER_CONFIG="$ROOT_DIR/config/docker-anonymous"
export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"

if command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
elif [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
  DOCKER_BIN="/Applications/Docker.app/Contents/Resources/bin/docker"
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
else
  print -u2 "Docker Desktopが必要です。インストール後にもう一度実行してください。"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  print -u2 ".env.wordpress がありません。config/wordpress.env.example をコピーして値を変更してください。"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

"$DOCKER_BIN" compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d database wordpress

for attempt in {1..30}; do
  if curl -fsS "http://127.0.0.1:${WP_LOCAL_PORT:-8080}/wp-admin/install.php" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

WP="$DOCKER_BIN compose --env-file $ENV_FILE -f $COMPOSE_FILE --profile tools run --rm wpcli wp"
if ! $=WP core is-installed >/dev/null 2>&1; then
  $=WP core install \
    --url="http://127.0.0.1:${WP_LOCAL_PORT:-8080}" \
    --title="${WP_SITE_TITLE:-くらメモ}" \
    --admin_user="$WP_ADMIN_USER" \
    --admin_password="$WP_ADMIN_PASSWORD" \
    --admin_email="$WP_ADMIN_EMAIL" \
    --skip-email
fi

$=WP theme activate kuramemo
$=WP option update blog_public 0
$=WP option update permalink_structure '/%postname%/'
$=WP rewrite flush --hard

for category in 'AI・ガジェット' '美容' 'フィットネス' '健康' '季節・暮らし' '防災・備蓄' '家事・時短' '旅行・外出'; do
  $=WP term create category "$category" --porcelain >/dev/null 2>&1 || true
done

"$DOCKER_BIN" compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d company-bot

print "WordPressを起動しました: http://127.0.0.1:${WP_LOCAL_PORT:-8080}"
print "管理画面: http://127.0.0.1:${WP_LOCAL_PORT:-8080}/wp-admin/"
print "会社BOTもDocker内で常駐します。Terminalは閉じて構いません。"
