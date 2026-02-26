# Redaction Tests
# SPDX-License-Identifier: AGPL-3.0

import pytest
from memory_hub.redaction import redact, redact_episode_content, contains_secrets


class TestRedact:
    """Test redaction patterns."""

    def test_api_key(self):
        """API keys redacted."""
        text = "My API key is sk-1234567890abcdefghij"
        result = redact(text)
        assert "sk-1234567890" not in result
        assert "<REDACTED_TOKEN>" in result

    def test_bearer_token(self):
        """Bearer tokens redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
        result = redact(text)
        assert "Bearer" not in result
        assert "<REDACTED_TOKEN>" in result

    def test_email(self):
        """Emails redacted."""
        text = "Contact me at john.doe@example.com"
        result = redact(text)
        assert "john.doe@example.com" not in result
        assert "<REDACTED_EMAIL>" in result

    def test_github_token(self):
        """GitHub tokens redacted."""
        text = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = redact(text)
        assert "ghp_" not in result
        assert "<REDACTED_TOKEN>" in result

    def test_aws_key(self):
        """AWS keys redacted."""
        text = "AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIA" not in result
        assert "<REDACTED_TOKEN>" in result

    def test_hex_string(self):
        """Long hex strings redacted."""
        text = "Hash: abcdef0123456789abcdef0123456789abcdef0123456789abcd"
        result = redact(text)
        assert "abcdef0123456789" not in result
        assert "<REDACTED_HEX>" in result

    def test_password_in_code(self):
        """Password patterns redacted."""
        text = 'password = "supersecret123"'
        result = redact(text)
        assert "supersecret" not in result
        assert "<REDACTED_SECRET>" in result

    def test_safe_text_unchanged(self):
        """Safe text unchanged."""
        text = "This is a normal message with no secrets."
        result = redact(text)
        assert result == text

    def test_max_length(self):
        """Max length truncation."""
        text = "This is a normal message. " * 50
        result = redact(text, max_length=50)
        assert len(result) <= 53  # 50 + "..."
        assert result.endswith("...") or len(result) <= 50

    def test_contains_secrets(self):
        """Secret detection."""
        assert contains_secrets("sk-1234567890abcdefghij")
        assert contains_secrets("contact@email.com")
        assert not contains_secrets("hello world")


class TestRedactEpisodeContent:
    """Test episode content redaction."""

    def test_redact_intent(self):
        """Intent redacted."""
        result = redact_episode_content(
            intent="Fix bug with sk-secret123 key",
            steps=["Step 1"],
            evidence={"commands": [], "artifacts": []}
        )
        assert "sk-secret123" not in result["intent"]
        assert "<REDACTED_TOKEN>" in result["intent"]

    def test_redact_steps(self):
        """Steps redacted."""
        result = redact_episode_content(
            intent="Test",
            steps=["Run test with sk-test1234567890abcdef", "Check contact@example.com"],
            evidence={"commands": [], "artifacts": []}
        )
        assert "sk-test123" not in result["steps"][0]
        assert "contact@example.com" not in result["steps"][1]

    def test_redact_evidence_commands(self):
        """Evidence commands redacted."""
        result = redact_episode_content(
            intent="Test",
            steps=["Test"],
            evidence={"commands": ["curl -H 'Authorization: Bearer token123'"], "artifacts": []}
        )
        assert "Bearer" not in result["evidence"]["commands"][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
