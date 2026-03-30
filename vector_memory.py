"""
Vector memory for AgentOS POC.
Stores agent task inputs/outputs as embeddings so agents can retrieve
semantically relevant past context across restarts.

Uses ChromaDB with its default embedding function (sentence-transformers).
"""
from __future__ import annotations

import hashlib
import os

import chromadb
from chromadb.utils import embedding_functions

# Number of past results to surface as context
_TOP_K = 3

# Collection name for task memory
_COLLECTION = "task_memory"


class VectorMemory:
    """Persistent semantic memory for agent task context."""

    def __init__(self, persist_dir: str = "./agentos_memory"):
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._ef = embedding_functions.DefaultEmbeddingFunction()
        self._col = self._client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, task_id: str, role: str, title: str, input_text: str, output: str) -> None:
        """Persist a completed task's context as a vector embedding."""
        doc = f"Role: {role}\nTitle: {title}\nInput: {input_text}\nOutput: {output}"
        # Deterministic document id from task_id so upsert is idempotent
        doc_id = hashlib.sha256(task_id.encode()).hexdigest()[:16]
        self._col.upsert(
            ids=[doc_id],
            documents=[doc],
            metadatas=[{"task_id": task_id, "role": role, "title": title}],
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def retrieve(self, query: str, role: str | None = None, top_k: int = _TOP_K) -> str:
        """
        Return a formatted string of the most semantically similar past
        task outputs for the given query.  Returns empty string if the
        collection is empty.
        """
        count = self._col.count()
        if count == 0:
            return ""

        where = {"role": role} if role else None
        results = self._col.query(
            query_texts=[query],
            n_results=min(top_k, count),
            where=where,
        )

        docs: list[str] = results.get("documents", [[]])[0]
        metas: list[dict] = results.get("metadatas", [[]])[0]

        if not docs:
            return ""

        parts = []
        for doc, meta in zip(docs, metas):
            parts.append(f"[Past task — {meta.get('title', 'unknown')}]\n{doc}")
        return "\n\n".join(parts)
