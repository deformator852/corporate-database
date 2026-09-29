from setup.app import run
from setup.steps.chunking import ChunkingStep
from setup.steps.llm import LlmStep


def main() -> None:
    try:
        run(
            [LlmStep(), ChunkingStep()],
            "Configure complete.",
            footer="The next chat message uses the new model; new uploads use the new chunk size.",
        )
    except KeyboardInterrupt:
        raise SystemExit(130) from None
