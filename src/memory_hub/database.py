# Memory Fabric - SQLite Database
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
SQLite database with:
- normalized memories table
- FTS5 full-text index
- entities + edges (lightweight graph)
- approvals lifecycle
- traces
- eval runs
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def fts_sanitize(query: str) -> str:
    """
    Sanitize user query for FTS5 MATCH.

    FTS5 has strict syntax - punctuation breaks it.
    This extracts safe alphanumeric tokens and joins with OR for better recall.
    """
    if not query:
        return ""

    # Extract alphanumeric tokens (including CJK characters)
    tokens = re.findall(r"[\w]+", query.lower())

    # Dedupe and limit
    tokens = list(dict.fromkeys(tokens))[:20]

    if not tokens:
        return ""

    # Join with OR for OR semantics (better recall)
    return " OR ".join(tokens)


class MemoryDatabase:
    """
    SQLite database for Memory Fabric.

    Schema:
    - memories: normalized memory storage
    - memories_fts: FTS5 full-text search
    - entities: entity registry
    - edges: entity relationships
    - approvals: proposal lifecycle management
    - traces: execution traces for debugging
    - eval_runs: evaluation results
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        # Memories table (normalized)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'general',
                source TEXT,
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT,
                event_id TEXT
            )
        """)

        # FTS5 full-text index
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                memory_id,
                content,
                memory_type,
                source,
                content='memories',
                content_rowid='id'
            )
        """)

        # Triggers to keep FTS in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, memory_id, content, memory_type, source)
                VALUES (new.id, new.memory_id, new.content, new.memory_type, new.source);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, memory_id, content, memory_type, source)
                VALUES ('delete', old.id, old.memory_id, old.content, old.memory_type, old.source);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, memory_id, content, memory_type, source)
                VALUES ('delete', old.id, old.memory_id, old.content, old.memory_type, old.source);
                INSERT INTO memories_fts(rowid, memory_id, content, memory_type, source)
                VALUES (new.id, new.memory_id, new.content, new.memory_type, new.source);
            END
        """)

        # Entities table (for graph)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT UNIQUE NOT NULL,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                properties_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Edges table (relationships between entities)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id TEXT UNIQUE NOT NULL,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                properties_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
                FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
            )
        """)

        # Approvals table (lifecycle management)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_id TEXT UNIQUE NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                proposer TEXT,
                approver TEXT,
                reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT
            )
        """)

        # Traces table (debug/search)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                span_id TEXT,
                parent_span_id TEXT,
                operation_name TEXT NOT NULL,
                status TEXT DEFAULT 'ok',
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_ms REAL,
                input_json TEXT,
                output_json TEXT,
                error_message TEXT,
                metadata_json TEXT
            )
        """)

        # Eval runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eval_id TEXT UNIQUE NOT NULL,
                eval_type TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                total_tests INTEGER DEFAULT 0,
                passed_tests INTEGER DEFAULT 0,
                failed_tests INTEGER DEFAULT 0,
                results_json TEXT,
                metrics_json TEXT
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_traces_trace ON traces(trace_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_type ON eval_runs(eval_type)")

        self.conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ===== Memory Operations =====

    def insert_memory(self, memory_id: str, content: str, memory_type: str = "general",
                      source: str = None, importance: float = 0.5, metadata: dict = None,
                      event_id: str = None, expires_at: str = None) -> int:
        """Insert a new memory."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute("""
            INSERT INTO memories (memory_id, content, memory_type, source, importance,
                                created_at, updated_at, expires_at, metadata_json, event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (memory_id, content, memory_type, source, importance, now, now,
              expires_at, json.dumps(metadata) if metadata else None, event_id))
        self.conn.commit()
        return cursor.lastrowid

    def update_memory(self, memory_id: str, content: str = None, importance: float = None,
                     metadata: dict = None) -> bool:
        """Update an existing memory."""
        cursor = self.conn.cursor()
        updates = []
        params = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if metadata is not None:
            updates.append("metadata_json = ?")
            params.append(json.dumps(metadata))

        updates.append("updated_at = ?")
        params.append(self._now())
        params.append(memory_id)

        cursor.execute(f"""
            UPDATE memories SET {', '.join(updates)} WHERE memory_id = ?
        """, params)
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_memory(self, memory_id: str) -> dict | None:
        """Get a memory by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def search_memories_fts(self, query: str, limit: int = 10, memory_type: str = None) -> list[dict]:
        """Full-text search memories.

        Args:
            query: Raw user query (will be sanitized for FTS)
            limit: Max results
            memory_type: Optional type filter

        Returns:
            List of memory dicts with rank
        """
        # Sanitize query for FTS5 - removes punctuation that breaks MATCH
        safe_query = fts_sanitize(query)

        # If sanitization results in empty query, return no results
        if not safe_query:
            return []

        cursor = self.conn.cursor()

        if memory_type:
            cursor.execute("""
                SELECT m.*, fts.rank
                FROM memories_fts fts
                JOIN memories m ON m.memory_id = fts.memory_id
                WHERE memories_fts MATCH ? AND m.memory_type = ?
                ORDER BY fts.rank
                LIMIT ?
            """, (safe_query, memory_type, limit))
        else:
            cursor.execute("""
                SELECT m.*, fts.rank
                FROM memories_fts fts
                JOIN memories m ON m.memory_id = fts.memory_id
                WHERE memories_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
            """, (safe_query, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_memories_by_type(self, memory_type: str, limit: int = 100) -> list[dict]:
        """Get memories by type."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM memories WHERE memory_type = ?
            ORDER BY importance DESC, created_at DESC LIMIT ?
        """, (memory_type, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_all_memories(self, limit: int = 1000) -> list[dict]:
        """Get all memories."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM memories
            ORDER BY importance DESC, created_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Entity Operations =====

    def insert_entity(self, entity_id: str, entity_type: str, name: str,
                     description: str = None, properties: dict = None) -> int:
        """Insert a new entity."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute("""
            INSERT INTO entities (entity_id, entity_type, name, description,
                                properties_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entity_id, entity_type, name, description,
              json.dumps(properties) if properties else None, now, now))
        self.conn.commit()
        return cursor.lastrowid

    def get_entity(self, entity_id: str) -> dict | None:
        """Get an entity by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_entities_by_type(self, entity_type: str) -> list[dict]:
        """Get entities by type."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM entities WHERE entity_type = ?", (entity_type,))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Edge Operations =====

    def insert_edge(self, edge_id: str, source_entity_id: str, target_entity_id: str,
                   relationship_type: str, weight: float = 1.0, properties: dict = None) -> int:
        """Insert a new edge."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute("""
            INSERT INTO edges (edge_id, source_entity_id, target_entity_id,
                             relationship_type, weight, properties_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (edge_id, source_entity_id, target_entity_id, relationship_type,
              weight, json.dumps(properties) if properties else None, now))
        self.conn.commit()
        return cursor.lastrowid

    def get_edges_from(self, entity_id: str) -> list[dict]:
        """Get edges from an entity."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM edges WHERE source_entity_id = ?", (entity_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_edges_to(self, entity_id: str) -> list[dict]:
        """Get edges to an entity."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM edges WHERE target_entity_id = ?", (entity_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_neighbors(self, entity_id: str) -> list[dict]:
        """Get all neighboring entities."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT e.*, r.relationship_type, r.weight
            FROM edges r
            JOIN entities e ON e.entity_id = r.target_entity_id
            WHERE r.source_entity_id = ?
            UNION
            SELECT e.*, r.relationship_type, r.weight
            FROM edges r
            JOIN entities e ON e.entity_id = r.source_entity_id
            WHERE r.target_entity_id = ?
        """, (entity_id, entity_id))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Approval Operations =====

    def insert_approval(self, approval_id: str, target_type: str, target_id: str,
                       proposer: str, reason: str = None, expires_at: str = None) -> int:
        """Insert a new approval proposal."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute("""
            INSERT INTO approvals (approval_id, target_type, target_id, status,
                                proposer, reason, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?, ?)
        """, (approval_id, target_type, target_id, proposer, reason, now, now, expires_at))
        self.conn.commit()
        return cursor.lastrowid

    def update_approval_status(self, approval_id: str, status: str,
                              approver: str = None) -> bool:
        """Update approval status."""
        cursor = self.conn.cursor()
        now = self._now()
        if approver:
            cursor.execute("""
                UPDATE approvals SET status = ?, approver = ?, updated_at = ?
                WHERE approval_id = ?
            """, (status, approver, now, approval_id))
        else:
            cursor.execute("""
                UPDATE approvals SET status = ?, updated_at = ?
                WHERE approval_id = ?
            """, (status, now, approval_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_approval(self, approval_id: str) -> dict | None:
        """Get an approval."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_approvals_by_status(self, status: str) -> list[dict]:
        """Get approvals by status."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Trace Operations =====

    def insert_trace(self, trace_id: str, span_id: str, operation_name: str,
                    start_time: str, parent_span_id: str = None,
                    input_data: dict = None, metadata: dict = None) -> int:
        """Insert a trace span."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO traces (trace_id, span_id, parent_span_id, operation_name,
                              start_time, input_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (trace_id, span_id, parent_span_id, operation_name, start_time,
              json.dumps(input_data) if input_data else None,
              json.dumps(metadata) if metadata else None))
        self.conn.commit()
        return cursor.lastrowid

    def update_trace(self, span_id: str, end_time: str, status: str = "ok",
                    output_data: dict = None, error_message: str = None) -> bool:
        """Update trace span with end time."""
        cursor = self.conn.cursor()
        # Calculate duration
        cursor.execute("SELECT start_time FROM traces WHERE span_id = ?", (span_id,))
        row = cursor.fetchone()
        if not row:
            return False

        from datetime import datetime
        start = datetime.fromisoformat(row[0])
        end = datetime.fromisoformat(end_time)
        duration_ms = (end - start).total_seconds() * 1000

        cursor.execute("""
            UPDATE traces SET end_time = ?, status = ?, output_json = ?,
                            error_message = ?, duration_ms = ?
            WHERE span_id = ?
        """, (end_time, status, json.dumps(output_data) if output_data else None,
              error_message, duration_ms, span_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_trace(self, trace_id: str) -> list[dict]:
        """Get all spans for a trace."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM traces WHERE trace_id = ? ORDER BY start_time", (trace_id,))
        return [dict(row) for row in cursor.fetchall()]

    def search_traces(self, query: str, limit: int = 100) -> list[dict]:
        """Search traces."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM traces
            WHERE operation_name LIKE ? OR error_message LIKE ?
            ORDER BY start_time DESC LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Eval Operations =====

    def insert_eval_run(self, eval_id: str, eval_type: str, description: str = None) -> int:
        """Insert a new eval run."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute("""
            INSERT INTO eval_runs (eval_id, eval_type, description, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
        """, (eval_id, eval_type, description, now))
        self.conn.commit()
        return cursor.lastrowid

    def update_eval_run(self, eval_id: str, status: str, total: int = None,
                       passed: int = None, failed: int = None,
                       results: dict = None, metrics: dict = None) -> bool:
        """Update eval run results."""
        cursor = self.conn.cursor()
        updates = ["status = ?"]
        params = [status]

        if total is not None:
            updates.append("total_tests = ?")
            params.append(total)
        if passed is not None:
            updates.append("passed_tests = ?")
            params.append(passed)
        if failed is not None:
            updates.append("failed_tests = ?")
            params.append(failed)
        if results is not None:
            updates.append("results_json = ?")
            params.append(json.dumps(results))
        if metrics is not None:
            updates.append("metrics_json = ?")
            params.append(json.dumps(metrics))

        if status in ("completed", "failed", "passed"):
            updates.append("completed_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())

        params.append(eval_id)
        cursor.execute(f"UPDATE eval_runs SET {', '.join(updates)} WHERE eval_id = ?", params)
        self.conn.commit()
        return cursor.rowcount > 0

    def get_eval_run(self, eval_id: str) -> dict | None:
        """Get an eval run."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM eval_runs WHERE eval_id = ?", (eval_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_eval_runs(self, limit: int = 100) -> list[dict]:
        """Get all eval runs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM eval_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

    # ===== Utility =====

    def vacuum(self):
        """Run VACUUM to optimize database."""
        self.conn.execute("VACUUM")
        self.conn.commit()

    def close(self):
        """Close database connection."""
        self.conn.close()


def create_database(db_path: str | Path) -> MemoryDatabase:
    """Create or open a database."""
    return MemoryDatabase(Path(db_path))
