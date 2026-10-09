from setup.app import run
from setup.steps.chat import ChatStep
from setup.steps.chunking import ChunkingStep
from setup.steps.key_store import KeyStoreStep
from setup.steps.language import LanguageStep
from setup.steps.llm import LlmStep


def main() -> None:
    try:
        run(
            [LanguageStep(), LlmStep(), ChatStep(), ChunkingStep(), KeyStoreStep()],
            "Configure complete.",
            footer=(
                "Restart to apply: production `deploy/deploy.sh up` (after a language "
                "change `deploy/deploy.sh build` first: the interface is built with its "
                "languages); development: restart the backend, the worker and the "
                "frontend dev server (and Ollama for simultaneous "
                "answers: docker compose --env-file backend/.env -f docker-compose.local.yml up -d ollama). "
                "The new chunk size applies to documents uploaded afterwards; re-chunk the "
                "others on the System page, or keep them as they are."
            ),
        )
    except KeyboardInterrupt:
        raise SystemExit(130) from None
