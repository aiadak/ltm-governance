"""
Embeddings for vector retrieval.

- If OPENAI_API_KEY is set, uses real OpenAI embeddings (text-embedding-3-small).
- Otherwise falls back to a deterministic hashed bag-of-words vector so cosine
  similarity still works offline (the demo runs with zero config).

The same cosine math is used whether vectors come from OpenAI or the fallback,
and whether they live in memory or in Postgres/pgvector.
"""
import os
import re
import math
import hashlib
from typing import List

_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
_FALLBACK_DIM = 256
_token_re = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _token_re.findall((text or "").lower())


def _hash_embed(text: str) -> List[float]:
    """Deterministic hashed bag-of-words embedding, L2-normalised."""
    vec = [0.0] * _FALLBACK_DIM
    toks = _tokens(text)
    for t in toks:
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        idx = h % _FALLBACK_DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> List[float]:
    if _OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=_OPENAI_KEY)
            resp = client.embeddings.create(
                model="text-embedding-3-small", input=text[:8000]
            )
            return resp.data[0].embedding
        except Exception:
            # fall through to deterministic fallback on any error
            pass
    return _hash_embed(text)


def embed_mode() -> str:
    return "openai" if _OPENAI_KEY else "fallback"


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
