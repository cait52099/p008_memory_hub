# Memory Fabric

Platform-grade memory system for OpenClaw + Claude Code with event sourcing, SQLite FTS, and hybrid retrieval.

## Features

- **Event Store**: Append-only JSONL as immutable truth source
- **SQLite + FTS5**: Full-text search with normalized memories
- **Entity Graph**: Lightweight graph with entities and edges
- **Governance**: Approval lifecycle (proposed/active/deprecated/expired)
- **Traces**: Execution debugging and search
- **Eval Runs**: Built-in evaluation metrics
- **Hybrid Retrieval**: FTS + importance + recency + graph expansion
- **Context Assembler**: Token-budgeted context packs for Claude

## Installation

```bash
cd /Users/caihongwei/clawd/projects/p008_memory_hub
export PYTHONPATH=./src:$PYTHONPATH
```

### Install (recommended: venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
memory-hub --help
```

**macOS**: If `memory-hub` is not found after install, add venv to PATH:
```bash
# Add to ~/.zshrc or ~/.bashrc:
export PATH="$PWD/.venv/bin:$PATH"
```

Or use full path: `./.venv/bin/memory-hub --help`

## Quick Start

```bash
# Write a memory
python3 -m cli.commands write "Python is a great language" --type implementation

# Search memories
python3 -m cli.commands search "Python"

# Assemble context pack
python3 -m cli.commands assemble "architecture decisions"

# Summarize
python3 -m cli.commands summarize --type decision

# Show stats
python3 -m cli.commands stats

# Export with redaction
python3 -m cli.commands export /tmp/export.jsonl --redact
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `write <content>` | Write a memory |
| `search <query>` | Search memories |
| `assemble <query>` | Build context pack |
| `summarize` | Summarize memories |
| `approve <type> <id> <proposer>` | Approve a proposal |
| `reject <id> <approver>` | Reject a proposal |
| `gc [--dry-run]` | Garbage collect |
| `export <file>` | Export events |
| `stats` | Show statistics |

Options:
- `--type`: Memory type filter
- `--json`: JSON output
- `--redact`: Redact sensitive data

## Testing

```bash
# Run all tests
PYTHONPATH=./src:$PYTHONPATH ./scripts/smoke_test.sh
PYTHONPATH=./src:$PYTHONPATH ./scripts/eval_retrieval.sh
PYTHONPATH=./src:$PYTHONPATH ./scripts/eval_redaction.sh
```

## Architecture

See [memory_bank/architecture.md](memory_bank/architecture.md) for details.

## Data Storage

Default data directory: `~/.memory_hub/`
- `events/events.jsonl` - Event store
- `memory_hub.db` - SQLite database

## Production Notes

### Data Retention & Backup
Backup BOTH the JSONL events file and the SQLite database:
```bash
tar -czf backup_$(date +%F).tgz data/events data/*.db memory_bank
```
Restore by extracting to the same paths.

### SQLite Tuning
For better performance in production, enable WAL mode:
```bash
sqlite3 ~/.memory_hub/memory_hub.db "PRAGMA journal_mode=WAL;"
sqlite3 ~/.memory_hub/memory_hub.db "PRAGMA synchronous=NORMAL;"
```
Periodically optimize:
```bash
sqlite3 ~/.memory_hub/memory_hub.db "VACUUM;"
sqlite3 ~/.memory_hub/memory_hub.db "PRAGMA optimize;"
```

### Python Version
Requires Python >= 3.9.

## License

MIT
