from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextDocument:
    """A document as the assistant reads it: from `document_texts`, or
    excerpts of it when it is too long for the context (services/chat/excerpts.py)."""

    document_id: int
    name: str
    filename: str
    classification: str
    text: str

    @property
    def label(self) -> str:
        """How the prompt and the sources line name it."""
        return (self.filename or self.name).strip() or "Document"
