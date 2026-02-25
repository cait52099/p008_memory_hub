# Memory Fabric - Episode Memory System
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
Episode Memory system for storing and retrieving execution episodes.

An episode captures the outcome of an agent execution attempt, including:
- Intent (what was attempted)
- Cues (entities, errors, tools, files involved)
- Path (ordered steps taken)
- Outcome (success/failure/mixed)
- Score (0-100)
- Valence (-1 to 1)
- Cost metrics
- Evidence (commands, artifacts, logs)
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

# English stopwords to filter during fingerprinting
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "just",
    "and", "but", "if", "or", "because", "until", "while", "although",
    "this", "that", "these", "those", "it", "its", "what", "which",
    "who", "whom", "whose", "add", "create", "fix", "update", "remove",
    "delete", "make", "get", "set", "put", "implement", "refactor"
}

# Error signature penalties
ERROR_SIGNATURE_PENALTIES = {
    "false green": -20,
    "false_green": -20,
    "http 401": -15,
    "http_401": -15,
    "unauthorized": -15,
    "data loss": -40,
    "data_loss": -40,
    "permission denied": -25,
    "permission_denied": -25,
    "timeout": -10,
    "deadlock": -30,
    "race condition": -25,
    "race_condition": -25,
    "null pointer": -20,
    "null_pointer": -20,
    "type error": -15,
    "type_error": -15,
}


def intent_fingerprint(prompt: str, project_id: str) -> str:
    """
    Generate a robust fingerprint for an intent, normalized to be
    resistant to rewordings.

    Args:
        prompt: The user's prompt/intent
        project_id: The project identifier

    Returns:
        A fingerprint string: "{project_id}::{'+'.join(sorted(tokens[:10]))}"
    """
    # Normalize: lowercase
    normalized = prompt.lower()

    # Remove punctuation
    normalized = re.sub(r"[^\w\s]", " ", normalized)

    # Extract tokens (alphanumeric)
    tokens = normalized.split()

    # Filter stopwords and short tokens
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]

    # Deduplicate while preserving order
    seen = set()
    unique_tokens = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique_tokens.append(t)

    # Take top 10 stable tokens
    stable_tokens = unique_tokens[:10]

    # Generate fingerprint
    fingerprint = f"{project_id}::{'+'.join(sorted(stable_tokens))}"

    return fingerprint


def calculate_score(
    outcome: str,
    attempts: int,
    rollbacks: int,
    error_signatures: list[str],
    has_regression_test: bool = False,
    has_release: bool = False
) -> dict:
    """
    Deterministic scoring V1 for episode evaluation.

    Args:
        outcome: "success", "failure", or "mixed"
        attempts: Number of attempts to complete
        rollbacks: Number of rollbacks performed
        error_signatures: List of error pattern strings
        has_regression_test: Whether a regression test was added
        has_release: Whether this was released

    Returns:
        dict with keys: score (0-100), valence (-1 to 1), strength (0-1)
    """
    # Base score by outcome
    outcome_bases = {
        "success": 85,
        "mixed": 60,
        "failure": 25
    }
    score = outcome_bases.get(outcome, 50)

    # Penalty for attempts > 1
    if attempts > 1:
        score -= (attempts - 1) * 5

    # Penalty for rollbacks
    score -= rollbacks * 10

    # Penalty for error signatures
    for sig in error_signatures:
        sig_lower = sig.lower()
        for pattern, penalty in ERROR_SIGNATURE_PENALTIES.items():
            if pattern in sig_lower:
                score += penalty
                break

    # Bonuses
    if has_regression_test:
        score += 10
    if has_release:
        score += 5

    # Clamp to 0-100
    score = max(0, min(100, score))

    # Valence: clip((score-50)/50, -1, 1)
    valence = (score - 50) / 50
    valence = max(-1.0, min(1.0, valence))

    # Strength: initial based on outcome
    if outcome == "success":
        strength = 0.5
    elif outcome == "failure":
        strength = 0.7
    else:  # mixed
        strength = 0.6

    return {
        "score": score,
        "valence": valence,
        "strength": strength
    }


def store_episode(episode: dict, db, events) -> str:
    """
    Store an episode as a memory.

    Args:
        episode: Episode dict with all required fields
        db: MemoryDatabase instance
        events: EventStore instance

    Returns:
        The memory_id of the stored episode
    """
    from pathlib import Path

    episode_id = episode.get("episode_id", str(uuid.uuid4()))
    project_id = episode.get("project_id", "unknown")
    fingerprint = episode.get("intent_fingerprint", "")
    outcome = episode.get("outcome", "mixed")

    # Serialize episode content as JSON
    content = json.dumps(episode, ensure_ascii=False)

    # Build keys for indexing
    keys = [
        "episode",
        f"intent:{fingerprint}",
        f"project:{project_id}",
        f"outcome:{outcome}",
    ]

    # Add cue keys
    cues = episode.get("cues", {})
    for entity in cues.get("entities", []):
        keys.append(f"entity:{entity}")
    for error in cues.get("error_signatures", []):
        keys.append(f"error:{error}")
    for tool in cues.get("tools", []):
        keys.append(f"tool:{tool}")
    for file in cues.get("files", []):
        keys.append(f"file:{file}")

    # Importance based on score
    importance = episode.get("score", 50) / 100.0

    # Source: episode:<project_id>
    source = f"episode:{project_id}"

    # Record event
    event_id = events.append("episode_stored", {
        "episode_id": episode_id,
        "project_id": project_id,
        "outcome": outcome,
        "score": episode.get("score"),
    }, metadata={
        "intent_fingerprint": fingerprint,
    })

    # Store in database
    memory_id = db.insert_memory(
        memory_id=episode_id,
        content=content,
        memory_type="episode",
        source=source,
        importance=importance,
        metadata={
            "keys": keys,
            "intent_fingerprint": fingerprint,
            "project_id": project_id,
            "outcome": outcome,
            "score": episode.get("score"),
        },
        event_id=event_id
    )

    return episode_id


def retrieve_episodes(project_id: str, prompt: str, top_k: int, db) -> list[dict]:
    """
    Find episodes by fingerprint match.

    Args:
        project_id: The project identifier
        prompt: The query prompt to match
        top_k: Number of episodes to retrieve
        db: MemoryDatabase instance

    Returns:
        List of episode dicts
    """
    # Generate fingerprint from prompt
    fingerprint = intent_fingerprint(prompt, project_id)

    # Get all episode memories for this project
    episodes = db.get_memories_by_type_and_source(
        memory_type="episode",
        source=f"episode:{project_id}",
        limit=top_k * 2  # Get more to filter
    )

    # Parse and filter by fingerprint similarity
    results = []
    for mem in episodes:
        try:
            episode = json.loads(mem["content"])
            # Include if same project and similar intent
            if episode.get("project_id") == project_id:
                results.append(episode)
        except json.JSONDecodeError:
            continue

    # Sort by score descending
    results.sort(key=lambda e: e.get("score", 0), reverse=True)

    return results[:top_k]


def assemble_episodes_context(
    query: str,
    project_id: str,
    top_k: int,
    db
) -> str:
    """
    Assemble context from successful and failed episodes.

    Returns markdown with:
    - ## Best Known Path (top success episodes by score)
    - ## Pitfalls to Avoid (top failure episodes by score)

    Args:
        query: The query prompt
        project_id: The project identifier
        top_k: Number of episodes per category
        db: MemoryDatabase instance

    Returns:
        Markdown string with episode context
    """
    # Get all episode memories for this project
    all_episodes = db.get_memories_by_type_and_source(
        memory_type="episode",
        source=f"episode:{project_id}",
        limit=top_k * 4
    )

    # Parse episodes
    episodes = []
    for mem in all_episodes:
        try:
            episode = json.loads(mem["content"])
            if episode.get("project_id") == project_id:
                episodes.append(episode)
        except json.JSONDecodeError:
            continue

    # Separate by outcome
    successes = [e for e in episodes if e.get("outcome") == "success"]
    failures = [e for e in episodes if e.get("outcome") == "failure"]

    # Sort by score
    successes.sort(key=lambda e: e.get("score", 0), reverse=True)
    failures.sort(key=lambda e: e.get("score", 0), reverse=True)

    # Take top_k
    successes = successes[:top_k]
    failures = failures[:top_k]

    lines = []

    # Best Known Path (successes)
    if successes:
        lines.append("## Best Known Path")
        lines.append("")
        for i, ep in enumerate(successes, 1):
            score = ep.get("score", 0)
            intent = ep.get("intent", "")[:100]
            path = ep.get("path", [])
            cues = ep.get("cues", {})

            lines.append(f"### {i}. {intent}")
            lines.append(f"**Score:** {score} | **Attempts:** {ep.get('cost', {}).get('attempts', 1)}")
            lines.append("")

            if path:
                lines.append("**Path:**")
                for step in path[:5]:  # Limit steps
                    lines.append(f"- {step}")
                lines.append("")

            if cues.get("tools"):
                lines.append(f"**Tools:** {', '.join(cues.get('tools', [])[:5])}")
            if cues.get("files"):
                lines.append(f"**Files:** {', '.join(cues.get('files', [])[:5])}")

            lines.append("")

    # Pitfalls to Avoid (failures)
    if failures:
        lines.append("## Pitfalls to Avoid")
        lines.append("")
        for i, ep in enumerate(failures, 1):
            score = ep.get("score", 0)
            intent = ep.get("intent", "")[:100]
            errors = ep.get("cues", {}).get("error_signatures", [])

            lines.append(f"### {i}. {intent}")
            lines.append(f"**Score:** {score}")
            lines.append("")

            if errors:
                lines.append(f"**Errors:** {', '.join(errors[:3])}")
                lines.append("")

            path = ep.get("path", [])
            if path:
                lines.append("**What went wrong:**")
                for step in path[:3]:
                    lines.append(f"- {step}")
                lines.append("")

    if not lines:
        return "No episode history found for this project."

    return "\n".join(lines)


def create_episode(
    episode_id: str | None,
    project_id: str,
    intent: str,
    cues: dict,
    path: list[str],
    outcome: str,
    attempts: int = 1,
    rollbacks: int = 0,
    time_to_green_sec: int | None = None,
    evidence: dict | None = None,
    has_regression_test: bool = False,
    has_release: bool = False,
) -> dict:
    """
    Create a complete episode dict with scoring.

    Args:
        episode_id: Unique ID (auto-generated if None)
        project_id: Project identifier
        intent: The original intent/prompt
        cues: Dict with entities, error_signatures, tools, files
        path: Ordered list of step descriptions
        outcome: "success", "failure", or "mixed"
        attempts: Number of attempts
        rollbacks: Number of rollbacks
        time_to_green_sec: Time to successful completion
        evidence: Dict with commands, artifacts, commit, logs
        has_regression_test: Whether regression test was added
        has_release: Whether this was released

    Returns:
        Complete episode dict
    """
    now = datetime.now(timezone.utc).isoformat()

    # Generate fingerprint
    fingerprint = intent_fingerprint(intent, project_id)

    # Calculate score
    scoring = calculate_score(
        outcome=outcome,
        attempts=attempts,
        rollbacks=rollbacks,
        error_signatures=cues.get("error_signatures", []),
        has_regression_test=has_regression_test,
        has_release=has_release,
    )

    episode = {
        "episode_id": episode_id or str(uuid.uuid4()),
        "project_id": project_id,
        "intent": intent,
        "intent_fingerprint": fingerprint,
        "cues": {
            "entities": cues.get("entities", []),
            "error_signatures": cues.get("error_signatures", []),
            "tools": cues.get("tools", []),
            "files": cues.get("files", []),
        },
        "path": path,
        "outcome": outcome,
        "score": scoring["score"],
        "valence": scoring["valence"],
        "cost": {
            "attempts": attempts,
            "rollbacks": rollbacks,
            "time_to_green_sec": time_to_green_sec,
        },
        "evidence": evidence or {
            "commands": [],
            "artifacts": [],
            "commit": None,
            "logs": None,
        },
        "strength": scoring["strength"],
        "created_at": now,
        "updated_at": now,
    }

    return episode
