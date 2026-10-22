from setup.app import run
from setup.steps.chat import ChatStep
from setup.steps.chunking import ChunkingStep
from setup.steps.key_store import KeyStoreStep
from setup.steps.language import LanguageStep
from setup.steps.llm import LlmStep
from setup.steps.sso import SsoStep
from setup.steps.storage import StorageStep


def main() -> None:
    try:
        run(
            [LanguageStep(), LlmStep(), ChatStep(), ChunkingStep(), SsoStep(), KeyStoreStep(), StorageStep()],
            "Configure complete.",
            footer=(
                "Restart to apply: production `deploy/deploy.sh up` (after a language "
                "change `deploy/deploy.sh build` first: the interface is built with its "
                "languages); development: restart the backend, the worker and the "
                "frontend dev server (and Ollama for simultaneous "
                "answers: docker compose --env-file backend/.env -f docker-compose.local.yml up -d ollama). "
                "The new chunk size applies to documents uploaded afterwards; update the "
                "others on the System page (Update documents), or keep them as they are."
            ),
        )
    except KeyboardInterrupt:
        print()  # end the line ^C left open
        raise SystemExit(130) from None
