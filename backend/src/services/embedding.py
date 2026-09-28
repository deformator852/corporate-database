from sentence_transformers import SentenceTransformer

from settings import EmbeddingSpec, embedding_model


class EmbeddingModel:
    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None
        self._spec: EmbeddingSpec | None = None

    def _loaded(self) -> tuple[SentenceTransformer, EmbeddingSpec]:
        if self._model is None or self._spec is None:
            self._spec = embedding_model()
            self._model = SentenceTransformer(self._spec.hf_id)
        return self._model, self._spec

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        model, spec = self._loaded()
        prefixed = [f"{spec.passage_prefix}{text}" for text in texts]
        vectors = model.encode(
            prefixed,
            normalize_embeddings=True,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        model, spec = self._loaded()
        vectors = model.encode(
            [f"{spec.query_prefix}{text}"],
            normalize_embeddings=True,
        )
        return vectors[0].tolist()


_embedder: EmbeddingModel | None = None


def get_embedding_model() -> EmbeddingModel:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingModel()
    return _embedder
