# Open Questions

## Technical

1. **Vector Embeddings**: Should we add actual vector search? Currently placeholder only.
   - Pro: Better semantic matching
   - Con: Additional infrastructure (embedding model)

2. **Sync Strategy**: How to sync event store with database?
   - Current: Triggers for FTS only
   - Could add: Background worker for full sync

3. **Multi-writer**: SQLite is single-writer. How to handle concurrent access?
   - Options: File locking, queue, or external coordination

4. **Retention Policy**: How long to keep events?
   - Current: No automatic cleanup
   - Need: Archive + purge strategy

## UX

1. **Memory Types**: What types should be supported out of the box?
   - Current: general, decision, architecture, implementation
   - Need: Define taxonomy

2. **CLI vs API**: CLI is primary but should we add HTTP API?
   - Pro: Easier integration
   - Con: More complexity

## Governance

1. **Approval Flow**: Is simple proposer=approver sufficient?
   - Could add: Multi-sig, time-locks

2. **Conflict Resolution**: What happens on contradictory decisions?
   - Need: Deprecation strategy
