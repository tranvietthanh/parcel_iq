"""PII stripping utility.

Removes personally identifiable information from scraped text before
persisting to the database.  This is a legal requirement per
docs/07-legal-compliance.md.
"""

from __future__ import annotations

import re


# Common PII patterns
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+61|0)\s?[2-478](?:\s?\d){7,8}"  # AU phone numbers
)
_TFN_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\b")  # Tax File Numbers
_ABN_RE = re.compile(r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b")  # ABN (11 digits)


def strip_pii(text: str | None) -> str | None:
    """Remove PII patterns from *text*.

    Replaces email addresses, phone numbers, TFNs, and ABNs with
    ``[REDACTED]``.  Returns ``None`` if input is ``None``.
    """
    if text is None:
        return None

    result = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    result = _PHONE_RE.sub("[REDACTED_PHONE]", result)
    result = _TFN_RE.sub("[REDACTED_TFN]", result)
    # ABN pattern overlaps with TFN — run after TFN
    result = _ABN_RE.sub("[REDACTED_ABN]", result)

    return result


def strip_pii_from_scraped_data(data: dict) -> dict:
    """Strip PII recursively from all string values in scraped data.

    Modifies and returns *data* in-place for efficiency.
    """
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = strip_pii(value)
        elif isinstance(value, dict):
            data[key] = strip_pii_from_scraped_data(value)
        elif isinstance(value, list):
            data[key] = [
                strip_pii_from_scraped_data(item)
                if isinstance(item, dict)
                else strip_pii(item)
                if isinstance(item, str)
                else item
                for item in value
            ]

    return data
