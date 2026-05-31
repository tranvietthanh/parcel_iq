"""MinIO client for raw scrape data storage.

All raw scraped data (JSON payloads, PDFs) is stored in MinIO before
being written to Postgres.  This provides an audit trail and enables
re-processing without re-scraping.
"""

from __future__ import annotations

import io
import json
import logging
import time

from minio import Minio

from app.config import settings

logger = logging.getLogger(__name__)

# Bucket names
RAW_SCRAPE_BUCKET = "raw-scrape-data"
RAW_PDF_BUCKET = "raw-scrape-cache"

_client: Minio | None = None


def _get_client() -> Minio:
    """Lazy-initialise the MinIO client (singleton)."""
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        # Ensure buckets exist
        for bucket in (RAW_SCRAPE_BUCKET, RAW_PDF_BUCKET):
            if not _client.bucket_exists(bucket):
                _client.make_bucket(bucket)
                logger.info("Created MinIO bucket: %s", bucket)
    return _client


def store_raw_scrape(property_id: str, merged_data: dict) -> str:
    """Store the merged raw JSON payload in MinIO.

    Returns the object key.
    """
    client = _get_client()
    key = f"properties/{property_id}/{int(time.time())}.json"
    data = json.dumps(merged_data, default=str).encode("utf-8")

    client.put_object(
        RAW_SCRAPE_BUCKET,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/json",
    )
    logger.debug("Stored raw scrape: %s/%s", RAW_SCRAPE_BUCKET, key)
    return key


def store_raw_pdf(property_id: str, pdf_bytes: bytes) -> str:
    """Store a raw PDF in MinIO.

    Returns the object key.
    """
    client = _get_client()
    key = f"council-pdfs/{property_id}/{int(time.time())}.pdf"

    client.put_object(
        RAW_PDF_BUCKET,
        key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )
    logger.debug("Stored raw PDF: %s/%s", RAW_PDF_BUCKET, key)
    return key
