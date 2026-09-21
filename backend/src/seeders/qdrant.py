from services.rag import Rag


async def seed_qdrant() -> None:
    rag = Rag()
    try:
        await rag.ensure_collection()
    finally:
        await rag.client.close()
