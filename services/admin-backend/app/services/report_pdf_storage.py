"""Report PDF storage helpers.

Re-exports canonical MinIO storage functions from `pdf_renderer` to ensure
consistent versioned object keys and storage operations across services.
"""

from __future__ import annotations

from pdf_renderer import (
    build_report_pdf_object_key,
    delete_report_pdf,
    get_report_pdf_bytes,
    put_report_pdf_bytes,
    report_pdf_exists,
)

__all__ = [
    "build_report_pdf_object_key",
    "delete_report_pdf",
    "get_report_pdf_bytes",
    "put_report_pdf_bytes",
    "report_pdf_exists",
]

