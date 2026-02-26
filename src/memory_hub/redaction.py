# Memory Fabric - Redaction Utilities
# SPDX-License-Identifier: AGPL-3.0

"""
Deterministic redaction utilities for safe memory storage.
No LLM - pure regex-based pattern matching.
"""

import re
from typing import Optional


# Common secret patterns
PATTERNS = [
    # API keys (various services)
    (r'sk-[a-zA-Z0-9]{20,}', '<REDACTED_TOKEN>'),
    (r'sk-[a-zA-Z0-9]+', '<REDACTED_TOKEN>'),  # Any sk- key
    (r'Bearer\s+[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+', '<REDACTED_TOKEN>'),
    (r'Bearer\s+[a-zA-Z0-9\-_]+', '<REDACTED_TOKEN>'),

    # Anthropic
    (r'sk-ant-[a-zA-Z0-9\-_]+', '<REDACTED_TOKEN>'),

    # OpenAI
    (r'OpenAI\s+[a-zA-Z0-9\-_]+', '<REDACTED_TOKEN>'),

    # GitHub tokens
    (r'gh[pousr]_[a-zA-Z0-9]{36,}', '<REDACTED_TOKEN>'),

    # AWS keys
    (r'AKIA[0-9A-Z]{16}', '<REDACTED_TOKEN>'),

    # Explicit secrets
    (r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*[\'"]?[a-zA-Z0-9\-_]{16,}[\'"]?', '<REDACTED_SECRET>'),

    # Emails
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '<REDACTED_EMAIL>'),

    # Long hex strings (likely tokens/keys) - 32+ hex chars
    (r'\b[0-9a-fA-F]{32,}\b', '<REDACTED_HEX>'),

    # Generic password patterns in code
    (r'password\s*[:=]\s*[\'"][^\'"]{4,}[\'"]', '<REDACTED_SECRET>'),
]

# Compile patterns for performance
COMPILED_PATTERNS = [(re.compile(pattern), replacement) for pattern, replacement in PATTERNS]


def redact(text: str, max_length: Optional[int] = None) -> str:
    """
    Redact sensitive patterns from text.

    Args:
        text: Input text to redact
        max_length: Optional max length (truncates if longer, applies AFTER redaction)

    Returns:
        Redacted text
    """
    if not text:
        return text

    result = text
    for pattern, replacement in COMPILED_PATTERNS:
        result = pattern.sub(replacement, result)

    # Truncate if requested (apply AFTER redaction)
    if max_length and len(result) > max_length:
        result = result[:max_length] + "..."

    return result


def redact_episode_content(intent: str, steps: list, evidence: dict) -> dict:
    """
    Redact an episode record before storage.

    Args:
        intent: The intent/prompt
        steps: List of step descriptions
        evidence: Evidence dict with commands, artifacts, logs

    Returns:
        Redacted episode dict
    """
    return {
        "intent": redact(intent),
        "steps": [redact(step) for step in steps],
        "evidence": {
            "commands": [redact(cmd) for cmd in evidence.get("commands", [])],
            "artifacts": evidence.get("artifacts", []),  # Keep file paths
            "logs": redact(evidence.get("logs", "")) if evidence.get("logs") else "",
        }
    }


def contains_secrets(text: str) -> bool:
    """
    Check if text contains potential secrets.

    Args:
        text: Text to check

    Returns:
        True if secrets detected
    """
    if not text:
        return False

    for pattern, _ in COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False
