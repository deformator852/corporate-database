# Deploying Corpus on a company server

This guide shows you how to install Corpus on a Linux server in your company
network and keep it running: updates, backups, disk encryption and key
rotation.

## About the deployment

Corpus runs entirely inside the company network. After installation, no
container can reach the internet. Only the model download job reaches it, and
only when you run it. If you connect HashiCorp Vault, single sign-on or S3
storage, a tunnel container forwards to that one address and nowhere else.

All settings and secrets live in one file, `backend/.env`. Documents and chats
are encrypted with `DATA_ENCRYPTION_KEY` from that file, so the data cannot be
read without the key. Uploaded files stay on the server, in a Docker volume,
unless you keep them in the company's S3 storage.

## Prerequisites

* A Linux server with Docker and Docker Compose v2
* `git` and [uv](https://docs.astral.sh/uv/) on the server, to run the setup
  command
* 16 GB of RAM or more for the default 8B model, about 80 GB of disk, and an
  x86-64 CPU with AVX2. The AI model uses most of the memory. A GPU is
  optional. Larger models need more: see
  [System requirements](../README.md#system-requirements).
* A host name that users will open, for example `corpus.company.local`
* Either a company TLS certificate, or Caddy's internal certificate
  (`TLS=internal`)
* Internet access during installation only, to download the AI models

## Installing Corpus

1. Get the code and run the setup. It generates the secrets and asks where
   to keep the document files, the system language, the AI models and the
   chat limits. Files stay on the server unless you choose the company's S3
   storage; see
   [Keeping document files in S3 storage](#keeping-document-files-in-s3-storage).

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

5. Start Corpus. Database migrations run automatically. The first start
   downloads the AI models named in `backend/.env` (the embedding model and
   the LLM, several GB, side by side). This is the only step that needs the
   internet; later starts find the models on disk and skip it.

   ```sh
   deploy/deploy.sh up
   ```

   The Corpus containers themselves never get internet access: only the
   download jobs do, and only while they run.

6. Create the first administrator. The command prints the password once.

   ```sh
   deploy/deploy.sh admin ADMIN-EMAIL
   ```

7. Open `https://corpus.company.local` and sign in. Click your name at the
   top to open **My account**, and change the password. On the
   **System status** page, check that every component shows **Running**.

With `TLS=internal`, browsers do not trust the certificate until you install
Caddy's root certificate on the users' computers. Print it with:

```sh
docker compose -f docker-compose.prod.yml exec proxy \
  cat /data/caddy/pki/authorities/local/root.crt
```

## Giving people access

After installation, only the administrator from step 6 can sign in, and only
the **Admin** role exists. It always has every permission and cannot be
deleted.

1. On the **Roles** page, create a role for each group of people, for example
   "Employees" and "Legal", and select its permissions. See the table below.
2. On the **Users** page, create an account for each person: name, email, a
   first password and roles. Give the person the password; they change it
   under **My account**. With single sign-on, accounts are created at the
   first sign-in instead; assign their roles on the **Users** page, or from
   the provider's groups. See
   [Signing in with the company account](#signing-in-with-the-company-account-sso).

Every document has an access level. A user reads the documents of the levels
their roles allow, and the assistant answers only from those:

| Permission | Document levels the user reads |
|---|---|
| List documents | Standard |
| Restricted documents | Standard, restricted |
| Confidential documents | Standard, restricted, confidential |
| Secret documents | All |

A user with none of these can still use the chat, but the assistant answers
that no document matches.

The other permissions:

| Area | Permissions |
|---|---|
| Documents | Create document (upload, process a failed one again), Update document (rename, change the level), Delete document |
| Users | List users, View user (profile and history of actions), Create user, Update user, Disable user, Delete user |
| Roles | List roles, Create role, Update role, Delete role, List permissions |
| Chats | View chat history, Delete chats, View answer ratings. See [Managing chat history](#managing-chat-history). |
| Audit | View audit log |
| System | View system status, View error log, Update documents for search |

Nobody can give permissions they do not have, or change a user or role with
more access than their own. Disable a user who leaves the company: they can
no longer sign in, and their documents and history stay.

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

2. If you changed the AI models with `uv run configure`, `deploy/deploy.sh up`
   downloads the new ones before it starts Corpus. To fetch newer versions
   of models already on disk, run `deploy/deploy.sh models`.

## Signing in with the company account (SSO)

Users can sign in with their company account instead of a Corpus password:
Microsoft Entra ID, ADFS, Keycloak, Okta or another provider that supports
OpenID Connect. SSO is off until you turn it on.

1. At the provider, register Corpus as a confidential web application with
   this redirect URI, where SITE is the address users open:

   ```text
   https://SITE/api/v1/auth/sso/callback
   ```

   Allow the scopes `openid email profile`. To give roles from groups, add
   the groups claim to the ID token.
2. In `backend/`, run `uv run configure`, answer yes to **Use single
   sign-on?** and enter the issuer address, the client ID and the client
   secret. The setup asks:
   * **Button name**: the button says "Sign in with NAME".
   * **Group to role map**: `GROUP=ROLE_KEY` pairs separated by `;`, for
     example `Corpus Admins=admin;Legal=legal`. A mapped role follows the
     groups at every sign-in. Leave it empty to assign roles on the
     **Users** page.
   * **Link existing Corpus accounts by email**: someone who already has a
     Corpus account keeps it at their first SSO sign-in, with its roles and
     chats. Answer yes only when your IT department assigns the emails at
     the provider; where people choose their own, one could take over
     another's account. With no, such a sign-in is refused.
3. Run `deploy/deploy.sh up`.

While SSO is on, only users with the Admin role sign in with a Corpus
password, through **Administrator sign-in with a password** under the SSO
button; everyone else signs in with the company account. So administrators
can still get in when the provider is down. To let everyone use passwords
again, run `uv run configure`, answer no to **Use single sign-on?** and run
`deploy/deploy.sh up`.

A user's first SSO sign-in creates their Corpus account. Corpus recognizes
the person by the provider's own ID, not by email.

If a Corpus account with the same email already exists and linking by email
is off, the sign-in is refused with "An account with your email already
exists". To let the person in, delete that account or change its email on the
**Users** page; their next SSO sign-in creates a new account. The chats of
the old account do not move to the new one. Disable a user on the
**Users** page to stop them signing in; disabling them at the provider stops
new sign-ins too.

The backend reaches the provider through `sso-tunnel`, which forwards to the
issuer's host only. The provider's token and key addresses must be on that
host, as they are for the providers above. If a company CA signed the
provider's certificate, give its file when the setup asks for the CA.

To turn SSO off, run `uv run configure`, answer no, and run
`deploy/deploy.sh up`. Users created by SSO have no password: set one for
them on the **Users** page.

## Keeping document files in S3 storage

By default, Corpus keeps uploaded files on the server, in the
`documents_data` Docker volume. A company with its own S3-compatible object
storage, such as Ceph, NetApp StorageGRID, Dell ECS or AWS S3, can keep them
there instead, under its replication, versioning and retention rules. Corpus
encrypts each file before it leaves the server: the storage holds only
encrypted objects named `documents/UUID`, without document names.

When you switch with documents already uploaded, the step offers to move
their files; see
[Moving files between the server and S3](#moving-files-between-the-server-and-s3).

You need:

* A bucket for Corpus, for example `corpus-documents`.
* An access key and a secret key of an account allowed only to read, write
  and delete objects in that bucket. For example, as an S3 policy:

  ```json
  {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": ["arn:aws:s3:::corpus-documents/*"]}]}
  ```

* The storage's address, `https://HOST` or `https://HOST:PORT` without a
  path, reachable from the Corpus server. For Amazon S3, use the address of
  the bucket's region, for example `https://s3.eu-central-1.amazonaws.com`,
  and enter that region (`eu-central-1`) when the step asks.

1. Run the storage step:

   ```sh
   cd backend && uv run configure && cd ..
   ```

   At **Document storage**, answer yes to **Keep the files in the company's
   S3 storage?** and enter the address, the bucket, the keys and the region.
   If a company CA signed the storage's certificate, give its file when the
   step asks for the CA. The step writes, reads back and deletes a test
   object. If that fails, it shows the storage's reason and saves the
   settings only if you confirm.

2. Apply it:

   ```sh
   deploy/deploy.sh up
   ```

   The containers have no route out of the server, so `deploy.sh` starts an
   `s3-tunnel` container that forwards only to the storage's address. TLS
   runs from Corpus to the storage and is checked against the storage's
   name.

`deploy/deploy.sh backup` then copies the database and the search index, not
the files. Back the bucket up with the storage's versioning or replication,
and restore the bucket and a Corpus backup from the same point in time.

The **System status** page shows the bucket under **File storage**, or the
storage's reason when it refuses Corpus.

### Moving files between the server and S3

When you change the storage at **Document storage** in `uv run configure`
and documents exist, the step asks **Move the document files to the new
storage?**

* **Yes.** The step stops the backend and the worker, copies every
  document's file to the new storage, reads each copy back, saves the new
  settings and starts Corpus again. The files are encrypted already and
  keep their names, so nothing is decrypted on the way. The old copies stay:
  delete them yourself once Corpus works with the new storage. If the copy
  stops midway, nothing is saved; run the step again and it continues where
  it stopped.
* **No.** Only the settings change. The documents stay searchable, but the
  **Documents** page marks them **The file is not in the storage**, and the
  **System status** page counts them. They cannot be opened or processed
  again until their files are in the new storage. Corpus checks every file
  when it starts.

The step moves files between the server and one S3 storage. To move them
between two S3 storages at different addresses, copy them with the storages'
own tools, for example the AWS command-line tool. Replace BUCKET with the
bucket and HOST with the storage's address:

```sh
aws s3 sync s3://OLD-BUCKET/documents s3://BUCKET/documents --endpoint-url https://HOST
```

To copy the files back to the server by hand, stop Corpus, copy them into the
volume and give them to the Corpus user (uid 10001), then answer no at
**Document storage** and to the move, and run `deploy/deploy.sh up`:

```sh
files=$(docker volume inspect corpus_documents_data --format '{{.Mountpoint}}')
sudo -E aws s3 sync s3://BUCKET/documents "$files/documents" --endpoint-url https://HOST
sudo chown -R 10001:10001 "$files"
```

## Using several languages

Corpus can serve documents and users in several languages: English, Spanish
and French. Each user picks the interface language in the header (the
**Language** button), and reads the interface, error messages, notices and
the assistant's answers in it. The choice is saved on the account.

1. In `backend/`, run `uv run configure`. At the **System language** step,
   answer yes to **Use more than one language?**, enter the numbers of the
   languages (for example `1,2,3`), then choose the default language. Users
   who have not chosen see the default one.
2. Search must match a question with documents in any of these languages, so
   the embedding model must be multilingual: `multilingual-e5-small`,
   `multilingual-e5-base` or `bge-m3`. If the current model is for one
   language (`bge-*-en`, `solon-*`), switch it as described in
   [Changing the embedding model](#changing-the-embedding-model).
3. Rebuild and restart. The interface is built with its languages, so a
   change needs a new build:

   ```sh
   deploy/deploy.sh build && deploy/deploy.sh up
   ```

To go back to one language, run `uv run configure` again, answer no, and
rebuild. The header then shows no language button.

## Re-chunking documents after a chunk size change

A new chunk size or overlap (`uv run configure`) applies to documents
uploaded afterwards. Documents processed before keep their chunks and keep
working. To cut them again with the new size, open **System**: it shows how
many documents use another size. Select **Update documents** (permission
**Update documents for search**). The worker cuts them one at a time, between
new uploads, from the text saved at processing time. They stay searchable meanwhile, and
the progress shows in the banner. The action is recorded in the audit log.

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

## Viewing errors

Corpus keeps the warnings and errors of the backend and the worker, with
their tracebacks, encrypted in the database. To see them, open **Error log**
in the sidebar; you need the **View error log** permission, which the Admin
role has. Filter by level (warning, error, critical) and by type:

| Type | What it means |
|---|---|
| Unhandled (bug) | An error nothing in Corpus caught. Report these. |
| Handled | Corpus noticed the problem and logged it, for example a document it could not process |
| System | A component Corpus uses failed, for example the database or the AI model. Only its errors are kept, not its warnings. |

Each part of the code keeps at most 30 entries a minute, so a failing
component cannot fill the database.

Entries are deleted after 30 days. To change that, set
`ERROR_LOG_RETENTION_DAYS` in `backend/.env` (`0` keeps them forever) and run
`deploy/deploy.sh up`. The containers' console logs (`docker compose logs`)
still show everything, including messages below warning level.

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
| Delete chats | Delete one chat, from its row or its page, or all chats: those of the last day, 3 days, week, month or year, or those between two dates. Each chat is deleted whole, with its messages and ratings |
| View answer ratings | Read the answers users rated good or bad, with their questions, and remove a rating once it is dealt with. With **View chat history** too, open the chat of an answer |

An answer quotes the documents its author can read, so these permissions reach
only some users:

* **View chat history** and **Delete chats** reach users who hold no
  permission the reviewer lacks.
* **View answer ratings** shows the answers of users who can read no document
  the reviewer cannot. Someone without access to secret documents never sees
  the rated answers of someone who has it.

Every chat a reviewer opens, every deletion and every removed rating is
recorded in the **Audit log**.

> Deleted chats cannot be restored, except from a backup.

## Backing up

A backup goes into `BACKUP-DIR/corpus-YYYYMMDD-HHMMSS/`:

| File | What it holds |
|---|---|
| `postgres.dump.enc` | The database: users, roles, document records, chats, audit log |
| `documents_data.tar.gz.enc` | The document files. Only when they are on the server: with S3 storage they stay in the bucket, which the storage backs up |
| `qdrant_data.tar.gz.enc` | The search index |
| `manifest` | The date, the version and the fingerprint of the key |

Every part is encrypted with `DATA_ENCRYPTION_KEY`, so a stolen backup reveals
nothing, and a backup is useless without that key.

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
document is embedded again. While `EMBEDDING_MODEL` in `backend/.env` is not
the model the documents are indexed with, Corpus runs but search is off: the
chat answers that the search index must be rebuilt, and new uploads wait in
the queue.

You can switch with one command, or edit `backend/.env` and rebuild the index
from the **System** page.

### Switching with the command

1. Choose a model from the table in [Where the models come from](#where-the-models-come-from).
   Running the command without a model also lists them:

   ```sh
   cd backend && uv run switch-embedding-model
   ```

2. Switch to it. The command downloads the model (the server needs the
   internet for this step), stops the backend and the worker, rebuilds the
   search index, writes `EMBEDDING_MODEL` to `backend/.env` and starts the
   backend and the worker again:

   ```sh
   cd backend && uv run switch-embedding-model MODEL
   ```

While the documents are embedded again, the **Documents** page shows their
progress, and search finds each document once it is done. Documents, their
files and chats are not changed. A large library can take hours on a server
without a GPU.

If the command stops midway, run it again: it continues where it stopped.

### Switching from the System page

1. Set `EMBEDDING_MODEL` in `backend/.env` to a model from the table in
   [Where the models come from](#where-the-models-come-from).
2. Restart Corpus. It downloads the new model when it is missing, so the
   server needs the internet for this step:

   ```sh
   deploy/deploy.sh up
   ```

3. On the **System** page, select **Rebuild search index**, then
   **Rebuild**. You need the **Update documents for search** permission.

The documents are embedded again in the background, as with the command.

To rebuild the index with the same model, for example after changing the
chunk size with `uv run configure`, run the command with the current model.

### Where the models come from

The embedding models are open models published on the Hugging Face Hub
(huggingface.co). Corpus knows the ones below; `EMBEDDING_MODEL` takes the
name in the first column.

| Name | Hugging Face model | Documents in | Vector size |
|---|---|---|---|
| `multilingual-e5-small` | `intfloat/multilingual-e5-small` | Many languages | 384 |
| `multilingual-e5-base` | `intfloat/multilingual-e5-base` | Many languages | 768 |
| `multilingual-e5-large` | `intfloat/multilingual-e5-large` | Many languages | 1024 |
| `bge-m3` | `BAAI/bge-m3` | Many languages | 1024 |
| `bge-small-en` | `BAAI/bge-small-en-v1.5` | English | 384 |
| `bge-base-en` | `BAAI/bge-base-en-v1.5` | English | 768 |
| `bge-large-en` | `BAAI/bge-large-en-v1.5` | English | 1024 |
| `solon-base` | `OrdalieTech/Solon-embeddings-base-0.1` | French | 768 |
| `solon-large` | `OrdalieTech/Solon-embeddings-large-0.1` | French | 1024 |

Larger models usually find more relevant documents and need more memory and
time to embed. `multilingual-e5-large` has no calibrated relevance threshold
yet, so search with it keeps every hit, relevant or not.

Where the files go:

* **Production.** Only the `models` job downloads them, into the `hf_models`
  Docker volume (`/models/hf` in the containers). It is the one container with
  internet access, and runs only when you ask: `deploy/deploy.sh models`, or
  `uv run switch-embedding-model`. The backend and the worker read the model
  from that volume and never go online (`HF_HUB_OFFLINE=1`).
* **Development.** The model is downloaded on first use into the Hugging Face
  cache of your user, `~/.cache/huggingface` (or `HF_HOME` if you set it).

A server without internet access can copy the volume's contents from another
machine that downloaded the same model.

## Rotating the encryption key

Rotate the key when it may have leaked, or when your policy requires it.

1. Generate a new key. The command keeps the old key as
   `DATA_ENCRYPTION_KEY_PREVIOUS` and asks you to confirm that you saved a copy
   of the new one.

   ```sh
   cd backend && uv run setup key rotate && cd ..
   ```

2. Re-encrypt the data. The command stops Corpus, re-encrypts every file,
   document text, chat and error log entry, and the search index text,
   removes the old key from `.env`, and starts Corpus again.

   ```sh
   deploy/deploy.sh rotate-key
   ```

3. With the key in Vault, remove the old key from Vault. The command asks for
   a Vault token that may write the secret:

   ```sh
   cd backend && uv run setup key finish && cd ..
   ```

If `rotate-key` stops halfway, fix the cause and run it again. It continues
where it stopped. Until it finishes, keep the old key: part of the data is
still encrypted with it. With S3 storage, the files in the bucket are
re-encrypted too; if the bucket keeps versions, the older versions still need
the old key, like older backups.

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

With S3 storage the backup holds no files: Corpus reads them from the bucket
as it is now. Files of documents uploaded after the backup stay there unused.
Files of documents deleted after the backup are gone, unless the bucket's
versioning brings them back; restore the bucket to the backup's time if it
can.

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
`rabbitmq` or `proxy`, or with `vault-tunnel`, `sso-tunnel` or `s3-tunnel`
when you use Vault, single sign-on or S3 storage.

**Single sign-on fails.** The sign-in page names the problem, and the
**Error log** page shows the cause as a **Handled** warning:

| Message on the sign-in page | Usual cause |
|---|---|
| The sign-in service cannot be reached | The provider is down, or its certificate is not signed by a public CA or by the CA file you gave. Check `deploy/deploy.sh logs sso-tunnel` too. |
| Single sign-on failed | The issuer address does not match the provider's discovery document, or the provider's token and key addresses are on another host than the issuer. |
| The sign-in could not be completed | A wrong client ID or client secret (the log says `invalid_client`), or a sign-in left open too long. |
| An account with your email already exists | See [Signing in with the company account](#signing-in-with-the-company-account-sso). |

**Ports 80 or 443 are taken.** Set `HTTP_PORT` and `HTTPS_PORT` in
`backend/.env`, then run `deploy/deploy.sh up`.

**`deploy.sh` says an address points to this server's loopback address.**
Vault, the SSO provider and the S3 storage are reached through tunnel
containers, and inside a container `localhost` or `127.0.0.1` is the
container itself. If the service runs on the Corpus server, make it listen on
the server's network address and enter that address or the server's host
name instead, with `cd backend && uv run configure`.

**Answers are slow.** The AI model runs on the CPU unless you give it a GPU.
In `docker-compose.prod.yml`, uncomment the lines under `ollama` that match
your GPU, then run `deploy/deploy.sh up`. For an Intel or AMD integrated GPU
these are `OLLAMA_IGPU_ENABLE`, `devices` and `group_add`; in `group_add`, put
the ids that `getent group video render` prints on the server. Check that
Ollama found the GPU: `deploy/deploy.sh logs ollama` shows a line
`inference compute` without `library=cpu`.
