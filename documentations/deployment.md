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

8. Open `https://corpus.company.local` and sign in. Click your name at the
   top to open **My account**, and change the password. On the
   **System status** page, check that every component shows **Running**.

With `TLS=internal`, browsers do not trust the certificate until you install
Caddy's root certificate on the users' computers. Print it with:

```sh
docker compose -f docker-compose.prod.yml exec proxy \
  cat /data/caddy/pki/authorities/local/root.crt
```

## Protecting the key and the data

* `backend/.env` holds every secret, including `DATA_ENCRYPTION_KEY`. Without
  that key, documents and chats cannot be read. Store a copy outside the
  server, separately from backups of the data. To keep the key off the server's
  disk, keep it in HashiCorp Vault. See
  [Keeping the key in HashiCorp Vault](#keeping-the-key-in-hashicorp-vault).
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

## Managing chat history

Corpus saves every user's chats, encrypted. Users cannot delete their own
chats. A chat is deleted automatically after 90 days without new messages; to
change that, set `CHAT_RETENTION_DAYS` in `backend/.env` (`0` keeps chats
forever) and run `deploy/deploy.sh up`.

Three permissions give access to other users' chats. Assign them on the
**Roles** page:

| Permission | What it allows |
|---|---|
| View chat history | Read users' chats on the **Chat history** page and from a user's page |
| Clear chat history | Delete chats: all of them, those of the last day, 3 days, week, month or year, or those between two dates. Each chat is deleted whole, with its messages and ratings |
| View answer ratings | Read the answers users rated good or bad, with their questions |

These permissions reach only users who hold no permission the reviewer lacks:
someone without access to secret documents cannot read or delete the chats of
someone who has it. Every chat a reviewer opens and every deletion is recorded
in the **Audit log**.

> Deleted chats cannot be restored, except from a backup.

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

## Changing the embedding model

The embedding model turns documents and questions into vectors for search.
Vectors of two models cannot be compared, so another model means every
document is embedded again. Corpus does not start if `EMBEDDING_MODEL` in
`backend/.env` is not the model the documents are indexed with.

1. Choose a model from the table in `uv run configure` (embedding model step)
   or from `EMBEDDING_MODELS` in `backend/src/settings.py`.
2. Switch to it. This downloads the model (the server needs the internet for
   this step), rebuilds the search index and starts Corpus again:

   ```sh
   deploy/deploy.sh switch-model MODEL
   ```

While the documents are embedded again, the **Documents** page shows their
progress, and search finds each document once it is done. Documents, their
files and chats are not changed. A large library can take hours on a server
without a GPU.

If the command stops midway, run it again: it continues where it stopped.

To rebuild the index with the same model, for example after changing the
chunk size with `uv run configure`, run the command with the current model.

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

3. With the key in Vault, remove the old key from Vault yourself; the command
   asks for a Vault token that may write the secret:

   ```sh
   cd backend && uv run setup key finish && cd ..
   ```

If `rotate-key` stops halfway, fix the cause and run it again. It continues
where it stopped. Until it finishes, keep the old key: part of the data is
still encrypted with it.

## Keeping the key in HashiCorp Vault

By default `DATA_ENCRYPTION_KEY` is in `backend/.env`, so a copy of the
server's disk includes it. With HashiCorp Vault, `.env` holds only the
credentials of a Vault AppRole. Corpus reads the key from Vault when it starts
and keeps it in memory only. A copy of the disk is then no use outside the
company network, and you can revoke the AppRole, bind it to the server's
address and see every read in Vault's audit log.

You need a Vault server with a KV version 2 secrets engine (mounted at
`secret` by default), reachable from the Corpus server. A hardware security
module (HSM) protects Vault's own master key; Corpus needs no HSM setup of its
own.

1. In Vault, create a read-only policy and an AppRole for Corpus. Replace
   SERVER-IP with the address of the Corpus server:

   ```sh
   vault auth enable approle
   vault policy write corpus-read - <<'EOF'
   path "secret/data/corpus" { capabilities = ["read"] }
   EOF
   vault write auth/approle/role/corpus token_policies=corpus-read \
     secret_id_bound_cidrs=SERVER-IP/32 token_bound_cidrs=SERVER-IP/32
   vault read -field=role_id auth/approle/role/corpus/role-id
   vault write -f -field=secret_id auth/approle/role/corpus/secret-id
   ```

2. Run the key storage step and choose **HashiCorp Vault**:

   ```sh
   cd backend && uv run configure && cd ..
   ```

   It asks for the Vault address, the role_id and secret_id from step 1, the
   mount and path (`secret`, `corpus`), and the CA file of Vault's certificate
   if a company CA signed it. It then asks once for a Vault token that may
   write `secret/data/corpus`, writes the key there, checks that the AppRole
   can read it, and removes the key from `.env`. The token is not saved.

3. Apply it:

   ```sh
   deploy/deploy.sh up
   ```

   The containers have no route out of the server, so `deploy.sh` starts a
   `vault-tunnel` container that forwards only to the Vault address. TLS runs
   from Corpus to Vault and is checked against Vault's name.

To move the key back into `.env`, run `uv run configure` and choose the `.env`
file. The key stays in Vault until you delete it there.

If Vault cannot be reached when Corpus starts, the backend and the worker do
not start; `deploy/deploy.sh logs backend` shows why.

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
