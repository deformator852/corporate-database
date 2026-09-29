#!/usr/bin/env bash
# Production helper. Run from anywhere:
#   deploy/deploy.sh build     build the backend and proxy images
#   deploy/deploy.sh models    download the AI models (the only step that
#                              uses the internet; run once and after a change)
#   deploy/deploy.sh up        start or update the stack
#   deploy/deploy.sh admin EMAIL [First Last]   create an administrator
#   deploy/deploy.sh down      stop it (data volumes are kept)
#   deploy/deploy.sh logs [service]
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=${CORPUS_ENV_FILE:-backend/.env}
export CORPUS_ENV_FILE=$ENV_FILE
[[ -f $ENV_FILE ]] || { echo "Missing $ENV_FILE: run 'uv run setup' in backend/ first." >&2; exit 1; }
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml "$@"; }
language=$(grep -E '^APP_LANGUAGE=' "$ENV_FILE" | cut -d= -f2 || true)

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
  down) compose down ;;
  logs) shift; compose logs -f "$@" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
