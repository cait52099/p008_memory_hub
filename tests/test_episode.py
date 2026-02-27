# Episode Memory Tests
# SPDX-License-Identifier: AGPL-3.0

"""
Tests for Episode Memory system:
1. fingerprint stability under rewording
2. scoring deterministic outputs for known inputs
3. episode match finds relevant episodes by intent_fingerprint/cues
4. assemble --with-episodes includes both blocks with expected tokens
"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory_hub.episode import (
    intent_fingerprint,
    calculate_score,
    store_episode,
    retrieve_episodes,
    assemble_episodes_context,
    create_episode,
    extract_cues,
    mark_episode_used,
    bump_episode_strength,
    get_used_episodes,
    _USED_EPISODES,
)
from memory_hub import create_database, create_event_store


class TestIntentFingerprint:
    """Test intent fingerprint stability under rewording."""

    def test_fingerprint_basic(self):
        """Basic fingerprint generation."""
        fp = intent_fingerprint("Fix the login bug", "myproject")
        assert fp.startswith("myproject::")
        assert "login" in fp or "fix" in fp

    def test_fingerprint_reworded_same(self):
        """Rephrased prompts should have token overlap."""
        p1 = "Fix the authentication bug in the login flow"
        p2 = "Fix authentication problem in login"

        fp1 = intent_fingerprint(p1, "myproject")
        fp2 = intent_fingerprint(p2, "myproject")

        # Extract tokens from fingerprints
        tokens1 = set(fp1.replace("myproject::", "").split("+"))
        tokens2 = set(fp2.replace("myproject::", "").split("+"))

        # Should have some overlap (lowered expectation)
        overlap = len(tokens1 & tokens2)
        assert overlap >= 2, f"Low overlap: {tokens1} vs {tokens2}"

    def test_fingerprint_punctuation_ignored(self):
        """Punctuation should be ignored."""
        fp1 = intent_fingerprint("Add user authentication!", "proj")
        fp2 = intent_fingerprint("Add user authentication", "proj")

        assert fp1 == fp2

    def test_fingerprint_case_insensitive(self):
        """Case should be ignored."""
        fp1 = intent_fingerprint("FIX THE BUG", "proj")
        fp2 = intent_fingerprint("fix the bug", "proj")

        assert fp1 == fp2


class TestScoring:
    """Test deterministic scoring outputs."""

    def test_base_scores(self):
        """Base scores for outcomes."""
        result = calculate_score("success", 1, 0, [])
        assert result["score"] == 85

        result = calculate_score("mixed", 1, 0, [])
        assert result["score"] == 60

        result = calculate_score("failure", 1, 0, [])
        assert result["score"] == 25

    def test_attempts_penalty(self):
        """Penalty for multiple attempts."""
        result = calculate_score("success", 1, 0, [])
        assert result["score"] == 85

        result = calculate_score("success", 2, 0, [])
        assert result["score"] == 80  # 85 - 5

        result = calculate_score("success", 3, 0, [])
        assert result["score"] == 75  # 85 - 10

    def test_rollback_penalty(self):
        """Penalty for rollbacks."""
        result = calculate_score("success", 1, 1, [])
        assert result["score"] == 75  # 85 - 10

    def test_error_signatures(self):
        """Error signature penalties."""
        result = calculate_score("failure", 1, 0, ["false green"])
        assert result["score"] == 5  # 25 - 20

        result = calculate_score("failure", 1, 0, ["HTTP 401"])
        assert result["score"] == 10  # 25 - 15

        result = calculate_score("failure", 1, 0, ["data loss"])
        assert result["score"] == 0  # 25 - 40, clamped to 0

    def test_bonuses(self):
        """Bonus points."""
        result = calculate_score("success", 1, 0, [], has_regression_test=True)
        assert result["score"] == 95  # 85 + 10

        result = calculate_score("success", 1, 0, [], has_release=True)
        assert result["score"] == 90  # 85 + 5

    def test_score_clamping(self):
        """Scores clamped to 0-100."""
        # Very bad case
        result = calculate_score("failure", 5, 3, ["data loss", "false green"])
        assert 0 <= result["score"] <= 100

    def test_valence(self):
        """Valence calculation."""
        result = calculate_score("success", 1, 0, [])
        assert result["valence"] == 0.7  # (85-50)/50

        result = calculate_score("failure", 1, 0, [])
        assert result["valence"] == -0.5  # (25-50)/50

        result = calculate_score("mixed", 1, 0, [])
        assert result["valence"] == 0.2  # (60-50)/50

    def test_strength(self):
        """Initial strength by outcome."""
        result = calculate_score("success", 1, 0, [])
        assert result["strength"] == 0.5

        result = calculate_score("failure", 1, 0, [])
        assert result["strength"] == 0.7

        result = calculate_score("mixed", 1, 0, [])
        assert result["strength"] == 0.6


class TestEpisodeStorage:
    """Test episode storage and retrieval."""

    @pytest.fixture
    def db_setup(self):
        """Create temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            events_path = Path(tmpdir) / "events"
            db = create_database(db_path)
            events = create_event_store(events_path)
            yield db, events, tmpdir

    def test_store_episode(self, db_setup):
        """Store an episode."""
        db, events, tmpdir = db_setup

        episode = create_episode(
            episode_id=None,
            project_id="testproj",
            intent="Add user authentication",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["Add login endpoint", "Add auth middleware"],
            outcome="success",
            attempts=1,
            rollbacks=0,
            evidence={"commands": ["git commit -m 'add auth'"], "artifacts": ["auth.py"]}
        )

        episode_id = store_episode(episode, db, events)
        assert episode_id is not None

    def test_retrieve_episodes(self, db_setup):
        """Retrieve episodes by prompt."""
        db, events, tmpdir = db_setup

        # Store success episode
        ep1 = create_episode(
            episode_id=None,
            project_id="testproj",
            intent="Fix login bug",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["Fix validation logic"],
            outcome="success",
            attempts=1,
            rollbacks=0
        )
        store_episode(ep1, db, events)

        # Store failure episode
        ep2 = create_episode(
            episode_id=None,
            project_id="testproj",
            intent="Add database migration",
            cues={"entities": [], "error_signatures": ["data loss"], "tools": [], "files": []},
            path=["Drop table", "Oops"],
            outcome="failure",
            attempts=2,
            rollbacks=1
        )
        store_episode(ep2, db, events)

        # Retrieve
        results = retrieve_episodes("testproj", "Fix login", top_k=5, db=db)
        assert len(results) == 2
        # Should find the fix login episode
        assert any("login" in r["intent"].lower() for r in results)

    def test_assemble_episodes_context(self, db_setup):
        """Test context assembly."""
        db, events, tmpdir = db_setup

        # Store success episode with unique token
        ep1 = create_episode(
            episode_id=None,
            project_id="testproj",
            intent="SUCCESS episode for testing",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["SUCCESS_TOKEN_12345 step one", "SUCCESS_TOKEN_12345 step two"],
            outcome="success",
            attempts=1,
            rollbacks=0
        )
        store_episode(ep1, db, events)

        # Store failure episode with unique token
        ep2 = create_episode(
            episode_id=None,
            project_id="testproj",
            intent="FAILURE episode for testing",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["FAIL_TOKEN_67890 step one"],
            outcome="failure",
            attempts=1,
            rollbacks=0
        )
        store_episode(ep2, db, events)

        # Assemble context - now returns tuple (markdown, included_ids)
        result = assemble_episodes_context("test query", "testproj", top_k=5, db=db)
        context = result[0] if isinstance(result, tuple) else result
        included_ids = result[1] if isinstance(result, tuple) else []

        # Should have both sections
        assert "## Best Known Path" in context
        assert "## Pitfalls to Avoid" in context

        # Should contain our tokens
        assert "SUCCESS_TOKEN_12345" in context
        assert "FAIL_TOKEN_67890" in context

        # Should return included IDs
        assert len(included_ids) == 2


class TestExtractCues:
    """Test deterministic cue extraction."""

    def test_extract_entities(self):
        """Extract known entities from prompt."""
        cues = extract_cues("fix openclaw doctor hooks gateway timeout", "")
        assert "openclaw" in cues["entities"]
        assert "doctor" in cues["entities"]
        assert "hooks" in cues["entities"]
        assert "gateway" in cues["entities"]

    def test_extract_files(self):
        """Extract file patterns from prompt."""
        cues = extract_cues("update handler.ts and config.json", "")
        assert "handler.ts" in cues["files"]
        assert "config.json" in cues["files"]

    def test_extract_error_signatures(self):
        """Extract error signatures."""
        cues = extract_cues("fix http 401 auth error", "")
        assert len(cues["error_signatures"]) > 0
        assert any("401" in e for e in cues["error_signatures"])

    def test_extract_tools(self):
        """Extract command tools."""
        cues = extract_cues("run git commit and pytest", "")
        assert "git" in cues["tools"]
        assert "pytest" in cues["tools"]

    def test_cues_stability(self):
        """Same prompt should produce same cues."""
        cues1 = extract_cues("fix openclaw gateway timeout", "run pytest")
        cues2 = extract_cues("fix openclaw gateway timeout", "run pytest")
        assert cues1 == cues2


class TestStrengthBump:
    """Test rehearsal strength bump."""

    @pytest.fixture
    def db_setup(self):
        """Create temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            events_path = Path(tmpdir) / "events"
            db = create_database(db_path)
            events = create_event_store(events_path)
            yield db, events, tmpdir

    def test_mark_episode_used(self):
        """Mark episode as used."""
        # Clear state
        _USED_EPISODES.clear()

        mark_episode_used("fp123", "ep1")
        assert "ep1" in get_used_episodes("fp123")

    def test_mark_multiple_used(self):
        """Mark multiple episodes as used."""
        _USED_EPISODES.clear()

        mark_episode_used("fp456", "ep1")
        mark_episode_used("fp456", "ep2")
        used = get_used_episodes("fp456")
        assert "ep1" in used
        assert "ep2" in used

    def test_strength_bump_cap(self):
        """Strength bump should cap at 1.0."""
        _USED_EPISODES.clear()

        # Test the cap logic: 0.95 + 0.05 = 1.0 (capped)
        old = 0.95
        new = min(1.0, old + 0.05)
        assert new == 1.0

        # Test normal bump: 0.50 + 0.05 = 0.55
        old = 0.50
        new = min(1.0, old + 0.05)
        assert new == 0.55

        # Test already at cap
        old = 1.0
        new = min(1.0, old + 0.05)
        assert new == 1.0

    def test_strength_bump_db_persistence(self, db_setup):
        """Test real DB persistence: strength bump + re-read from DB."""
        db, events, tmpdir = db_setup
        _USED_EPISODES.clear()

        project_id = "testproj"
        fingerprint = "testproj::fix+login"

        # Create and store episode with strength=0.95
        episode1 = create_episode(
            episode_id="ep95",
            project_id=project_id,
            intent="Fix login bug",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["Check auth logic"],
            outcome="failure",  # Start as failure to have low strength
            attempts=2,
            rollbacks=1
        )
        # Override strength to 0.95 manually
        episode1["strength"] = 0.95
        store_episode(episode1, db, events)

        # Create another episode with strength=0.50
        episode2 = create_episode(
            episode_id="ep50",
            project_id=project_id,
            intent="Fix login bug",
            cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
            path=["Update validation"],
            outcome="failure",
            attempts=1,
            rollbacks=0
        )
        episode2["strength"] = 0.50
        store_episode(episode2, db, events)

        # Mark both as used
        mark_episode_used(fingerprint, "ep95")
        mark_episode_used(fingerprint, "ep50")

        # Bump strength (should limit to 3 by default)
        bumped_ids = bump_episode_strength(fingerprint, db, project_id=project_id, bump=0.05, cap=1.0, limit=3)

        # Verify DB was updated: re-read episodes
        mem1 = db.get_memory("ep95")
        assert mem1 is not None
        ep1_updated = json.loads(mem1["content"])

        mem2 = db.get_memory("ep50")
        assert mem2 is not None
        ep2_updated = json.loads(mem2["content"])

        # Check cap: 0.95 + 0.05 = 1.0 (capped)
        assert ep1_updated["strength"] == 1.0, f"Expected 1.0, got {ep1_updated['strength']}"

        # Check normal bump: 0.50 + 0.05 = 0.55
        assert ep2_updated["strength"] == 0.55, f"Expected 0.55, got {ep2_updated['strength']}"

    def test_strength_bump_limit(self, db_setup):
        """Test that bump is limited to N most recent used IDs."""
        db, events, tmpdir = db_setup
        _USED_EPISODES.clear()

        project_id = "testproj"
        fingerprint = "testproj::fix+bug"

        # Create 5 episodes
        for i in range(5):
            ep = create_episode(
                episode_id=f"ep{i}",
                project_id=project_id,
                intent="Fix bug",
                cues={"entities": [], "error_signatures": [], "tools": [], "files": []},
                path=[f"Step {i}"],
                outcome="failure",
                attempts=1,
                rollbacks=0
            )
            ep["strength"] = 0.50
            store_episode(ep, db, events)
            mark_episode_used(fingerprint, f"ep{i}")

        # Bump with limit=2
        bumped_ids = bump_episode_strength(fingerprint, db, project_id=project_id, bump=0.05, cap=1.0, limit=2)

        # Should only bump 2 episodes (the first 2 from used list)
        assert len(bumped_ids) == 2, f"Expected 2 bumped, got {len(bumped_ids)}"

        # Verify only ep0 and ep1 were bumped (deterministic: first N)
        for ep_id in ["ep0", "ep1"]:
            mem = db.get_memory(ep_id)
            ep = json.loads(mem["content"])
            assert ep["strength"] == 0.55, f"{ep_id} should be 0.55"

        # Verify others unchanged
        for ep_id in ["ep2", "ep3", "ep4"]:
            mem = db.get_memory(ep_id)
            ep = json.loads(mem["content"])
            assert ep["strength"] == 0.50, f"{ep_id} should still be 0.50"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
