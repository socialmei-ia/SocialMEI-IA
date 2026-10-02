#!/usr/bin/env bash

set -euo pipefail
umask 077

BASE_DIR="/home/ubuntu/socialmei"
BACKUP_DIR="$BASE_DIR/backups"
DATE="$(date +'%Y-%m-%d_%H-%M-%S')"

mkdir -p "$BACKUP_DIR"
cd "$BASE_DIR"

echo "[$(date)] Iniciando backup SocialMEI"

# Backup do PostgreSQL
docker exec socialmei-postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP_DIR/postgres_$DATE.dump"

# Backup das configurações
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" \
  compose.yaml \
  Caddyfile \
  .env

# Backup dos dados persistentes do n8n
docker compose stop n8n

trap 'docker compose start n8n >/dev/null 2>&1 || true' EXIT

docker run --rm \
  -v socialmei_n8n_data:/data:ro \
  -v "$BACKUP_DIR":/backup \
  alpine \
  tar -czf "/backup/n8n_data_$DATE.tar.gz" -C /data .

docker compose start n8n
trap - EXIT

# Apaga backups com mais de 14 dias
find "$BACKUP_DIR" -type f \
  \( -name "*.dump" -o -name "*.tar.gz" \) \
  -mtime +14 -delete

echo "[$(date)] Backup concluído"
