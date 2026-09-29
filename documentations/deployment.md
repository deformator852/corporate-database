# Installing Corpus on a company server

Corpus runs entirely inside the company network. After installation no
container can reach the internet: only the one-off model download (step 3)
does, and only when you run it.

## Requirements

- Linux server with Docker and Docker Compose v2
- 16 GB RAM or more (the AI model is the largest consumer); a GPU is optional
- A host name users will open, e.g. `corpus.company.local`, and either a
  company TLS certificate or Caddy's internal one (`TLS=internal`)

## Install

```sh
git clone <repository> corpus && cd corpus
cd backend && uv run setup && cd ..      # secrets, language, models, chunking
```

Then set the proxy in `backend/.env`:

```sh
SITE_ADDRESS=corpus.company.local
TLS=internal            # or "/certs/fullchain.pem /certs/privkey.pem" (files in deploy/certs/)
```

```sh
deploy/deploy.sh build                   # build the images
deploy/deploy.sh models                  # download AI models (needs internet once)
deploy/deploy.sh up                      # start; migrations run automatically
deploy/deploy.sh admin you@company.com   # first administrator; prints a password once
```

Open `https://corpus.company.local`, sign in, change the password on the Users
page and check the System page: every component should be "Running".

With `TLS=internal`, install Caddy's root certificate on the users' machines
(`docker compose -f docker-compose.prod.yml exec proxy cat /data/caddy/pki/authorities/local/root.crt`),
or use a company certificate instead.

## Keep safe

- **`backend/.env`** holds every secret, including `DATA_ENCRYPTION_KEY`.
  Documents and chats are encrypted with it: **without it they cannot be read**.
  Store a copy outside the server, separately from backups of the data.
- Put the Docker volumes on an encrypted disk: search vectors and document
  names are not encrypted by the application.

## Update

```sh
git pull
deploy/deploy.sh build && deploy/deploy.sh up
```

After changing the embedding or LLM model in `uv run configure`, run
`deploy/deploy.sh models` again.

## Useful

- `deploy/deploy.sh logs backend` — logs of one service
- `HTTP_PORT` / `HTTPS_PORT` in `backend/.env` — other ports if 80/443 are taken
- GPU for the AI model: uncomment the matching lines under `ollama` in
  `docker-compose.prod.yml`
