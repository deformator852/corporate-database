"""Setup steps. To add one: write a module with `title` + `run(console)`, then append it here."""

from .embedding import EmbeddingStep
from .llm import LlmStep

SETUP_STEPS = [LlmStep(), EmbeddingStep()]
