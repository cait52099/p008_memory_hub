#!/usr/bin/env python3
"""Regression test for project override with many global memories."""
import sys
import os
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory_hub.database import MemoryDatabase
from memory_hub.retrieval import HybridRetrieval
from memory_hub.context_assembler import ContextAssembler


def test_project_override_with_many_global_memories():
    """Test that project override retrieves project memories even with many global memories."""
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    try:
        # Initialize database
        db_path = os.path.join(temp_dir, 'test.db')
        db = MemoryDatabase(db_path)

        # Insert many global memories of type "note"
        # These should NOT appear in project results
        for i in range(50):
            db.insert_memory(
                memory_id=f"global_{i}",
                content=f"Global memory content {i}",
                memory_type="note",
                source="other_project",
                importance=0.5
            )

        # Insert a few project-specific memories
        # These SHOULD appear in project results
        project_name = "p009_memory_fabric_global"
        for i in range(3):
            db.insert_memory(
                memory_id=f"project_{i}",
                content=f"Project-specific memory about Memory Fabric {i}",
                memory_type="note",
                source=project_name,
                importance=0.8  # Higher importance
            )

        # Create retrieval engine
        retrieval = HybridRetrieval(db, None, None)

        # Test: Query with project override
        # FTS will likely miss (content differs), but fallback should work
        results = retrieval.search(
            query="Memory Fabric project",
            top_k=10,
            memory_type="note",
            source=project_name
        )

        # Verify: Should return project memories even with many global memories
        project_results = [r for r in results if r.source == project_name]

        print(f"Total results: {len(results)}")
        print(f"Project results: {len(project_results)}")

        if len(project_results) == 0:
            print("FAIL: No project memories returned!")
            return False

        print("PASS: Project memories retrieved despite many global memories")
        for r in project_results[:3]:
            print(f"  - {r.memory_id}: {r.content[:50]}...")

        return True

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    success = test_project_override_with_many_global_memories()
    sys.exit(0 if success else 1)
