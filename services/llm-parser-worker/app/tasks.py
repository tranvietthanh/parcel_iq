"""Celery tasks for the LLM parser worker.

Main task: :func:`parse_with_llm` — takes raw scraped data from a property
report, sends it to Gemini for structured extraction, validates with
Pydantic v2, scores confidence, and upserts results.

Scheduled tasks: :func:`trigger_state_refresh` (monthly per state),
:func:`check_dlq` (every 15 min — retries stuck reports).
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.celery_app import celery_app
from app.config import settings
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.user_prompt import build_user_prompt
from app.schemas.confidence import compute_confidence
from app.schemas.llm_output import LlmOutput
from app.services.db import get_db_connection
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

STATE_REFRESH_BATCH_SIZE = 500
MAX_DLQ_RETRIES = 5


def _active_model_name() -> str:
    """Return the configured OpenAI model name."""
    return settings.OPENAI_MODEL


def _extract_json_payload(raw_response: str) -> str:
    """Extract a JSON object string from common LLM response wrappers.

    Handles cases like Markdown fences (```json ... ```), leading/trailing
    prose, and UTF-8 BOM. If no wrapper is detected, returns the original
    stripped response.
    """
    text = (raw_response or "").lstrip("\ufeff").strip()

    # Fast path: fully fenced response.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    # Embedded fenced block inside additional prose.
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1).strip()

    # Fallback: attempt to isolate the outermost JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidate = text[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass

    return text


# ── Main LLM parsing task ──────────────────────────────────────────────────


@celery_app.task(
    bind=True,
    name="app.tasks.parse_with_llm",
    queue="llm_processing_queue",
    max_retries=3,
    default_retry_delay=65,  # 1-min rate window + 5s buffer
    acks_late=True,
)
def parse_with_llm(
    self,
    property_id: str,
    property_report_id: str,
    address_string: str,
) -> None:
    """Parse raw scraped data with the configured provider and store insights.

    Steps:
        1. Mark report as PROCESSING
        2. Fetch raw_scraped_data from property_reports
        3. Build prompt from raw data
        4. Call provider API (blocks on rate limiter)
        5. Validate response with Pydantic v2
        6. Compute confidence scores
        7. Determine status (READY)
        8. Upsert results into property_reports
    """
    db = get_db_connection()
    try:
        # 1. Mark as PROCESSING
        with db.cursor() as cur:
            cur.execute(
                "UPDATE property_reports SET status='PROCESSING', updated_at=NOW() "
                "WHERE id=%s",
                (property_report_id,),
            )
            db.commit()

        # 2. Fetch raw scraped data
        with db.cursor() as cur:
            cur.execute(
                "SELECT raw_scraped_data FROM property_reports WHERE id=%s",
                (property_report_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"No report found for id={property_report_id}")
            raw_data: dict = row["raw_scraped_data"]

        # 3. Build prompt
        user_prompt = build_user_prompt(address_string, raw_data)

        # 4. Call LLM API (blocks until a rate limit token is available)
        raw_json_str = llm_client.generate_json(SYSTEM_PROMPT, user_prompt)
        cleaned_json_str = _extract_json_payload(raw_json_str)

        # 5. Parse + validate with Pydantic v2
        try:
            parsed = LlmOutput.model_validate_json(cleaned_json_str)
        except Exception as e:
            raise ValueError(
                f"LLM output failed Pydantic validation: {e}\n"
                f"Raw: {raw_json_str[:500]}"
            ) from e

        # 6. Compute confidence scores
        confidence = compute_confidence(parsed)

        # 7. Determine final status
        new_status = "READY"
        active_model = _active_model_name()

        # 8. Upsert results into property_reports
        with db.cursor() as cur:
            cur.execute(
                """UPDATE property_reports SET
                    llm_parsed_insights = %s,
                    confidence_scores   = %s,
                    overall_confidence  = %s,
                    status              = %s,
                    llm_model_version   = %s,
                    updated_at          = NOW()
                WHERE id = %s""",
                (
                    json.dumps(parsed.model_dump()),
                    json.dumps(confidence.scores),
                    confidence.overall,
                    new_status,
                    active_model,
                    property_report_id,
                ),
            )
            db.commit()

        logger.info(
            "[LLM] %s → %s (confidence=%s)", address_string, new_status, confidence.overall
        )

        # 9. Dispatch email notification if requested by a user
        try:
            with db.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.email, p.slug FROM users u
                    JOIN property_reports pr ON pr.requested_by_user_id = u.id
                    JOIN properties p ON p.id = pr.property_id
                    WHERE pr.id = %s
                    """,
                    (property_report_id,)
                )
                user_row = cur.fetchone()
            
            if user_row and user_row.get("email"):
                from app.services.email import send_report_ready_email
                send_report_ready_email(
                    to_email=user_row["email"],
                    address=address_string,
                    slug=user_row["slug"],
                )
                logger.info("[LLM] Sent report ready email to %s", user_row["email"])
        except Exception as email_exc:
            logger.error("[LLM] Failed to send email for %s: %s", property_report_id, email_exc)

    except Exception as exc:
        db.rollback()
        err_msg = str(exc)

        if "RATE_LIMIT" in err_msg or "429" in err_msg:
            logger.warning("[LLM] Rate limited on %s. Retrying in 65s.", address_string)
            raise self.retry(exc=exc)

        if "DAILY_QUOTA_EXCEEDED" in err_msg:
            logger.warning("[LLM] Daily quota reached. Retrying %s later.", address_string)
            # Retry with longer delay — next day
            raise self.retry(exc=exc, countdown=3600)

        if self.request.retries >= self.max_retries:
            # Exhausted retries — mark as FAILED
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE property_reports
                       SET status='FAILED', error_message=%s, updated_at=NOW()
                       WHERE id=%s""",
                    (err_msg[:1000], property_report_id),
                )
                db.commit()
            logger.error("[LLM] FAILED after max retries: %s — %s", address_string, err_msg)
        else:
            raise self.retry(exc=exc)
    finally:
        db.close()


# ── Scheduled: monthly state refresh ───────────────────────────────────────


@celery_app.task(
    bind=True,
    name="app.tasks.trigger_state_refresh",
    queue="llm_processing_queue",
    acks_late=True,
)
def trigger_state_refresh(self, state: str) -> dict:
    """Re-scrape all properties for a given state.

    Called by Celery Beat on schedule (e.g. VIC on 1st, NSW on 8th).
    Queries all properties in the state and dispatches a
    ``scraper_worker.tasks.scrape_property`` task for each.
    """
    db = get_db_connection()
    try:
        with db.cursor(name="state_refresh_cursor") as cur:
            cur.itersize = STATE_REFRESH_BATCH_SIZE
            cur.execute(
                """SELECT
                    p.id::text          AS property_id,
                    p.gnaf_pid,
                    p.address_string,
                    ST_Y(p.geom)        AS latitude,
                    ST_X(p.geom)        AS longitude,
                    COALESCE(z.name, 'UNKNOWN') AS lga_name,
                    p.state
                FROM properties p
                LEFT JOIN spatial_zones z
                    ON p.lga_id = z.id AND z.zone_type = 'LGA'
                WHERE p.state = %s
                ORDER BY p.last_scraped_at ASC NULLS FIRST""",
                (state,),
            )
            dispatched = 0
            for row in cur:
                celery_app.send_task(
                    "scraper_worker.tasks.scrape_property",
                    kwargs={
                        "property_id": row["property_id"],
                        "gnaf_pid": row["gnaf_pid"],
                        "address_string": row["address_string"],
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"]),
                        "lga_name": row["lga_name"],
                        "state": row["state"],
                    },
                    queue="data_acquisition_queue",
                )
                dispatched += 1
                if dispatched % STATE_REFRESH_BATCH_SIZE == 0:
                    time.sleep(0.1)
                    logger.info(
                        "[REFRESH] Dispatched %d scrape tasks for state=%s",
                        dispatched,
                        state,
                    )

        logger.info(
            "[REFRESH] Dispatched %d scrape tasks for state=%s", dispatched, state
        )
        return {"state": state, "dispatched": dispatched}

    except Exception as exc:
        logger.exception("[REFRESH] Failed to refresh state=%s: %s", state, exc)
        raise
    finally:
        db.close()


# ── Scheduled: dead-letter queue checker ───────────────────────────────────


@celery_app.task(
    bind=True,
    name="app.tasks.check_dlq",
    queue="llm_processing_queue",
    acks_late=True,
)
def check_dlq(self) -> dict:
    """Check for stuck reports and retry them.

    Finds property_reports that have been in PROCESSING with raw data for > 10 min
    (likely lost by a crashed worker) and re-dispatches the LLM parsing task.
    """
    db = get_db_connection()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT
                    pr.id::text             AS report_id,
                    pr.property_id::text    AS property_id,
                    p.address_string
                FROM property_reports pr
                JOIN properties p ON p.id = pr.property_id
                WHERE pr.status = 'PROCESSING'
                  AND pr.raw_scraped_data IS NOT NULL
                  AND pr.updated_at < NOW() - INTERVAL '10 minutes'
                  AND pr.retry_count < %s""",
                (MAX_DLQ_RETRIES,),
            )
            stuck_rows = cur.fetchall()

        retried = 0
        for row in stuck_rows:
            # Update retry count
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE property_reports
                       SET retry_count = retry_count + 1,
                           updated_at = NOW()
                       WHERE id=%s AND status='PROCESSING'""",
                    (row["report_id"],),
                )
                db.commit()

            # Re-dispatch LLM task
            parse_with_llm.apply_async(
                kwargs={
                    "property_id": row["property_id"],
                    "property_report_id": row["report_id"],
                    "address_string": row["address_string"],
                },
            )
            retried += 1

        if retried > 0:
            logger.warning("[DLQ] Retried %d stuck PROCESSING reports.", retried)

        with db.cursor() as cur:
            cur.execute(
                """UPDATE property_reports
                   SET status = 'FAILED',
                       error_message = 'Exhausted DLQ retries without completing LLM parse.',
                       updated_at = NOW()
                   WHERE status = 'PROCESSING'
                     AND raw_scraped_data IS NOT NULL
                     AND updated_at < NOW() - INTERVAL '10 minutes'
                     AND retry_count >= %s""",
                (MAX_DLQ_RETRIES,),
            )
            failed = cur.rowcount
            db.commit()

        if failed > 0:
            logger.error(
                "[DLQ] Marked %d exhausted PROCESSING reports as FAILED.",
                failed,
            )

        return {"retried": retried, "failed": failed}

    except Exception as exc:
        logger.exception("[DLQ] Check failed: %s", exc)
        raise
    finally:
        db.close()
