"""Tests for PII stripping utility."""

from __future__ import annotations

from app.utils.pii import strip_pii, strip_pii_from_scraped_data


class TestStripPii:
    """Tests for PII removal."""

    def test_strips_email(self):
        text = "Contact john.doe@example.com for details"
        result = strip_pii(text)
        assert "john.doe@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_strips_phone_numbers(self):
        text = "Call 0412 345 678 or +61 3 9876 5432"
        result = strip_pii(text)
        assert "0412 345 678" not in result
        assert "+61 3 9876 5432" not in result
        assert "[REDACTED_PHONE]" in result

    def test_strips_tfn(self):
        text = "TFN: 123 456 789"
        result = strip_pii(text)
        assert "123 456 789" not in result
        assert "[REDACTED" in result

    def test_none_input_returns_none(self):
        assert strip_pii(None) is None

    def test_no_pii_passes_through(self):
        text = "Planning application PA-2024-0001 approved"
        assert strip_pii(text) == text


class TestStripPiiFromScrapedData:
    """Tests for PII stripping on full scraped data dicts."""

    def test_strips_from_text_fields(self):
        data = {
            "council_planning_applications_text": "Contact john@test.com",
            "council_meeting_minutes_text": "Call 0412 345 678",
            "zoning_code": "R1Z",
        }
        result = strip_pii_from_scraped_data(data)
        assert "[REDACTED_EMAIL]" in result["council_planning_applications_text"]
        assert "[REDACTED_PHONE]" in result["council_meeting_minutes_text"]
        assert result["zoning_code"] == "R1Z"  # non-text fields untouched

    def test_handles_none_text_fields(self):
        data = {
            "council_planning_applications_text": None,
            "council_meeting_minutes_text": None,
        }
        result = strip_pii_from_scraped_data(data)
        assert result["council_planning_applications_text"] is None
        assert result["council_meeting_minutes_text"] is None
