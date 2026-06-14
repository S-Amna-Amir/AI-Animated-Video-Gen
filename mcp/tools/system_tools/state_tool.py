"""
mcp/tools/system_tools/state_tool.py
--------------------------------------
MCP tools: commit_memory, query_memory

Persistent shared memory layer backed by ChromaDB (with an in-process
mock fallback). All agents use these tools to store and retrieve data
across the workflow.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mcp.base_tool import BaseTool
from mcp.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# ── In-process mock store (fallback) ──────────────────────────────────────────
_mock_store: Dict[str, Dict[str, str]] = {}

# ── ChromaDB client (lazy-initialized) ────────────────────────────────────────
_chroma_client = None


def _get_chroma_client():
    global _chroma_client
    if os.getenv("MEMORY_BACKEND", "chromadb") == "mock":
        return None
    if _chroma_client is not None:
        return _chroma_client
    try:
        import chromadb
        _chroma_client = chromadb.Client()
        return _chroma_client
    except ImportError:
        logger.warning("[Memory] ChromaDB not installed — using mock store.")
        return None
    except Exception as e:
        logger.warning(f"[Memory] ChromaDB init failed ({e}) — using mock store.")
        return None


# ── commit_memory ─────────────────────────────────────────────────────────────

class CommitMemoryTool(BaseTool):
    name = "commit_memory"
    description = "Persists a data payload to the named memory collection."
    owner_agent = "all"
    input_schema = {
        "collection": {"type": "string", "required": True},
        "data":       {"type": "object", "required": True},
        "doc_id":     {"type": "string", "required": True},
    }

    def execute(
        self,
        collection: str,
        data: Any,
        doc_id: str,
        **_,
    ) -> Dict[str, Any]:
        serialized = json.dumps(data, ensure_ascii=False)
        client = _get_chroma_client()

        if client is not None:
            try:
                col = client.get_or_create_collection(collection)
                col.upsert(documents=[serialized], ids=[doc_id])
                logger.info(f"[Memory] Committed '{doc_id}' to '{collection}' (ChromaDB)")
            except Exception as e:
                logger.error(f"[Memory] ChromaDB commit failed: {e} — writing to mock store.")
                self._mock_write(collection, doc_id, serialized)
        else:
            self._mock_write(collection, doc_id, serialized)

        return {
            "doc_id":     doc_id,
            "collection": collection,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "status":     "committed",
        }

    @staticmethod
    def _mock_write(collection: str, doc_id: str, serialized: str) -> None:
        if collection not in _mock_store:
            _mock_store[collection] = {}
        _mock_store[collection][doc_id] = serialized
        logger.info(f"[Memory] Committed '{doc_id}' to '{collection}' (mock store)")


# ── query_memory ──────────────────────────────────────────────────────────────

class QueryMemoryTool(BaseTool):
    name = "query_memory"
    description = "Retrieves relevant documents from a memory collection."
    owner_agent = "all"
    input_schema = {
        "collection": {"type": "string",  "required": True},
        "query":      {"type": "string",  "required": True},
        "n_results":  {"type": "integer", "required": False, "default": 3},
    }

    def execute(
        self,
        collection: str,
        query: str,
        n_results: int = 3,
        **_,
    ) -> List[Dict]:
        client = _get_chroma_client()

        if client is not None:
            try:
                col = client.get_or_create_collection(collection)
                results = col.query(query_texts=[query], n_results=n_results)
                docs = results.get("documents", [[]])[0]
                ids  = results.get("ids", [[]])[0]
                return [
                    {"id": i, "data": json.loads(d)}
                    for i, d in zip(ids, docs)
                ]
            except Exception as e:
                logger.error(f"[Memory] ChromaDB query failed: {e} — querying mock store.")

        # Mock fallback
        col_data = _mock_store.get(collection, {})
        out = []
        for doc_id, raw in list(col_data.items())[:n_results]:
            try:
                out.append({"id": doc_id, "data": json.loads(raw)})
            except json.JSONDecodeError:
                out.append({"id": doc_id, "data": raw})
        logger.info(f"[Memory] Queried '{collection}' from mock store — {len(out)} results")
        return out


# Self-register both tools
ToolRegistry.register(CommitMemoryTool())
ToolRegistry.register(QueryMemoryTool())
