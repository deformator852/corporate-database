"""Downloads the configured embedding model into HF_HOME.

Run by the `models` job in docker-compose.prod.yml, the only container with
internet access. The app itself runs offline (HF_HUB_OFFLINE=1).

    python -m maintenance.download_models           download (or update) it
    python -m maintenance.download_models --check   exit 1 if it is not on disk;
                                                    no internet needed
"""

import sys

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from settings import embedding_model


def main(args: list[str]) -> None:
    spec = embedding_model()
    if args == ["--check"]:
        try:
            snapshot_download(spec.hf_id, local_files_only=True)
        except LocalEntryNotFoundError:
            raise SystemExit(f"Embedding model {spec.hf_id} is not downloaded.") from None
        print(f"Embedding model {spec.hf_id} is downloaded.")
        return
    path = snapshot_download(spec.hf_id)
    print(f"Embedding model {spec.hf_id} ready in {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
