from __future__ import annotations

import io
import os
from minio import Minio
from minio.error import S3Error

_client: Minio | None = None


def _get_client() -> Minio:
    """Get MinIO client (lazy singleton)."""
    global _client
    if _client is None:
        _client = Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
        )
        bucket = os.getenv("REPORT_PDF_BUCKET", "property-reports")
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket)
    return _client


def build_report_pdf_object_key(report_id: str, variant: str = "full") -> str:
    safe_variant = variant.lower().strip() if variant else "full"
    if safe_variant == "full":
        return f"reports/{report_id}.pdf"
    return f"reports/{report_id}.{safe_variant}.pdf"


def report_pdf_exists(object_key: str) -> bool:
    """Check if a PDF exists in MinIO."""
    client = _get_client()
    bucket = os.getenv("REPORT_PDF_BUCKET", "property-reports")
    try:
        client.stat_object(bucket, object_key)
        return True
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return False
        raise


def get_report_pdf_bytes(object_key: str) -> bytes:
    """Retrieve PDF bytes from MinIO."""
    client = _get_client()
    bucket = os.getenv("REPORT_PDF_BUCKET", "property-reports")
    response = client.get_object(bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def put_report_pdf_bytes(object_key: str, pdf_bytes: bytes) -> None:
    """Store PDF bytes in MinIO."""
    client = _get_client()
    bucket = os.getenv("REPORT_PDF_BUCKET", "property-reports")
    client.put_object(
        bucket,
        object_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )


def delete_report_pdf(object_key: str) -> None:
    """Delete PDF from MinIO."""
    client = _get_client()
    bucket = os.getenv("REPORT_PDF_BUCKET", "property-reports")
    try:
        client.remove_object(bucket, object_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return
        raise
