#!/usr/bin/env bash
# infra/scripts/create_buckets.sh
# Creates required MinIO buckets for local development.
# Requires: mc (MinIO Client) — install via `brew install minio/stable/mc`
#           or `apt install minio-client`

set -euo pipefail

MINIO_ENDPOINT="http://localhost:${MINIO_PORT:-9000}"
MINIO_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-minioadmin}"
REPORT_BUCKET="${REPORT_PDF_BUCKET:-property-report-pdfs}"

minio-client alias set parceliq "$MINIO_ENDPOINT" "$MINIO_USER" "$MINIO_PASS" --api S3v4

for BUCKET in raw-scrape-cache parceliq-db-backups "$REPORT_BUCKET"; do
    if minio-client ls parceliq/"$BUCKET" &>/dev/null; then
        echo "Bucket '$BUCKET' already exists."
    else
        minio-client mb parceliq/"$BUCKET"
        echo "Created bucket '$BUCKET'."
    fi
done

echo "Done. MinIO buckets ready."
