# Memory Fabric - Event Store (JSONL Append-Only)
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations
"""
Append-only JSONL event store as the truth source for Memory Fabric.
Events are immutable and form the foundation of the event sourcing architecture.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class EventStore:
    """
    Append-only JSONL event store.

    Events are the single source of truth. All state is derived from events.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.events_file = self.data_dir / "events.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.events_file.exists():
            self.events_file.touch()

    def _generate_event_id(self) -> str:
        return str(uuid.uuid4())

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def append(self, event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
        """
        Append an event to the store.

        Args:
            event_type: Type of event (e.g., "memory_created", "memory_updated")
            payload: Event data
            metadata: Optional metadata (correlation_id, causation_id, etc.)

        Returns:
            Event ID
        """
        event = {
            "event_id": self._generate_event_id(),
            "timestamp": self._timestamp(),
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {}
        }

        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        return event["event_id"]

    def read_all(self) -> Iterator[dict[str, Any]]:
        """Read all events in chronological order."""
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)

    def read_from(self, start_timestamp: str) -> Iterator[dict[str, Any]]:
        """Read events from a specific timestamp onwards."""
        for event in self.read_all():
            if event["timestamp"] >= start_timestamp:
                yield event

    def get_by_type(self, event_type: str) -> Iterator[dict[str, Any]]:
        """Get all events of a specific type."""
        for event in self.read_all():
            if event["event_type"] == event_type:
                yield event

    def get_by_correlation(self, correlation_id: str) -> Iterator[dict[str, Any]]:
        """Get all events with a specific correlation ID."""
        for event in self.read_all():
            if event.get("metadata", {}).get("correlation_id") == correlation_id:
                yield event

    def count(self) -> int:
        """Count total events."""
        with open(self.events_file, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search events by content (simple substring match in payload)."""
        results = []
        query_lower = query.lower()
        for event in self.read_all():
            payload_str = json.dumps(event.get("payload", {}), ensure_ascii=False).lower()
            if query_lower in payload_str:
                results.append(event)
        return results

    def export(self, output_file: Path, redact: bool = False):
        """Export all events to a file."""
        with open(output_file, "w", encoding="utf-8") as out:
            for event in self.read_all():
                if redact:
                    # Redact sensitive fields
                    event = self._redact_event(event)
                out.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _redact_event(self, event: dict) -> dict:
        """Redact sensitive information from event."""
        sensitive_keys = {"password", "token", "secret", "api_key", "credential"}
        payload = event.get("payload", {})
        if isinstance(payload, dict):
            for key in list(payload.keys()):
                if any(s in key.lower() for s in sensitive_keys):
                    payload[key] = "[REDACTED]"
        return event


# Convenience functions
def create_event_store(data_dir: str | Path) -> EventStore:
    """Create or open an event store."""
    return EventStore(Path(data_dir))
