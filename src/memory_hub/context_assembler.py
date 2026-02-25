# Memory Fabric - Context Assembler
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
Context Assembler that outputs ready-to-inject context packs with token budget control.
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ContextPack:
    """A context pack ready for injection into Claude."""
    query: str
    memories: list[dict]
    summaries: list[dict]
    entities: list[dict]
    token_budget: int
    token_used: int
    token_remaining: int

    def to_markdown(self) -> str:
        """Convert to markdown format for easy reading."""
        lines = ["# Context Pack\n"]

        if self.query:
            lines.append(f"**Query:** {self.query}\n")

        lines.append(f"**Token Budget:** {self.token_used}/{self.token_budget} ({self.token_remaining} remaining)\n")

        if self.summaries:
            lines.append("\n## Summaries\n")
            for s in self.summaries:
                lines.append(f"- {s.get('content', '')}")

        if self.entities:
            lines.append("\n## Entities\n")
            for e in self.entities:
                lines.append(f"- **{e.get('name', '')}** ({e.get('type', '')}): {e.get('description', '')}")

        if self.memories:
            lines.append("\n## Memories\n")
            for m in self.memories:
                score_pct = int(m.get('score', 0) * 100)
                lines.append(f"### [{m.get('type', 'general')}] {m.get('id', '')} (score: {score_pct}%)\n")
                lines.append(f"{m.get('content', '')}\n")

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Convert to JSON."""
        return {
            "query": self.query,
            "memories": self.memories,
            "summaries": self.summaries,
            "entities": self.entities,
            "token_budget": self.token_budget,
            "token_used": self.token_used,
            "token_remaining": self.token_remaining
        }


class ContextAssembler:
    """
    Assembles context packs with token budget control.

    Features:
    - Automatic token estimation
    - Priority-based memory selection
    - Summary generation for overflow
    - Entity extraction
    """

    # Rough token conversion
    CHARS_PER_TOKEN = 4

    # Priority order (higher priority = included first)
    PRIORITY_TYPES = ["decision", "architecture", "implementation", "general"]

    def __init__(self, retrieval, database):
        """
        Initialize context assembler.

        Args:
            retrieval: HybridRetrieval instance
            database: MemoryDatabase instance
        """
        self.retrieval = retrieval
        self.db = database

    def assemble(self, query: str, max_tokens: int = 4000,
                memory_types: list[str] = None, source: str = None,
                include_entities: bool = True, include_summaries: bool = True) -> ContextPack:
        """
        Assemble a context pack.

        Args:
            query: Search query
            max_tokens: Token budget
            memory_types: Optional list of memory types to include
            source: Optional filter by source/project
            include_entities: Whether to include entities
            include_summaries: Whether to generate summaries

        Returns:
            ContextPack ready for injection
        """
        max_chars = max_tokens * self.CHARS_PER_TOKEN

        # Get all relevant memories
        all_memories = []
        types_to_search = memory_types or [None]

        for mem_type in types_to_search:
            results = self.retrieval.search(
                query,
                top_k=30,
                memory_type=mem_type if mem_type != "all" else None,
                source=source,
                use_graph=True
            )
            all_memories.extend(results)

        # Sort by priority type then score
        def sort_key(m):
            type_order = self.PRIORITY_TYPES.index(m.memory_type) if m.memory_type in self.PRIORITY_TYPES else 999
            return (type_order, -m.score)
        all_memories.sort(key=sort_key)

        # Select memories within budget
        memories = []
        used_chars = 0

        for mem in all_memories:
            mem_chars = len(mem.content)
            if used_chars + mem_chars <= max_chars:
                memories.append({
                    "id": mem.memory_id,
                    "content": mem.content,
                    "type": mem.memory_type,
                    "source": mem.source,
                    "score": mem.score,
                    "explanation": mem.explanation
                })
                used_chars += mem_chars

        # Get entities if requested
        entities = []
        if include_entities:
            entities = self._extract_entities(query, limit=10)

        # Generate summaries if needed
        summaries = []
        if include_summaries and len(memories) > 5:
            summaries = self._generate_summaries(memories[:10])

        return ContextPack(
            query=query,
            memories=memories,
            summaries=summaries,
            entities=entities,
            token_budget=max_tokens,
            token_used=used_chars // self.CHARS_PER_TOKEN,
            token_remaining=max_tokens - (used_chars // self.CHARS_PER_TOKEN)
        )

    def _extract_entities(self, query: str, limit: int = 10) -> list[dict]:
        """Extract relevant entities."""
        entities = []

        # Search for entities related to query
        try:
            all_entities = self.db.get_entities_by_type("concept")
            for entity in all_entities[:limit]:
                entities.append({
                    "id": entity["entity_id"],
                    "name": entity["name"],
                    "type": entity["entity_type"],
                    "description": entity["description"]
                })
        except:
            pass

        return entities

    def _generate_summaries(self, memories: list[dict]) -> list[dict]:
        """Generate summaries from memories."""
        # Simple extractive summarization
        summaries = []

        # Group by type
        by_type = {}
        for mem in memories:
            mtype = mem.get("type", "general")
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(mem)

        # Create summary for each type
        for mtype, mems in by_type.items():
            if len(mems) > 1:
                content_parts = [m["content"][:200] for m in mems[:3]]
                summaries.append({
                    "type": mtype,
                    "content": f"{len(mems)} {mtype} memories found. Key points: " + " | ".join(content_parts)
                })

        return summaries
