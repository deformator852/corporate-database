"""Downloads the configured embedding model into HF_HOME.

Run by the `models` job in docker-compose.prod.yml, the only container with
internet access. The app itself runs offline (HF_HUB_OFFLINE=1).
"""

from huggingface_hub import snapshot_download

from settings import embedding_model


def main() -> None:
    spec = embedding_model()
    path = snapshot_download(spec.hf_id)
    print(f"Embedding model {spec.hf_id} ready in {path}")


if __name__ == "__main__":
    main()
