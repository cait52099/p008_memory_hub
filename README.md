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
# Clone and enter directory
git clone https://github.com/cait52099/p008_memory_hub.git
cd p008_memory_hub

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Verify
memory-hub --help
```

**macOS**: If `memory-hub` command is not found after install, activate the venv first:
```bash
source .venv/bin/activate
```

Or add to PATH: `export PATH="$PWD/.venv/bin:$PATH"`

## Quick Start

```bash
# Write a memory
memory-hub write "Python is a great language" --type implementation

# Search memories
memory-hub search "Python"

# Assemble context pack
memory-hub assemble "architecture decisions"

# Summarize
memory-hub summarize --type decision

# Show stats
memory-hub stats

# Export with redaction
memory-hub export /tmp/export.jsonl --redact
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
bash scripts/verify_all.sh
```

**Troubleshooting**: If tests fail with import errors, try:
```bash
export PYTHONPATH=./src:$PYTHONPATH
bash scripts/verify_all.sh
```

## Architecture

See [memory_bank/architecture.md](memory_bank/architecture.md) for details.

## Data Storage

Default data directory: `~/.memory_hub/`
- `events/events.jsonl` - Event store
- `memory_hub.db` - SQLite database

## Production Notes

### Data Retention & Backup
Backup your data directory:
```bash
# Recommended: backup ~/.memory_hub/
tar -czf memory_hub_backup_$(date +%F).tgz ~/.memory_hub/
```
Restore by extracting to `~/.memory_hub/`.

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
