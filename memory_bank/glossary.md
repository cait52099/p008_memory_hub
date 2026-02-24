# Glossary

## Terms

### Event Store
Append-only JSONL file serving as the single source of truth. All state changes are recorded as immutable events.

### Memory
A piece of stored information with content, type, source, and importance score.

### FTS5
Full-Text Search version 5 - SQLite's built-in full-text search engine.

### Hybrid Retrieval
Search method combining multiple signals: FTS text match, importance, recency, and graph relationships.

### Context Pack
A bundle of memories and metadata assembled for injection into Claude Code, respecting token budgets.

### Entity
A node in the knowledge graph representing a concept, person, or thing.

### Edge
A relationship between two entities with a type and optional weight.

### Approval
Lifecycle tracking for proposals with states: proposed, active, deprecated, expired.

### Trace
A debugging record capturing execution flow with timing information.

### Eval Run
A recorded evaluation test with pass/fail status and metrics.

### Redaction
The process of masking sensitive information (passwords, tokens, keys) during export.
