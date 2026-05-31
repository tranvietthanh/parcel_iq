from __future__ import annotations

import io
from minio import Minio
from minio.error import S3Error

from app.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        if not _client.bucket_exists(settings.REPORT_PDF_BUCKET):
            _client.make_bucket(settings.REPORT_PDF_BUCKET)
    return _client


def build_report_pdf_object_key(report_id: str, variant: str = "full") -> str:
    safe_variant = variant.lower().strip() if variant else "full"
    if safe_variant == "full":
        return f"reports/{report_id}.pdf"
    return f"reports/{report_id}.{safe_variant}.pdf"


def report_pdf_exists(object_key: str) -> bool:
    client = _get_client()
    try:
        client.stat_object(settings.REPORT_PDF_BUCKET, object_key)
        return True
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return False
        raise


def get_report_pdf_bytes(object_key: str) -> bytes:
    client = _get_client()
    response = client.get_object(settings.REPORT_PDF_BUCKET, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def put_report_pdf_bytes(object_key: str, pdf_bytes: bytes) -> None:
    client = _get_client()
    client.put_object(
        settings.REPORT_PDF_BUCKET,
        object_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )


def delete_report_pdf(object_key: str) -> None:
    client = _get_client()
    try:
        client.remove_object(settings.REPORT_PDF_BUCKET, object_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return
        raise
