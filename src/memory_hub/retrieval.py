# Memory Fabric - Hybrid Retrieval
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
Hybrid retrieval combining:
- FTS5 full-text search
- Optional vector search (embedding-based)
- Graph expansion (entity relationships)
- Explainable scoring
"""

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalResult:
    """A single retrieval result with scoring explanation."""
    memory_id: str
    content: str
    memory_type: str
    source: str
    importance: float
    created_at: str
    score: float
    scores: dict[str, float]  # Breakdown of scoring components
    explanation: str


class HybridRetrieval:
    """
    Hybrid retrieval system combining multiple signals:
    - FTS5 text matching
    - Importance/relevance scoring
    - Graph-based expansion (optional)
    """

    # Scoring weights
    FTS_WEIGHT = 0.4
    IMPORTANCE_WEIGHT = 0.3
    RECENCY_WEIGHT = 0.2
    GRAPH_WEIGHT = 0.1

    def __init__(self, database, event_store=None, embedding_model=None):
        """
        Initialize hybrid retrieval.

        Args:
            database: MemoryDatabase instance
            event_store: Optional EventStore for graph expansion
            embedding_model: Optional embedding model for vector search
        """
        self.db = database
        self.event_store = event_store
        self.embedding_model = embedding_model

    def search(self, query: str, top_k: int = 10, memory_type: str = None, source: str = None,
               use_graph: bool = False, expand_entities: bool = False) -> list[RetrievalResult]:
        """
        Perform hybrid search.

        Args:
            query: Search query
            top_k: Number of results to return
            memory_type: Optional filter by memory type
            source: Optional filter by source/project
            use_graph: Whether to use graph expansion
            expand_entities: Whether to expand by entity relationships

        Returns:
            List of RetrievalResult with scores and explanations
        """
        # Get FTS results
        fts_results = self.db.search_memories_fts(query, limit=top_k * 3, memory_type=memory_type, source=source)

        if not fts_results:
            # Fall back to type/source filtered memories
            if memory_type and source:
                # Use SQL-level filtering to avoid truncation by global results
                fts_results = self.db.get_memories_by_type_and_source(
                    memory_type, source, limit=top_k * 3
                )
            elif memory_type:
                fts_results = self.db.get_memories_by_type(memory_type, limit=top_k * 3)
            elif source:
                fts_results = self.db.get_memories_by_source(source, limit=top_k * 3)
            else:
                fts_results = self.db.get_all_memories(limit=top_k * 3)

        # Score and rank results
        results = []
        for row in fts_results:
            scores = self._calculate_scores(row, query, use_graph=use_graph)
            total_score = (
                scores["fts"] * self.FTS_WEIGHT +
                scores["importance"] * self.IMPORTANCE_WEIGHT +
                scores["recency"] * self.RECENCY_WEIGHT +
                scores.get("graph", 0) * self.GRAPH_WEIGHT
            )
            scores["total"] = total_score

            explanation = self._explain_score(scores, query)

            result = RetrievalResult(
                memory_id=row["memory_id"],
                content=row["content"],
                memory_type=row["memory_type"],
                source=row["source"],
                importance=row["importance"],
                created_at=row["created_at"],
                score=total_score,
                scores=scores,
                explanation=explanation
            )
            results.append(result)

        # Sort by total score
        results.sort(key=lambda x: x.score, reverse=True)

        # Expand by entities if requested
        if expand_entities and self.event_store:
            results = self._expand_by_entities(results, query)

        return results[:top_k]

    def _calculate_scores(self, memory_row: dict, query: str, use_graph: bool = False) -> dict[str, float]:
        """Calculate component scores for a memory."""
        scores = {}

        # FTS score (from rank)
        try:
            fts_rank = int(memory_row.get("rank", 1) or 1)
            if fts_rank <= 0:
                scores["fts"] = 1.0  # Perfect match
            else:
                scores["fts"] = 1.0 / (1.0 + math.log1p(fts_rank))
        except (ValueError, TypeError):
            scores["fts"] = 0.5  # Default if rank unavailable

        # Importance score (0-1)
        scores["importance"] = memory_row.get("importance", 0.5)

        # Recency score (exponential decay)
        from datetime import datetime, timezone
        try:
            created = datetime.fromisoformat(memory_row.get("created_at", ""))
            now = datetime.now(timezone.utc)
            days_old = (now - created).days
            scores["recency"] = math.exp(-days_old / 365)  # Half-life of 1 year
        except:
            scores["recency"] = 0.5

        # Graph score (if enabled)
        if use_graph:
            scores["graph"] = self._calculate_graph_score(memory_row.get("memory_id"))
        else:
            scores["graph"] = 0.0

        return scores

    def _calculate_graph_score(self, memory_id: str) -> float:
        """Calculate score based on entity connections."""
        # Get entities linked to this memory
        # This is a simplified implementation
        try:
            entity_id = f"memory_{memory_id}"
            neighbors = self.db.get_neighbors(entity_id)
            if neighbors:
                # Score based on number of connections
                return min(1.0, len(neighbors) / 10.0)
        except:
            pass
        return 0.0

    def _explain_score(self, scores: dict[str, float], query: str) -> str:
        """Generate human-readable explanation of scoring."""
        parts = []

        if scores.get("fts", 0) > 0.5:
            parts.append("high text relevance")
        elif scores.get("fts", 0) > 0.2:
            parts.append("moderate text relevance")
        else:
            parts.append("low text relevance")

        if scores.get("importance", 0) > 0.7:
            parts.append("high importance")
        elif scores.get("importance", 0) > 0.4:
            parts.append("medium importance")

        if scores.get("recency", 0) > 0.7:
            parts.append("recent")
        elif scores.get("recency", 0) > 0.3:
            parts.append("somewhat recent")

        if scores.get("graph", 0) > 0.3:
            parts.append("well-connected in graph")

        if not parts:
            parts.append("default relevance")

        return ", ".join(parts)

    def _expand_by_entities(self, results: list[RetrievalResult], query: str) -> list[RetrievalResult]:
        """Expand results by following entity relationships."""
        expanded_ids = {r.memory_id for r in results}
        expanded_results = list(results)

        for result in results[:3]:  # Expand top 3
            try:
                entity_id = f"memory_{result.memory_id}"
                neighbors = self.db.get_neighbors(entity_id)

                for neighbor in neighbors:
                    neighbor_id = neighbor.get("entity_id", "").replace("memory_", "")
                    if neighbor_id and neighbor_id not in expanded_ids:
                        # Fetch the memory
                        memory = self.db.get_memory(neighbor_id)
                        if memory:
                            scores = {
                                "fts": 0.1,
                                "importance": neighbor.get("weight", 0.5),
                                "recency": 0.5,
                                "graph": 0.8,
                                "total": 0.3
                            }
                            expanded_results.append(RetrievalResult(
                                memory_id=memory["memory_id"],
                                content=memory["content"],
                                memory_type=memory["memory_type"],
                                source=memory["source"],
                                importance=memory["importance"],
                                created_at=memory["created_at"],
                                score=0.3,
                                scores=scores,
                                explanation="found via entity expansion"
                            ))
                            expanded_ids.add(neighbor_id)
            except:
                continue

        return expanded_results

    def assemble_context(self, query: str, max_tokens: int = 4000,
                       memory_type: str = None) -> dict[str, Any]:
        """
        Assemble a context pack for injection into Claude.

        Args:
            query: Query to search for
            max_tokens: Maximum tokens (approximate)
            memory_type: Optional memory type filter

        Returns:
            Context pack with memories and metadata
        """
        # Get results
        results = self.search(query, top_k=20, memory_type=memory_type, use_graph=True)

        # Build context
        memories = []
        total_chars = 0

        for result in results:
            # Rough token estimate: 1 token ≈ 4 characters
            estimated_tokens = len(result.content) // 4
            if total_chars + estimated_tokens > max_tokens * 4:
                break

            memories.append({
                "id": result.memory_id,
                "content": result.content,
                "type": result.memory_type,
                "source": result.source,
                "score": result.score,
                "explanation": result.explanation
            })
            total_chars += estimated_tokens

        return {
            "query": query,
            "memories": memories,
            "count": len(memories),
            "token_estimate": total_chars // 4,
            "sources": list(set(m.get("source") for m in memories if m.get("source")))
        }
