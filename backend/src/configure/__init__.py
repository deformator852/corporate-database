from setup.app import run
from setup.steps.llm import LlmStep


def main() -> None:
    try:
        run(
            [LlmStep()],
            "Configure complete.",
            footer="The next chat message will use the new model.",
        )
    except KeyboardInterrupt:
        raise SystemExit(130) from None
