from sentence_transformers import SentenceTransformer

from settings import embedding_model_id


class EmbeddingModel:
    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    def _loaded(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(embedding_model_id())
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {text}" for text in texts]
        vectors = self._loaded().encode(
            prefixed,
            normalize_embeddings=True,
        )
        return [vector.tolist() for vector in vectors]
