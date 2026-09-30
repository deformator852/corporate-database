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
  Setup shows the key once and waits until you confirm a copy is saved; store
  it outside the server, separately from backups of the data.
  `cd backend && uv run setup key` prints its fingerprint, `--show` the key.
- Corpus remembers the key's fingerprint and does not start with another key
  (logs: "is not the key the stored data is encrypted with"). Restore the
  original key from your copy; the fingerprints tell which one it is.
- Put the Docker data on an encrypted disk (below): search vectors, document
  names, user emails and the audit log are not encrypted by the application.
- Make backups (below) and keep them on another machine.

## Update

```sh
git pull
deploy/deploy.sh build && deploy/deploy.sh up
```

After changing the embedding or LLM model in `uv run configure`, run
`deploy/deploy.sh models` again.

## Backups

```sh
deploy/deploy.sh backup /srv/corpus-backups     # default: backups/ in the repository
```

Copies the database, the document files and the search index into
`corpus-YYYYMMDD-HHMMSS/`. The app is stopped while it runs (under a minute
for small installations, longer with many documents) so all parts match; it
starts again by itself. Every file is encrypted with `DATA_ENCRYPTION_KEY`:
a backup is useless without the key, and a stolen backup reveals nothing.
`manifest` names the key's fingerprint.

Nightly, keeping 14 days (`crontab -e` as a user in the `docker` group):

```
0 3 * * * /opt/corpus/deploy/deploy.sh backup /srv/corpus-backups >> /var/log/corpus-backup.log 2>&1 && find /srv/corpus-backups -maxdepth 1 -name 'corpus-*' -mtime +14 -exec rm -rf {} +
```

Copy the backup directory to another machine (rsync, NAS): a backup on the
same disk is lost with it.

**Restore** (replaces all current data; asks to type `restore`):

```sh
deploy/deploy.sh restore /srv/corpus-backups/corpus-20260930-030000
```

`.env` must hold the key the backup was made with (the manifest names its
fingerprint; `uv run setup key` shows the current one). Every part is checked
before anything is deleted. An older backup is migrated on start. AI models
are not in backups: after a restore on a new server run `deploy/deploy.sh models`.

After a key rotation, old backups still need the old key: keep it (marked with
its fingerprint) until those backups are deleted.

## Encrypt the disk

Corpus encrypts document content itself, but Postgres also holds document
names, user emails and the audit log, and Qdrant holds search vectors, from
which parts of the text can be reconstructed. Keep all Docker data on a LUKS
encrypted volume so a stolen disk or a discarded server reveals nothing.

On a new server the simplest way is the installer's "encrypt disk" option
(Ubuntu, Debian, RHEL all offer it). To use a separate data disk instead
(here `/dev/sdb`; **this erases it**):

```sh
sudo cryptsetup luksFormat /dev/sdb              # choose a long passphrase
sudo cryptsetup open /dev/sdb corpus-data
sudo mkfs.ext4 /dev/mapper/corpus-data
sudo mkdir -p /srv/docker && sudo mount /dev/mapper/corpus-data /srv/docker
echo '{"data-root": "/srv/docker"}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker                    # before `deploy.sh up`
```

To open it at boot, add `corpus-data /dev/sdb none luks` to `/etc/crypttab`
and `/dev/mapper/corpus-data /srv/docker ext4 defaults 0 2` to `/etc/fstab`.
The boot then waits for the passphrase at the console. Unattended boot is
possible with a key file (`luksAddKey`) or TPM (`systemd-cryptenroll --tpm2-device=auto`),
but a key stored on the same machine protects only the removed disk, not
the running server. Store the LUKS passphrase like `DATA_ENCRYPTION_KEY`:
outside the server.

Check: `lsblk -f` shows `crypto_LUKS` under the disk and `docker info | grep "Docker Root Dir"`
shows `/srv/docker`.

## Rotate the encryption key

When the key may have leaked, or by policy:

```sh
cd backend && uv run setup key rotate && cd ..   # new key; confirm its backup
deploy/deploy.sh rotate-key                      # stops the app, re-encrypts, starts
```

`rotate-key` re-encrypts every file, text and chat, then removes the old key
from `.env`. If it stops halfway, fix the cause and run it again: it continues
where it stopped. Until it finishes, keep the old key: part of the data is
still sealed with it.

## Useful

- `deploy/deploy.sh logs backend` — logs of one service
- Chat capacity: `cd backend && uv run configure` sets how many questions a
  user may ask per 10 minutes (default 20) and how many answers the AI writes
  at the same time (default 4; each needs extra memory, the step shows how
  much). Apply with `deploy/deploy.sh up`. Every user gets one answer at a time.
- `HTTP_PORT` / `HTTPS_PORT` in `backend/.env` — other ports if 80/443 are taken
- GPU for the AI model: uncomment the matching lines under `ollama` in
  `docker-compose.prod.yml`
