"""Lines that many documents share: disclaimers, confidentiality notices,
legal footers. Repeated across a hundred e-mails, they make unrelated
documents look alike to search, so they are left out of the vectors.
Search results and answers still show them (embedding_text.py).

Each document's long lines are stored as keyed digests (DocumentLine). A
line counts once at least MIN_DOCUMENTS documents hold it, so only documents
processed after that point leave it out; reprocessing updates the others.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from encryption import keyed_digest
from models.document_line import DocumentLine
from services.documents.text_cleanup import normalized_lines

# Shorter lines are often headings ("Remote work") that documents share for
# a reason; boilerplate sentences are long.
MIN_LENGTH = 40
MIN_DOCUMENTS = 5


async def shared_lines(session: AsyncSession, document_id: int, text: str) -> frozenset[str]:
    """Records the document's long lines and returns those held by at least
    MIN_DOCUMENTS documents, this one included."""
    lines = {keyed_digest(line.casefold().encode()): line for line in normalized_lines(text) if len(line) >= MIN_LENGTH}
    await session.execute(delete(DocumentLine).where(DocumentLine.document_id == document_id))
    if not lines:
        return frozenset()
    session.add_all(DocumentLine(document_id=document_id, digest=digest) for digest in lines)
    await session.flush()
    shared = await session.scalars(
        select(DocumentLine.digest)
        .where(DocumentLine.digest.in_(list(lines)))
        .group_by(DocumentLine.digest)
        .having(func.count() >= MIN_DOCUMENTS)
    )
    return frozenset(lines[digest] for digest in shared)
