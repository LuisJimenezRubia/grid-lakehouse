"""Find the passages closest in meaning to a question.

Each passage is turned into a vector by a local embedding model; the question too; the closest
passages by cosine similarity are returned. The corpus is small (about a hundred passages), so the
vectors live in one JSON file under data/ and the search is plain Python - no vector database.
The index is rebuilt by itself when a document or the embedding model changes.
"""
import hashlib
import json
import math
from pathlib import Path

from assistant import corpus, llm

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "assistant" / "doc_index.json"      # data/ is not in the repository


def _normalise(vector):
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class Retriever:
    def __init__(self, embed=None, model=llm.EMBED_MODEL, index_path=INDEX):
        """embed(texts) -> vectors; defaults to the local Ollama embedding model."""
        self.embed = embed or (lambda texts: llm.embed(texts, model=model))
        passages = corpus.chunks()
        fingerprint = hashlib.sha256(
            (model + json.dumps([p["text"] for p in passages], ensure_ascii=False)).encode("utf-8")).hexdigest()
        cached = json.loads(index_path.read_text(encoding="utf-8")) if index_path and index_path.exists() else {}
        if cached.get("fingerprint") == fingerprint:
            vectors = cached["vectors"]
        else:
            vectors = []
            for start in range(0, len(passages), 16):         # small batches keep each request short
                vectors += [_normalise(v) for v in self.embed([p["text"] for p in passages[start:start + 16]])]
            if index_path:
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_text(json.dumps({"fingerprint": fingerprint, "vectors": vectors}), encoding="utf-8")
        self.passages, self.vectors = passages, vectors

    def search(self, question, k=4):
        """The k closest passages, each with its similarity score (1 = same direction)."""
        query = _normalise(self.embed([question])[0])
        scored = sorted(((sum(a * b for a, b in zip(query, vector)), passage)
                         for vector, passage in zip(self.vectors, self.passages)),
                        key=lambda pair: pair[0], reverse=True)
        return [{**passage, "score": round(score, 3)} for score, passage in scored[:k]]
