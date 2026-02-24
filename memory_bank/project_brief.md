# Memory Fabric - Project Brief

## Vision
Build a platform-grade memory system for OpenClaw + Claude Code that serves as the single source of truth for all agent interactions, decisions, and knowledge.

## Problem Statement
- Claude Code lacks persistent memory across sessions
- OpenClaw needs governance and traceability
- No unified way to search/retrieve past context
- Need auditability for AI agent decisions

## Solution
Event-sourced memory architecture with:
- **Truth Source**: Append-only JSONL event store
- **Fast Access**: SQLite with FTS5 full-text search
- **Relationships**: Lightweight entity graph
- **Governance**: Approval lifecycle for proposals
- **Debugging**: Trace assembly for execution flows
- **Evaluation**: Built-in metrics for retrieval quality

## Scope

### Core Features
1. Event Store (JSONL) - immutable truth source
2. SQLite Database with:
   - Normalized memories table
   - FTS5 full-text index
   - Entities + edges (graph)
   - Approvals (lifecycle)
   - Traces (debug/search)
   - Eval runs
3. Hybrid Retrieval (FTS + graph expansion)
4. Context Assembler (token-budgeted)
5. CLI (write/search/assemble/summarize/approve/reject/gc/export)
6. Test suite (smoke, eval_retrieval, eval_redaction)

### Out of Scope
- Vector embeddings (placeholder only)
- User authentication (future)
- Multi-tenant isolation (future)

## Success Criteria
- [x] Append-only event store functional
- [x] SQLite with FTS5 searchable
- [x] Hybrid retrieval with scoring
- [x] Context assembler with token control
- [x] CLI commands working
- [x] Test scripts passing
- [ ] Production deployment

## Timeline
- Phase 1 (Done): Core infrastructure
- Phase 2 (Done): Retrieval + CLI
- Phase 3 (Done): Testing + Documentation
- Phase 4: Production hardening
