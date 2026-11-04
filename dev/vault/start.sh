#!/bin/sh
# Local test Vault for Archfold's key storage (docker-compose.local.yml, profile
# "vault"). A real server with its data on a volume, not dev mode: dev mode
# keeps everything in memory, and an encryption key moved there would be gone
# at the next restart. Initialised on the first start (one unseal key, kept on
# the volume), unsealed on every start. Test values only.
set -eu
DATA=/vault/file
cat > /tmp/vault.hcl <<'HCL'
storage "file" { path = "/vault/file" }
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}
disable_mlock = true
ui = true
HCL

vault server -config=/tmp/vault.hcl &
server=$!
export VAULT_ADDR=http://127.0.0.1:8200

# "vault status" exits 0 unsealed, 2 sealed, 1 unreachable.
until status=$(vault status >/dev/null 2>&1; echo $?) && [ "$status" != 1 ]; do sleep 1; done

if [ ! -f "$DATA/init.json" ]; then
  vault operator init -key-shares=1 -key-threshold=1 -format=json > "$DATA/init.json"
  chmod 600 "$DATA/init.json"
fi
unseal_key=$(grep -A1 '"unseal_keys_b64"' "$DATA/init.json" | tail -1 | tr -d ' ",')
VAULT_TOKEN=$(grep '"root_token"' "$DATA/init.json" | cut -d'"' -f4)
export VAULT_TOKEN
vault operator unseal "$unseal_key" >/dev/null

# What a company's Vault administrator does for Archfold (deployment.md).
vault secrets list | grep -q '^secret/' || vault secrets enable -path=secret kv-v2 >/dev/null
vault auth list | grep -q '^approle/' || vault auth enable approle >/dev/null
vault policy write archfold-read - >/dev/null <<'HCL'
path "secret/data/archfold" { capabilities = ["read"] }
HCL
vault policy write archfold-write - >/dev/null <<'HCL'
path "secret/data/archfold" { capabilities = ["create", "update", "read"] }
HCL
vault write auth/approle/role/archfold token_policies=archfold-read >/dev/null
vault write auth/approle/role/archfold/role-id role_id=archfold-local-role-id >/dev/null
# Fixed test values; "already exists" on later starts is fine.
vault write auth/approle/role/archfold/custom-secret-id secret_id=archfold-local-secret-id >/dev/null 2>&1 || true
vault token create -id=archfold-local-admin-token -policy=archfold-write -orphan -period=768h >/dev/null 2>&1 || true
echo "Test Vault ready on http://localhost:8200"

wait "$server"
