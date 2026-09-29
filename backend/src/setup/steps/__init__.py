"""Setup steps. To add one: write a module with `title` + `run(console)`, then append it here."""

from .embedding import EmbeddingStep
from .language import LanguageStep
from .llm import LlmStep
from .chunking import ChunkingStep
from .credentials import SecretsStep
from .storage import StorageStep

SETUP_STEPS = [SecretsStep(), StorageStep(), LanguageStep(), LlmStep(), EmbeddingStep(), ChunkingStep()]
