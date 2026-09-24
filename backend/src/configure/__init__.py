from setup.app import run
from setup.steps.llm import LlmStep


def main() -> None:
    try:
        run([LlmStep()], "Configure complete.")
    except KeyboardInterrupt:
        raise SystemExit(130) from None
