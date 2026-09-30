from setup.app import run
from setup.steps.chat import ChatStep
from setup.steps.chunking import ChunkingStep
from setup.steps.llm import LlmStep


def main() -> None:
    try:
        run(
            [LlmStep(), ChatStep(), ChunkingStep()],
            "Configure complete.",
            footer=(
                "Restart to apply: production `deploy/deploy.sh up`; development: "
                "restart the backend and the worker (and Ollama for simultaneous "
                "answers: docker compose --env-file backend/.env -f docker-compose.local.yml up -d ollama). "
                "The new chunk size applies to documents uploaded afterwards."
            ),
        )
    except KeyboardInterrupt:
        raise SystemExit(130) from None
