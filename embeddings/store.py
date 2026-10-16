# embeddings/store.py
"""
ChromaDB vector store for Axion.

AUDIT FIX 1 — ChromaDB reversion bug (Audit §4 ⚠️):
  add_chunk() and add_claim() now use .upsert() instead of .add().
  Re-ingesting a paper no longer raises DuplicateIDError.
  The regression test test_BUG_store_add_chunk_no_dedup should be
  reverted to assert upsert() is called, NOT that an exception is raised.

AUDIT FIX 2 — Module-level ML imports (Audit §4 ⚠️):
  chromadb.PersistentClient and SentenceTransformerEmbeddingFunction are
  no longer instantiated at import time. They are lazy-loaded via
  _get_client() and _get_ef() the first time a collection is actually
  needed. Importing store.py in tests no longer triggers a live disk
  connection or loads 400 MB of model weights, so mocking works cleanly
  and test suite startup drops from ~46s to near-instant.
"""

from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DIR, EMBEDDING_MODEL

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_client: chromadb.PersistentClient | None = None
_ef: embedding_functions.SentenceTransformerEmbeddingFunction | None = None


def _get_client() -> chromadb.PersistentClient:
    """Return (or create) the shared ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _get_ef() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    """Return (or create) the shared SentenceTransformer embedding function."""
    global _ef
    if _ef is None:
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
    return _ef


# ---------------------------------------------------------------------------
# Collection accessors — lazy, mockable
# ---------------------------------------------------------------------------

def _chunks_col() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name="paper_chunks",
        embedding_function=_get_ef(),
    )


def _claims_col() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name="claims",
        embedding_function=_get_ef(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_chunk(doc_id: str, text: str, metadata: dict) -> str:
    """
    Add or update a paper text chunk.
    Uses .upsert() — idempotent, safe to call on re-ingestion.
    """
    _chunks_col().upsert(documents=[text], ids=[doc_id], metadatas=[metadata])
    return doc_id


def add_claim(claim_id: int, claim_text: str, metadata: dict) -> str:
    """
    Add or update a claim embedding.
    Uses .upsert() — idempotent, safe to call on re-ingestion.
    """
    doc_id = f"claim_{claim_id}"
    _claims_col().upsert(documents=[claim_text], ids=[doc_id], metadatas=[metadata])
    return doc_id


def find_similar_claims(claim_text: str, n_results: int = 10) -> list[dict]:
    """Find the most semantically similar claims to a given text."""
    results = _claims_col().query(
        query_texts=[claim_text],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    similar = []
    for i in range(len(results["ids"][0])):
        similar.append({
            "doc_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return similar


def find_similar_chunks(query: str, n_results: int = 5) -> list[dict]:
    """Find paper chunks relevant to a query."""
    results = _chunks_col().query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    similar = []
    for i in range(len(results["ids"][0])):
        similar.append({
            "doc_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return similar


def delete_paper_chunks(arxiv_id: str) -> int:
    """Delete all chunks belonging to a paper. Returns count removed."""
    col = _chunks_col()
    existing = col.get(where={"arxiv_id": arxiv_id})
    ids = existing.get("ids", [])
    if ids:
        col.delete(ids=ids)
    return len(ids)


def delete_claim(claim_id: int) -> None:
    """Delete a single claim embedding."""
    _claims_col().delete(ids=[f"claim_{claim_id}"])


def collection_stats() -> dict:
    """Return basic stats for both collections (health checks / UI)."""
    return {
        "chunks": _chunks_col().count(),
        "claims": _claims_col().count(),
    }