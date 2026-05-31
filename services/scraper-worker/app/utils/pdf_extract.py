"""PDF text extraction using pdfminer.six.

Downloads are cached to MinIO by the calling adapter.  This module only
handles byte-stream → text conversion.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str | None:
    """Extract text content from PDF bytes using pdfminer.six.

    Returns
    -------
    Extracted text or ``None`` if extraction fails or yields no content.
    """
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(io.BytesIO(pdf_bytes))
        cleaned = text.strip() if text else None
        return cleaned if cleaned else None
    except Exception:
        logger.exception("Failed to extract text from PDF (%d bytes)", len(pdf_bytes))
        return None
