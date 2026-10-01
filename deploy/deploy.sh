#!/usr/bin/env bash
# Production commands for Corpus. Run from any folder.
#
#   deploy/deploy.sh build                  Build the backend and proxy images.
#   deploy/deploy.sh models                 Download the AI models. The only
#                                           command that uses the internet.
#   deploy/deploy.sh up                     Start Corpus, or apply an update.
#   deploy/deploy.sh admin EMAIL [FIRST LAST]
#                                           Create an administrator.
#   deploy/deploy.sh backup [BACKUP-DIR]    Make an encrypted backup of all
#                                           data (default: backups/). Corpus
#                                           stops while it runs.
#   deploy/deploy.sh restore BACKUP         Replace all data with a backup.
#   deploy/deploy.sh rotate-key             Re-encrypt the data with a new key.
#                                           First run: uv run setup key rotate
#   deploy/deploy.sh down                   Stop Corpus. The data is kept.
#   deploy/deploy.sh logs [SERVICE]         Follow the logs.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=${CORPUS_ENV_FILE:-backend/.env}
[[ -f $ENV_FILE ]] || { echo "Missing $ENV_FILE: run 'uv run setup' in backend/ first." >&2; exit 1; }
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml "$@"; }
language=$(grep -E '^APP_LANGUAGE=' "$ENV_FILE" | cut -d= -f2 || true)
project=${COMPOSE_PROJECT_NAME:-corpus}
# Data volumes in a backup. Models (hf_models, ollama_data) are downloaded
# again with `models`.
VOLUMES=(minio_data qdrant_data)

# Encrypts/decrypts a stream with DATA_ENCRYPTION_KEY inside the backend
# image: nothing is written to disk unencrypted.
crypt() { compose run --rm --no-deps -T backend python -m maintenance.backup_crypt "$@"; }
# Raw volume contents as a gzip tar stream (compressed before encryption:
# Qdrant preallocates zero-filled files), read (or replaced) by a throwaway
# container without network.
volume_out() { docker run --rm --network none --user 0 -v "${project}_$1:/v:ro" corpus-backend:latest tar -C /v -czf - .; }
volume_in() {
  docker run --rm -i --network none --user 0 -v "${project}_$1:/v" corpus-backend:latest \
    sh -c 'find /v -mindepth 1 -delete && tar -C /v -xzpf -'
}
restart_app() { compose up -d --remove-orphans >/dev/null 2>&1 || echo "Start failed: run deploy/deploy.sh up" >&2; }

case "${1:-up}" in
  build)
    docker build -t corpus-backend:latest backend
    docker build -t corpus-proxy:latest --build-arg "APP_LANGUAGE=${language:-en}" frontend
    ;;
  models)
    compose --profile setup run --rm models
    compose --profile setup run --rm models-llm
    ;;
  up) compose up -d --remove-orphans ;;
  admin) shift; compose run --rm --no-deps backend python -m maintenance.create_admin "$@" ;;
  rotate-key)
    grep -qE '^DATA_ENCRYPTION_KEY_PREVIOUS=.+' "$ENV_FILE" || {
      echo "No rotation started: run 'uv run setup key rotate' in backend/ first." >&2; exit 1; }
    # Nothing may write with a key while the data is re-encrypted.
    compose stop backend worker
    compose up -d postgres qdrant minio
    compose run --rm --no-deps backend python -m maintenance.rotate_key
    sed -i '/^DATA_ENCRYPTION_KEY_PREVIOUS=/d' "$ENV_FILE"
    compose up -d --remove-orphans
    echo "Rotation finished; the old key is no longer used."
    ;;
  backup)
    dir=${2:-backups}/corpus-$(date +%Y%m%d-%H%M%S)
    umask 077
    mkdir -p "$dir"
    # Stopped, so the database, files and index are copied at the same moment.
    compose stop proxy backend worker
    trap restart_app EXIT
    compose up -d postgres
    compose exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' |
      crypt encrypt > "$dir/postgres.dump.enc"
    compose stop qdrant minio
    for volume in "${VOLUMES[@]}"; do
      volume_out "$volume" | crypt encrypt > "$dir/$volume.tar.gz.enc"
    done
    {
      echo "created=$(date -Iseconds)"
      echo "key_fingerprint=$(crypt fingerprint < "$dir/postgres.dump.enc")"
      echo "commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    } > "$dir/manifest"
    echo "Backup written to $dir ($(du -sh "$dir" | cut -f1))."
    echo "It is encrypted: restoring it needs the key with fingerprint $(grep key_fingerprint "$dir/manifest" | cut -d= -f2)."
    ;;
  restore)
    dir=${2:?usage: deploy/deploy.sh restore BACKUP_DIR}
    for part in postgres.dump "${VOLUMES[@]/%/.tar.gz}"; do
      [[ -f $dir/$part.enc ]] || { echo "Missing $dir/$part.enc" >&2; exit 1; }
    done
    cat "$dir/manifest" 2>/dev/null || true
    read -rp "Replace ALL current documents, users and chats with this backup? Type 'restore': " answer
    [[ $answer == restore ]] || { echo "Cancelled."; exit 1; }
    # Check key and integrity of every part before anything is deleted.
    for part in postgres.dump "${VOLUMES[@]/%/.tar.gz}"; do
      crypt decrypt < "$dir/$part.enc" > /dev/null
    done
    compose stop proxy backend worker qdrant minio
    trap restart_app EXIT
    compose up -d --wait postgres
    compose exec -T postgres sh -c 'PGOPTIONS=--client-min-messages=warning psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
    crypt decrypt < "$dir/postgres.dump.enc" |
      compose exec -T postgres sh -c 'pg_restore --single-transaction --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
    for volume in "${VOLUMES[@]}"; do
      crypt decrypt < "$dir/$volume.tar.gz.enc" | volume_in "$volume"
    done
    echo "Restored from $dir; starting the app (migrations run if the backup is older)."
    ;;
  down) compose down ;;
  logs) shift; compose logs -f "$@" ;;
  *) sed -n '2,17p' "$0"; exit 1 ;;
esac
