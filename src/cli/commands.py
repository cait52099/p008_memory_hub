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
from memory_hub.episode import (
    store_episode,
    retrieve_episodes,
    assemble_episodes_context,
    intent_fingerprint,
    calculate_score,
    create_episode,
    mark_episode_used,
    bump_episode_strength,
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

    def assemble(self, query: str, max_tokens: int = 4000, memory_type: str = None, source: str = None, json_output: bool = False, with_episodes: bool = False, project: str = None):
        """Assemble context pack."""
        pack = self.assembler.assemble(
            query,
            max_tokens=max_tokens,
            memory_types=[memory_type] if memory_type else None,
            source=source
        )

        # Prepend episode context if requested
        episode_context = ""
        included_episode_ids = []
        if with_episodes and project:
            fp = intent_fingerprint(query, project)

            # Get final episodes AFTER assemble selects them
            episode_result = assemble_episodes_context(
                query=query,
                project_id=project,
                top_k=5,
                db=self.db
            )

            # Handle new tuple return format (markdown, included_ids)
            if isinstance(episode_result, tuple):
                episode_context, included_episode_ids = episode_result
            else:
                episode_context = episode_result  # Fallback for empty

            # Mark FINAL included episodes as used (post-render selection)
            for ep_id in included_episode_ids:
                try:
                    mark_episode_used(fp, ep_id)
                except Exception:
                    pass  # Best-effort

        output = pack.to_markdown() if not json_output else pack.to_json()

        if json_output:
            if episode_context:
                output["episode_context"] = episode_context
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            if episode_context:
                print(episode_context)
                print("\n---\n")
            print(pack.to_markdown())

    def episode_record(
        self,
        project: str,
        intent: str,
        outcome: str,
        attempts: int = 1,
        rollbacks: int = 0,
        error_signatures: list = None,
        steps: list = None,
        steps_json: Path = None,
        evidence_json: Path = None,
        json_output: bool = False
    ):
        """Record an episode."""
        import json as json_mod

        # Load steps from JSON file if provided
        path_steps = []
        if steps_json and steps_json.exists():
            with open(steps_json) as f:
                path_steps = json_mod.load(f)

        # Combine CLI steps and file steps
        all_steps = (steps or []) + path_steps

        # Load evidence from JSON file if provided
        evidence = {}
        if evidence_json and evidence_json.exists():
            with open(evidence_json) as f:
                evidence = json_mod.load(f)

        # Build cues
        cues = {
            "entities": [],
            "error_signatures": error_signatures or [],
            "tools": [],
            "files": [],
        }

        # Create episode
        episode = create_episode(
            episode_id=None,
            project_id=project,
            intent=intent,
            cues=cues,
            path=all_steps,
            outcome=outcome,
            attempts=attempts,
            rollbacks=rollbacks,
            evidence=evidence,
        )

        # Store episode
        episode_id = store_episode(episode, self.db, self.events)

        # Bump strength of used episodes if this was a success
        if outcome == "success":
            fp = intent_fingerprint(intent, project)
            try:
                bump_episode_strength(fp, self.db)
            except Exception:
                pass  # Best-effort

        if json_output:
            print(json.dumps({"episode_id": episode_id, "score": episode["score"]}, indent=2))
        else:
            print(f"Episode recorded: {episode_id} (score: {episode['score']})")

    def episode_match(self, project: str, prompt: str, top_k: int = 5, json_output: bool = False):
        """Match episodes by prompt."""
        results = retrieve_episodes(project, prompt, top_k, self.db)

        if json_output:
            output = [{
                "episode_id": r.get("episode_id"),
                "intent": r.get("intent"),
                "outcome": r.get("outcome"),
                "score": r.get("score"),
                "path": r.get("path", [])[:3],
            } for r in results]
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            if not results:
                print("No matching episodes found.")
            for r in results:
                print(f"\n--- {r.get('episode_id')} (score: {r.get('score')}) [{r.get('outcome')}] ---")
                print(f"Intent: {r.get('intent')[:100]}...")
                path = r.get("path", [])
                if path:
                    print("Path:")
                    for step in path[:3]:
                        print(f"  - {step}")

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
    assemble_parser.add_argument("--with-episodes", action="store_true", help="Prepend episode context")

    # episode subcommand
    episode_parser = subparsers.add_parser("episode", help="Episode commands")
    episode_subparsers = episode_parser.add_subparsers(dest="episode_command", required=True)

    # episode record
    record_parser = episode_subparsers.add_parser("record", help="Record an episode")
    record_parser.add_argument("--project", required=True, help="Project ID")
    record_parser.add_argument("--intent", required=True, help="Intent text")
    record_parser.add_argument("--outcome", required=True, choices=["success", "failure", "mixed"], help="Outcome")
    record_parser.add_argument("--attempts", type=int, default=1, help="Number of attempts")
    record_parser.add_argument("--rollbacks", type=int, default=0, help="Number of rollbacks")
    record_parser.add_argument("--error-signature", action="append", default=[], help="Error signatures (repeatable)")
    record_parser.add_argument("--step", action="append", default=[], help="Step description (repeatable)")
    record_parser.add_argument("--steps-json", type=Path, help="Path to JSON file with steps")
    record_parser.add_argument("--evidence-json", type=Path, help="Path to JSON file with evidence")
    record_parser.add_argument("--json", action="store_true", help="JSON output")

    # episode match
    match_parser = episode_subparsers.add_parser("match", help="Match episodes")
    match_parser.add_argument("--project", required=True, help="Project ID")
    match_parser.add_argument("--prompt", required=True, help="Prompt to match")
    match_parser.add_argument("--k", type=int, default=5, help="Number of results")
    match_parser.add_argument("--json", action="store_true", help="JSON output")

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
        cli.assemble(args.query, args.max_tokens, args.type, args.project, args.json, args.with_episodes, args.project)
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
    elif args.command == "episode":
        if args.episode_command == "record":
            cli.episode_record(
                project=args.project,
                intent=args.intent,
                outcome=args.outcome,
                attempts=args.attempts,
                rollbacks=args.rollbacks,
                error_signatures=args.error_signature,
                steps=args.step,
                steps_json=args.steps_json,
                evidence_json=args.evidence_json,
                json_output=args.json
            )
        elif args.episode_command == "match":
            cli.episode_match(
                project=args.project,
                prompt=args.prompt,
                top_k=args.k,
                json_output=args.json
            )
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
