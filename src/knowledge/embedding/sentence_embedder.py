from typing import List, Sequence

from sentence_transformers import SentenceTransformer


class SentenceEmbedder:
    def __init__(self, model_path: str, batch_size: int = 32):
        self.model = SentenceTransformer(model_path)
        self.batch_size = batch_size

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
