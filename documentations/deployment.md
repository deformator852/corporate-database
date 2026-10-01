# Deploying Corpus on a company server

This guide shows you how to install Corpus on a Linux server in your company
network and keep it running: updates, backups, disk encryption and key
rotation.

## About the deployment

Corpus runs entirely inside the company network. After installation, no
container can reach the internet. Only the model download job reaches it, and
only when you run it.

All settings and secrets live in one file, `backend/.env`. Documents and chats
are encrypted with `DATA_ENCRYPTION_KEY` from that file, so the data cannot be
read without the key.

## Prerequisites

* A Linux server with Docker and Docker Compose v2
* `git` and [uv](https://docs.astral.sh/uv/) on the server, to run the setup
  command
* 16 GB of RAM or more. The AI model uses most of it. A GPU is optional.
* A host name that users will open, for example `corpus.company.local`
* Either a company TLS certificate, or Caddy's internal certificate
  (`TLS=internal`)
* Internet access during installation only, to download the AI models

## Installing Corpus

1. Get the code and run the setup. It generates the secrets and asks for the
   system language, the AI models and the chat limits.

   ```sh
   git clone REPOSITORY-URL corpus && cd corpus
   cd backend && uv run setup && cd ..
   ```

   Replace REPOSITORY-URL with the address of the Corpus repository.

2. When the setup shows `DATA_ENCRYPTION_KEY`, store a copy outside the
   server, then type `saved`. See
   [Protecting the key and the data](#protecting-the-key-and-the-data).

3. In `backend/.env`, set the address and the certificate:

   ```sh
   SITE_ADDRESS=corpus.company.local
   TLS=internal
   ```

   To use a company certificate, put the files in `deploy/certs/` and set
   `TLS="/certs/fullchain.pem /certs/privkey.pem"`.

4. Build the images:

   ```sh
   deploy/deploy.sh build
   ```

5. Download the AI models. This is the only step that needs the internet.

   ```sh
   deploy/deploy.sh models
   ```

6. Start Corpus. Database migrations run automatically.

   ```sh
   deploy/deploy.sh up
   ```

7. Create the first administrator. The command prints the password once.

   ```sh
   deploy/deploy.sh admin ADMIN-EMAIL
   ```

8. Open `https://corpus.company.local` and sign in. On the **Users** page,
   change the password. On the **System status** page, check that every
   component shows **Running**.

With `TLS=internal`, browsers do not trust the certificate until you install
Caddy's root certificate on the users' computers. Print it with:

```sh
docker compose -f docker-compose.prod.yml exec proxy \
  cat /data/caddy/pki/authorities/local/root.crt
```

## Protecting the key and the data

* `backend/.env` holds every secret, including `DATA_ENCRYPTION_KEY`. Without
  that key, documents and chats cannot be read. Store a copy outside the
  server, separately from backups of the data.
* `cd backend && uv run setup key` prints the key's fingerprint. Add `--show`
  to print the key itself.
* Corpus remembers the fingerprint of the key that encrypted the data and does
  not start with another key. See [Troubleshooting](#troubleshooting).
* The application does not encrypt document names, user emails, the audit log
  or search vectors. Keep the Docker data on an encrypted disk. See
  [Encrypting the disk](#encrypting-the-disk).
* Back up regularly and keep the backups on another machine. See
  [Backing up](#backing-up).

## Updating Corpus

1. Get the new version, then build and restart:

   ```sh
   git pull
   deploy/deploy.sh build && deploy/deploy.sh up
   ```

2. If you changed the AI models with `uv run configure`, download them again:

   ```sh
   deploy/deploy.sh models
   ```

## Configuring the chat capacity

The chat shares one AI model between all users. Two settings control how it
is shared:

* **Questions per 10 minutes**: how many questions one user can ask in any
  10 minutes. The default is 20. `0` turns the limit off.
* **Simultaneous answers**: how many answers the model writes at the same
  time. The default is 4. Each one needs extra memory; the setting shows how
  much.

Every user gets one answer at a time, whatever the settings.

1. Change the settings:

   ```sh
   cd backend && uv run configure && cd ..
   ```

2. Apply them:

   ```sh
   deploy/deploy.sh up
   ```

## Backing up

A backup copies the database, the document files and the search index into
`BACKUP-DIR/corpus-YYYYMMDD-HHMMSS/`. Every file in it is encrypted with
`DATA_ENCRYPTION_KEY`, so a stolen backup reveals nothing, and a backup is
useless without that key. The `manifest` file names the key's fingerprint.

1. Run the backup. Replace BACKUP-DIR with the folder for backups; without it,
   the backup goes to `backups/` in the repository. Corpus stops while the
   backup runs, so all parts match, and starts again by itself. Small
   installations take under a minute.

   ```sh
   deploy/deploy.sh backup BACKUP-DIR
   ```

2. Copy the new folder to another machine, for example with rsync or to a NAS.
   A backup on the same disk is lost together with it.

To back up every night at 03:00 and keep 14 days, add this line with
`crontab -e` as a user in the `docker` group:

```text
0 3 * * * /opt/corpus/deploy/deploy.sh backup BACKUP-DIR >> /var/log/corpus-backup.log 2>&1 && find BACKUP-DIR -maxdepth 1 -name 'corpus-*' -mtime +14 -exec rm -rf {} +
```

> [!IMPORTANT]
> After a key rotation, older backups still need the old key. Keep the old
> key, labeled with its fingerprint, until those backups are deleted.

## Encrypting the disk

Corpus encrypts document content itself. Postgres still holds document names,
user emails and the audit log, and Qdrant holds search vectors, from which
parts of the text can be reconstructed. Keep all Docker data on a LUKS
encrypted volume, so a stolen disk or a discarded server reveals nothing.

On a new server, the simplest way is the disk encryption option of the
operating system installer. Ubuntu, Debian and RHEL offer it.

To use a separate data disk instead, follow these steps before the first
`deploy.sh up`. Replace DISK with the disk device, for example `/dev/sdb`.

> [!CAUTION]
> Step 1 erases everything on DISK.

1. Encrypt the disk and choose a long passphrase:

   ```sh
   sudo cryptsetup luksFormat DISK
   sudo cryptsetup open DISK corpus-data
   sudo mkfs.ext4 /dev/mapper/corpus-data
   ```

2. Mount the disk and move the Docker data there:

   ```sh
   sudo mkdir -p /srv/docker
   sudo mount /dev/mapper/corpus-data /srv/docker
   echo '{"data-root": "/srv/docker"}' | sudo tee /etc/docker/daemon.json
   sudo systemctl restart docker
   ```

3. To open the disk at boot, add `corpus-data DISK none luks` to
   `/etc/crypttab` and `/dev/mapper/corpus-data /srv/docker ext4 defaults 0 2`
   to `/etc/fstab`. The boot then waits for the passphrase at the console.

4. Check the result: `lsblk -f` shows `crypto_LUKS` under the disk, and
   `docker info | grep "Docker Root Dir"` shows `/srv/docker`.

Store the LUKS passphrase like `DATA_ENCRYPTION_KEY`: outside the server. An
unattended boot is possible with a key file (`cryptsetup luksAddKey`) or a TPM
(`systemd-cryptenroll --tpm2-device=auto`). A key kept on the same machine
protects only a removed disk, not the running server.

## Rotating the encryption key

Rotate the key when it may have leaked, or when your policy requires it.

1. Generate a new key. The command keeps the old key as
   `DATA_ENCRYPTION_KEY_PREVIOUS` and asks you to confirm that you saved a copy
   of the new one.

   ```sh
   cd backend && uv run setup key rotate && cd ..
   ```

2. Re-encrypt the data. The command stops Corpus, re-encrypts every file, text
   and chat, removes the old key from `.env`, and starts Corpus again.

   ```sh
   deploy/deploy.sh rotate-key
   ```

If `rotate-key` stops halfway, fix the cause and run it again. It continues
where it stopped. Until it finishes, keep the old key: part of the data is
still encrypted with it.

## Restoring a backup

> [!WARNING]
> A restore replaces all current documents, users and chats.

1. Check that `backend/.env` holds the key the backup was made with. Compare
   the fingerprint in the backup's `manifest` file with the output of
   `cd backend && uv run setup key`.

2. Run the restore and type `restore` when asked. Corpus checks every part of
   the backup before it deletes anything.

   ```sh
   deploy/deploy.sh restore BACKUP-DIR/corpus-YYYYMMDD-HHMMSS
   ```

3. On a new server, download the AI models, which backups do not contain:

   ```sh
   deploy/deploy.sh models
   ```

A backup made by an older version of Corpus is migrated when Corpus starts.

## Troubleshooting

**Corpus does not start, and the log says "is not the key the stored data is
encrypted with".** `backend/.env` holds a different `DATA_ENCRYPTION_KEY` than
the one that encrypted the data. Restore the original key from your copy. The
log names both fingerprints; `cd backend && uv run setup key` shows the
fingerprint of the key in `.env`.

**A component is not running.** Open the **System status** page, then read the
logs of that service:

```sh
deploy/deploy.sh logs SERVICE
```

Replace SERVICE with `backend`, `worker`, `ollama`, `postgres`, `qdrant`,
`minio`, `rabbitmq` or `proxy`.

**Ports 80 or 443 are taken.** Set `HTTP_PORT` and `HTTPS_PORT` in
`backend/.env`, then run `deploy/deploy.sh up`.

**Answers are slow.** The AI model runs on the CPU unless you give it a GPU.
In `docker-compose.prod.yml`, uncomment the lines under `ollama` that match
your GPU, then run `deploy/deploy.sh up`.
