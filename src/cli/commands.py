# Memory Fabric - CLI
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
CLI commands for Memory Fabric.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from memory_hub import (
    create_event_store,
    create_database,
    HybridRetrieval,
    ContextAssembler,
)


class MemoryHubCLI:
    """CLI for Memory Fabric."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "memory_hub.db"
        self.events = create_event_store(self.data_dir / "events")
        self.db = create_database(self.db_path)
        self.retrieval = HybridRetrieval(self.db, self.events)
        self.assembler = ContextAssembler(self.retrieval, self.db)

    def write(self, content: str, memory_type: str = "general", source: str = None,
             importance: float = 0.5, metadata: dict = None):
        """Write a memory."""
        memory_id = str(uuid.uuid4())[:8]

        # Write to event store
        self.events.append("memory_created", {
            "memory_id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "source": source,
            "importance": importance,
            "metadata": metadata or {}
        })

        # Write to database
        self.db.insert_memory(
            memory_id=memory_id,
            content=content,
            memory_type=memory_type,
            source=source,
            importance=importance,
            metadata=metadata
        )

        print(f"Memory created: {memory_id}")

    def search(self, query: str, top_k: int = 10, memory_type: str = None, source: str = None, json_output: bool = False):
        """Search memories."""
        results = self.retrieval.search(query, top_k=top_k, memory_type=memory_type, source=source)

        if json_output:
            output = [{
                "id": r.memory_id,
                "content": r.content,
                "type": r.memory_type,
                "score": r.score,
                "explanation": r.explanation
            } for r in results]
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            for r in results:
                print(f"\n--- {r.memory_id} (score: {r.score:.2f}) [{r.memory_type}] ---")
                print(r.content[:200] + "..." if len(r.content) > 200 else r.content)
                print(f"Explanation: {r.explanation}")

    def assemble(self, query: str, max_tokens: int = 4000, memory_type: str = None, source: str = None, json_output: bool = False):
        """Assemble context pack."""
        pack = self.assembler.assemble(
            query,
            max_tokens=max_tokens,
            memory_types=[memory_type] if memory_type else None,
            source=source
        )

        if json_output:
            print(json.dumps(pack.to_json(), indent=2, ensure_ascii=False))
        else:
            print(pack.to_markdown())

    def summarize(self, query: str = None, memory_type: str = None, json_output: bool = False):
        """Summarize memories."""
        if memory_type:
            memories = self.db.get_memories_by_type(memory_type, limit=100)
        else:
            memories = self.db.get_all_memories(limit=100)

        by_type = {}
        for m in memories:
            mtype = m.get("memory_type", "general")
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(m)

        if json_output:
            print(json.dumps(by_type, indent=2, ensure_ascii=False))
        else:
            for mtype, mems in by_type.items():
                print(f"\n## {mtype} ({len(mems)} memories)")
                for m in mems[:5]:
                    print(f"- {m['content'][:100]}...")

    def approve(self, target_type: str, target_id: str, proposer: str, reason: str = None):
        """Approve a proposal."""
        approval_id = f"approval_{uuid.uuid4().hex[:8]}"

        self.events.append("approval_proposed", {
            "approval_id": approval_id,
            "target_type": target_type,
            "target_id": target_id,
            "proposer": proposer,
            "reason": reason
        })

        self.db.insert_approval(approval_id, target_type, target_id, proposer, reason)
        self.db.update_approval_status(approval_id, "active", approver=proposer)

        print(f"Approved: {approval_id}")

    def reject(self, approval_id: str, approver: str, reason: str = None):
        """Reject a proposal."""
        self.events.append("approval_rejected", {
            "approval_id": approval_id,
            "approver": approver,
            "reason": reason
        })

        self.db.update_approval_status(approval_id, "rejected", approver=approver)
        print(f"Rejected: {approval_id}")

    def gc(self, dry_run: bool = True):
        """Garbage collect expired memories."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT memory_id, expires_at FROM memories WHERE expires_at IS NOT NULL")
        expired = [row for row in cursor.fetchall() if row[1] < now]

        if dry_run:
            print(f"Would delete {len(expired)} expired memories:")
            for mem_id, _ in expired:
                print(f"  - {mem_id}")
        else:
            for mem_id, _ in expired:
                self.db.delete_memory(mem_id)
            print(f"Deleted {len(expired)} expired memories")

    def export(self, output_file: Path, redact: bool = False):
        """Export all events."""
        self.events.export(output_file, redact=redact)
        print(f"Exported to {output_file}")

    def stats(self, json_output: bool = False):
        """Show statistics."""
        stats = {
            "events": self.events.count(),
            "memories": len(self.db.get_all_memories(limit=10000)),
            "entities": len(self.db.get_entities_by_type("concept")),
            "approvals": {
                "active": len(self.db.get_approvals_by_status("active")),
                "proposed": len(self.db.get_approvals_by_status("proposed")),
                "deprecated": len(self.db.get_approvals_by_status("deprecated")),
            }
        }

        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            print(f"Events: {stats['events']}")
            print(f"Memories: {stats['memories']}")
            print(f"Entities: {stats['entities']}")
            print(f"Approvals: {stats['approvals']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Memory Fabric CLI")
    parser.add_argument("--data-dir", default="~/.memory_hub", help="Data directory")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # write
    write_parser = subparsers.add_parser("write", help="Write a memory")
    write_parser.add_argument("content", help="Memory content")
    write_parser.add_argument("--type", default="general", help="Memory type")
    write_parser.add_argument("--source", help="Source")
    write_parser.add_argument("--importance", type=float, default=0.5, help="Importance 0-1")

    # search
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--top-k", type=int, default=10)
    search_parser.add_argument("--type", help="Filter by type")
    search_parser.add_argument("--project", help="Filter by source/project")
    search_parser.add_argument("--json", action="store_true", help="JSON output")

    # assemble
    assemble_parser = subparsers.add_parser("assemble", help="Assemble context pack")
    assemble_parser.add_argument("query", help="Query")
    assemble_parser.add_argument("--max-tokens", type=int, default=4000)
    assemble_parser.add_argument("--type", help="Memory type filter")
    assemble_parser.add_argument("--project", help="Filter by source/project")
    assemble_parser.add_argument("--json", action="store_true", help="JSON output")

    # summarize
    summarize_parser = subparsers.add_parser("summarize", help="Summarize memories")
    summarize_parser.add_argument("--query", help="Query")
    summarize_parser.add_argument("--type", help="Memory type")
    summarize_parser.add_argument("--json", action="store_true", help="JSON output")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
    approve_parser.add_argument("target_type", help="Target type")
    approve_parser.add_argument("target_id", help="Target ID")
    approve_parser.add_argument("proposer", help="Proposer")
    approve_parser.add_argument("--reason", help="Reason")

    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
    reject_parser.add_argument("approval_id", help="Approval ID")
    reject_parser.add_argument("approver", help="Approver")
    reject_parser.add_argument("--reason", help="Reason")

    # gc
    gc_parser = subparsers.add_parser("gc", help="Garbage collect")
    gc_parser.add_argument("--dry-run", action="store_true", default=True)

    # export
    export_parser = subparsers.add_parser("export", help="Export events")
    export_parser.add_argument("output", help="Output file")
    export_parser.add_argument("--redact", action="store_true", help="Redact sensitive data")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    # Expand data dir
    data_dir = Path(args.data_dir).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create CLI
    cli = MemoryHubCLI(data_dir)

    # Execute command
    if args.command == "write":
        cli.write(args.content, args.type, args.source, args.importance)
    elif args.command == "search":
        cli.search(args.query, args.top_k, args.type, args.project, args.json)
    elif args.command == "assemble":
        cli.assemble(args.query, args.max_tokens, args.type, args.project, args.json)
    elif args.command == "summarize":
        cli.summarize(args.query, args.type, args.json)
    elif args.command == "approve":
        cli.approve(args.target_type, args.target_id, args.proposer, args.reason)
    elif args.command == "reject":
        cli.reject(args.approval_id, args.approver, args.reason)
    elif args.command == "gc":
        cli.gc(args.dry_run)
    elif args.command == "export":
        cli.export(Path(args.output), args.redact)
    elif args.command == "stats":
        cli.stats(args.json)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
