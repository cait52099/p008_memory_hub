# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Memory Fabric                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌──────────────┐     ┌───────────────┐  │
│  │    CLI      │────▶│ Context      │◀────│  Retrieval    │  │
│  │  Commands   │     │ Assembler    │     │  (Hybrid)      │  │
│  └─────────────┘     └──────────────┘     └───────────────┘  │
│         │                   │                      │          │
│         │                   ▼                      ▼          │
│         │          ┌──────────────────┐   ┌───────────────┐    │
│         │          │     SQLite      │   │  Event Store  │    │
│         │          │ (FTS5, Graph,   │◀──│   (JSONL)      │    │
│         │          │  Traces, Evals) │   │   Append-only │    │
│         │          └──────────────────┘   └───────────────┘    │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │                  Memory Bank                         │     │
│  │  project_brief.md | decisions.md | architecture.md │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Event Store (`event_store.py`)
- Append-only JSONL file
- Immutable events as truth source
- Supports correlation IDs for tracing

### Database (`database.py`)
- SQLite with FTS5
- Tables: memories, entities, edges, approvals, traces, eval_runs
- Automatic FTS sync via triggers

### Retrieval (`retrieval.py`)
- Hybrid scoring: FTS + importance + recency + graph
- Explainable scoring breakdown
- Optional entity expansion

### Context Assembler (`context_assembler.py`)
- Token budget control
- Priority-based memory selection
- Summary generation

### CLI (`cli/commands.py`)
- write, search, assemble, summarize
- approve, reject, gc, export
- JSON output option

## Data Flow

1. **Write**: CLI → Event Store → Database (via triggers)
2. **Search**: CLI → Retrieval → Database FTS → Score/Rank
3. **Assemble**: Query → Retrieval → ContextAssembler → ContextPack

## Storage

- Data directory: `~/.memory_hub/` (configurable)
- Events: `events/events.jsonl`
- Database: `memory_hub.db`
