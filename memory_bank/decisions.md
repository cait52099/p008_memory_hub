# Architecture Decisions

## ADR-001: Event Sourcing as Primary Pattern

**Status**: Accepted

**Context**: Memory system needs auditability and the ability to replay state.

**Decision**: Use append-only JSONL as truth source. All state changes are events.

**Consequences**:
- Positive: Full audit trail, easy replay
- Negative: Need to rebuild read models for queries

## ADR-002: SQLite + FTS5 for Storage

**Status**: Accepted

**Context**: Need fast full-text search with minimal infrastructure.

**Decision**: Use SQLite with FTS5 virtual table for full-text search.

**Consequences**:
- Positive: No external services, fast, ACID compliant
- Negative: Limited to single-writer, no distributed transactions

## ADR-003: Hybrid Retrieval

**Status**: Accepted

**Context**: Single search method insufficient for quality results.

**Decision**: Combine FTS5, importance scoring, recency, and graph expansion.

**Scoring weights**:
- FTS: 40%
- Importance: 30%
- Recency: 20%
- Graph: 10%

## ADR-004: Token-Budgeted Context Assembly

**Status**: Accepted

**Context**: Claude has context window limits.

**Decision**: ContextAssembler builds packs with explicit token budgets.

**Mechanism**: Character-count approximation (4 chars ≈ 1 token)

## ADR-005: Approval Lifecycle

**Status**: Accepted

**Context**: Need governance for proposals and changes.

**Decision**: Status field with proposed/active/deprecated/expired states.

## ADR-006: CLI-First Design

**Status**: Accepted

**Context**: Need easy integration with Claude Code.

**Decision**: CLI as primary interface with JSON output option.

**Commands**: write, search, assemble, summarize, approve, reject, gc, export
