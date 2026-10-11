#!/usr/bin/env bash
# Production commands for Corpus. Run from any folder.
#
#   deploy/deploy.sh build                  Build the backend and proxy images.
#   deploy/deploy.sh models                 Download (or update) the AI models.
#   deploy/deploy.sh up                     Start Corpus, or apply an update.
#                                           Downloads the models first when
#                                           missing: the only internet use.
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
setting() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//' || true; }
key_store=$(setting KEY_STORE)
profiles=()
if [[ $key_store == vault ]]; then
  # The encryption key comes from Vault: start vault-tunnel, aimed at VAULT_ADDR's host:port.
  vault_addr=$(setting VAULT_ADDR)
  upstream=${vault_addr#*://}
  upstream=${upstream%%/*}
  [[ $upstream == *:* ]] || upstream+=$([[ $vault_addr == https:* ]] && echo :443 || echo :80)
  export VAULT_UPSTREAM=$upstream
  profiles=(--profile vault)
fi
oidc_issuer=$(setting OIDC_ISSUER)
if [[ -n $oidc_issuer ]]; then
  # Single sign-on: start sso-tunnel, aimed at the provider's host (https, 443 unless given).
  upstream=${oidc_issuer#*://}
  upstream=${upstream%%/*}
  [[ $upstream == *:* ]] || upstream+=:443
  export SSO_UPSTREAM=$upstream
  profiles+=(--profile sso)
fi
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ${profiles[@]+"${profiles[@]}"} "$@"; }
language=$(setting APP_LANGUAGE)
languages=$(setting APP_LANGUAGES)
project=${COMPOSE_PROJECT_NAME:-corpus}
# Data volumes in a backup. Models (hf_models, ollama_data) are downloaded
# again by `up` when missing.
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

# The embedding model and the LLM named in .env, downloaded (in parallel) when
# not on disk yet. The app containers have no internet: without the models
# every document fails and the chat cannot answer. Checks need no internet.
ensure_models() {
  local downloads=() llm name tag
  if ! compose --profile setup run --rm --no-deps models python -m maintenance.download_models --check >/dev/null 2>&1; then
    echo "Downloading the embedding model $(setting EMBEDDING_MODEL)..."
    compose --profile setup run --rm models &
    downloads+=($!)
  fi
  # Ollama keeps a manifest per model: library/NAME/TAG (TAG defaults to latest).
  llm=$(setting LLM_MODEL)
  name=${llm%%:*}
  tag=latest
  [[ $llm == *:* ]] && tag=${llm#*:}
  [[ $name == */* ]] || name=library/$name
  if ! compose --profile setup run --rm --no-deps --entrypoint test models-llm \
      -f "/root/.ollama/models/manifests/registry.ollama.ai/$name/$tag" >/dev/null 2>&1; then
    echo "Downloading the LLM $llm..."
    compose --profile setup run --rm models-llm &
    downloads+=($!)
  fi
  local pid
  for pid in ${downloads[@]+"${downloads[@]}"}; do
    wait "$pid" || { echo "A model download failed: check the internet connection and run deploy/deploy.sh up again." >&2; exit 1; }
  done
}

case "${1:-up}" in
  build)
    docker build -t corpus-backend:latest backend
    docker build -t corpus-proxy:latest --build-arg "APP_LANGUAGE=${language:-en}" --build-arg "APP_LANGUAGES=$languages" frontend
    ;;
  models)
    compose --profile setup run --rm models
    compose --profile setup run --rm models-llm
    ;;
  up)
    ensure_models
    compose up -d --remove-orphans
    ;;
  admin) shift; compose run --rm --no-deps backend python -m maintenance.create_admin "$@" ;;
  rotate-key)
    # With Vault the keys are there, not in .env; rotate_key checks them itself.
    [[ $key_store == vault ]] || grep -qE '^DATA_ENCRYPTION_KEY_PREVIOUS=.+' "$ENV_FILE" || {
      echo "No rotation started: run 'uv run setup key rotate' in backend/ first." >&2; exit 1; }
    # Nothing may write with a key while the data is re-encrypted.
    compose stop backend worker
    compose up -d postgres qdrant minio
    compose run --rm --no-deps backend python -m maintenance.rotate_key
    if [[ $key_store == vault ]]; then
      compose up -d --remove-orphans
      echo "Data re-encrypted. Remove the old key from Vault: cd backend && uv run setup key finish"
    else
      sed -i '/^DATA_ENCRYPTION_KEY_PREVIOUS=/d' "$ENV_FILE"
      compose up -d --remove-orphans
      echo "Rotation finished; the old key is no longer used."
    fi
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
  *) sed -n '2,18p' "$0"; exit 1 ;;
esac
