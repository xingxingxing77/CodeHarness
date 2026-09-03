"""memory/：pgvector 语义记忆（后端设计 §7.9，P3）。

Embedder 双通道：OpenAIEmbedder（text-embedding-3-small，需 key）/
HashEmbedder（确定性哈希向量，维度一致，演示与测试用，语义弱）。
检索：HNSW 余弦相似度 top-k。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """确定性哈希向量（1536 维）：演示/测试通道，无语义能力。"""

    dim = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in text.lower().split() or [text.lower()]:
                digest = hashlib.sha256(token.encode()).digest()
                for i in range(0, 32, 2):
                    idx = int.from_bytes(digest[i : i + 2], "big") % self.dim
                    vec[idx] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAIEmbedder:
    dim = 1536

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small") -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in resp.data]


def default_embedder() -> Embedder:
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIEmbedder()
    return HashEmbedder()


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    tenant_id: str
    content: str
    kind: str
    score: float | None = None


class MemoryStore:
    """pgvector 记忆存取（SQL 直用 asyncpg；vector 以文本字面量传参）。"""

    def __init__(self, pool, embedder: Embedder | None = None) -> None:
        self._pool = pool
        self._embedder = embedder or default_embedder()

    async def add(
        self,
        tenant_id: str,
        content: str,
        *,
        kind: str = "fact",
        session_id: str | None = None,
        meta: dict | None = None,
    ) -> MemoryRecord:
        (embedding,) = await self._embedder.embed([content])
        row = await self._pool.fetchrow(
            "INSERT INTO memories (tenant_id, session_id, kind, content, embedding, meta)"
            " VALUES ($1,$2,$3,$4,$5::vector,$6::jsonb) RETURNING id",
            __import__("uuid").UUID(tenant_id),
            __import__("uuid").UUID(session_id) if session_id else None,
            kind,
            content,
            "[" + ",".join(f"{v:.6f}" for v in embedding) + "]",
            json.dumps(meta or {}),
        )
        return MemoryRecord(id=row["id"], tenant_id=tenant_id, content=content, kind=kind)

    async def search(
        self, tenant_id: str, query: str, *, k: int = 5
    ) -> list[MemoryRecord]:
        (embedding,) = await self._embedder.embed([query])
        literal = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
        rows = await self._pool.fetch(
            "SELECT id, tenant_id::text, content, kind,"
            " 1 - (embedding <=> $2::vector) AS score"
            " FROM memories WHERE tenant_id = $1"
            " ORDER BY embedding <=> $2::vector LIMIT $3",
            __import__("uuid").UUID(tenant_id),
            literal,
            k,
        )
        return [
            MemoryRecord(
                id=r["id"],
                tenant_id=r["tenant_id"],
                content=r["content"],
                kind=r["kind"],
                score=float(r["score"]),
            )
            for r in rows
        ]
