"""Setup steps. To add one: write a module with `title` + `run(console)`, then append it here."""

from .chat import ChatStep
from .chunking import ChunkingStep
from .credentials import SecretsStep
from .embedding import EmbeddingStep
from .key_store import KeyStoreStep
from .language import LanguageStep
from .llm import LlmStep
from .sso import SsoStep
from .storage import StorageStep

SETUP_STEPS = [
    SecretsStep(),
    KeyStoreStep(installing=True),
    StorageStep(installing=True),
    LanguageStep(),
    LlmStep(),
    ChatStep(),
    EmbeddingStep(),
    ChunkingStep(),
    SsoStep(),
]
