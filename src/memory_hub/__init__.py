# Memory Fabric - Main Package
# SPDX-License-Identifier: AGPL-3.0

"""
Memory Fabric - Event-sourced memory system for OpenClaw + Claude Code.

Components:
- Event Store: Append-only JSONL truth source
- Database: SQLite with FTS5, entities, edges, approvals, traces, evals
- Retrieval: Hybrid FTS + graph + optional vector search
- Context Assembler: Token-budgeted context packs
"""

from .event_store import EventStore, create_event_store
from .database import MemoryDatabase, create_database
from .retrieval import HybridRetrieval, RetrievalResult
from .context_assembler import ContextAssembler, ContextPack

__version__ = "0.1.0"

__all__ = [
    "EventStore",
    "create_event_store",
    "MemoryDatabase",
    "create_database",
    "HybridRetrieval",
    "RetrievalResult",
    "ContextAssembler",
    "ContextPack",
]
