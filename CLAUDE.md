# Memory Fabric - Claude Code Instructions

This is a Memory Fabric project for OpenClaw + Claude Code.

## Project Structure

```
p008_memory_hub/
├── src/
│   ├── memory_hub/       # Core modules
│   │   ├── __init__.py
│   │   ├── event_store.py   # JSONL event store
│   │   ├── database.py      # SQLite + FTS5
│   │   ├── retrieval.py     # Hybrid retrieval
│   │   └── context_assembler.py
│   └── cli/
│       └── commands.py      # CLI
├── scripts/
│   ├── smoke_test.sh       # Basic functionality
│   ├── eval_retrieval.sh   # Retrieval quality
│   └── eval_redaction.sh   # Redaction quality
├── memory_bank/            # Documentation
│   ├── project_brief.md
│   ├── decisions.md
│   ├── architecture.md
│   ├── glossary.md
│   ├── open_questions.md
│   └── working_log.md
└── data/                   # Data storage
```

## Key Commands

```bash
# Setup
cd /Users/caihongwei/clawd/projects/p008_memory_hub
export PYTHONPATH=./src:$PYTHONPATH

# Write memory
python3 -m cli.commands write "content" --type general

# Search
python3 -m cli.commands search "query" --json

# Context pack
python3 -m cli.commands assemble "query" --max-tokens 4000

# Run tests
PYTHONPATH=./src:$PYTHONPATH ./scripts/smoke_test.sh
PYTHONPATH=./src:$PYTHONPATH ./scripts/eval_retrieval.sh
PYTHONPATH=./src:$PYTHONPATH ./scripts/eval_redaction.sh
```

## Development Notes

- Event store is append-only JSONL - never modify directly
- Database auto-syncs FTS via triggers
- Hybrid retrieval uses: FTS 40%, importance 30%, recency 20%, graph 10%
- Token budget uses 4 chars ≈ 1 token approximation

## Tests

Always run tests after modifications:
- smoke_test.sh - Core functionality
- eval_retrieval.sh - Retrieval quality assertions
- eval_redaction.sh - Redaction assertions
