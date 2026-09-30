"""Encrypts or decrypts a backup stream with DATA_ENCRYPTION_KEY.

    ... | python -m maintenance.backup_crypt encrypt > part.enc
    python -m maintenance.backup_crypt decrypt < part.enc | ...

Used by deploy/deploy.sh backup/restore, so dumps never touch the disk in
plain form. `fingerprint FILE` prints which key a backup needs.
"""

import sys

from encryption import decrypt_stream, encrypt_stream, stream_fingerprint
from exceptions import AppError


def main(args: list[str]) -> None:
    try:
        if args == ["encrypt"]:
            encrypt_stream(sys.stdin.buffer, sys.stdout.buffer)
        elif args == ["decrypt"]:
            decrypt_stream(sys.stdin.buffer, sys.stdout.buffer)
        elif args == ["fingerprint"]:
            print(stream_fingerprint(sys.stdin.buffer.read(64)))
        else:
            raise SystemExit(__doc__)
        sys.stdout.flush()
    except AppError as exc:
        raise SystemExit(exc.message) from None


if __name__ == "__main__":
    main(sys.argv[1:])
