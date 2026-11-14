from collections.abc import Callable, Sequence

from app.services.ai.exceptions import EmbeddingError

# document_chunks.embedding is Vector(384). This model matches that column.
# fastembed runs the ONNX build of sentence-transformers/all-MiniLM-L6-v2 so the API
# does not install PyTorch. Do not change the dimension without a migration.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

Embedder = Callable[[Sequence[str]], list[list[float]]]


class EmbeddingService:
    def __init__(self, embedder: Embedder | None = None, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._embedder = embedder or _fastembed
        self.dimensions = dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts]
        if any(not text for text in cleaned):
            raise EmbeddingError("Embedding input cannot be empty.")
        if not cleaned:
            return []
        vectors = self._embedder(cleaned)
        if len(vectors) != len(cleaned):
            raise EmbeddingError("The embedding model returned a different number of vectors than texts.")
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"Expected {self.dimensions} dimensions to match the existing vector column, got {len(vector)}."
                )
        return vectors

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


_model = None


def _fastembed(texts: Sequence[str]) -> list[list[float]]:
    global _model
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise EmbeddingError("Install fastembed before generating embeddings.") from exc
    if _model is None:
        _model = TextEmbedding(model_name=DEFAULT_EMBEDDING_MODEL)
    return [vector.tolist() for vector in _model.embed(list(texts))]
