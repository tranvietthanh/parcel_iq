# OZ Property Report – LLM Parser Worker Specification

## 1. Overview

**Technology:** Python 3.12, Celery, httpx (OpenAI), Pydantic v2, psycopg2  
**Purpose:** Takes raw scraped data from the `llm_processing_queue`, sends it to OpenAI via the Chat Completions API for structured extraction, validates the output with Pydantic v2, computes confidence scores, upserts results to `property_reports`, and sends a report-ready email to the requesting user.

**Rate limiting:** Configure `OPENAI_MAX_RPM` and `OPENAI_DAILY_QUOTA` in `services/llm-parser-worker/.env` (defaults: `OPENAI_MAX_RPM=60`, `OPENAI_DAILY_QUOTA=100000`).

The worker uses a Redis-backed token bucket to enforce limits strictly across all worker processes. Also configure `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-3.5-turbo`), `RESEND_API_KEY`, and `PUBLIC_WEB_URL` in `services/llm-parser-worker/.env`.

**Celery Beat:** The Celery Beat schedule (monthly state refreshes and DLQ monitoring) is embedded in this worker's `celery_app.py`. One pod is started with `--beat` in production.

---

## 2. Project Structure

```
/llm-parser-worker
├── app/
│   ├── celery_app.py              # Celery app factory (shares config with scraper)
│   ├── config.py                  # pydantic-settings (OPENAI_*, RESEND_API_KEY, PUBLIC_WEB_URL)
│   ├── tasks.py                   # Celery task: parse_with_llm
│   ├── services/
│   │   ├── llm_client.py          # OpenAI client (Chat Completions)
│   │   ├── email.py               # Resend email — sends report-ready notification
│   │   ├── db.py                  # psycopg2 (sync)
│   │   └── rate_limiter.py        # Redis token bucket (cross-process safe)
│   ├── prompts/
│   │   ├── system_prompt.py       # System prompt constant
│   │   └── user_prompt.py         # User prompt builder function
│   └── schemas/
│       ├── llm_output.py          # Pydantic v2 model for LLM output
│       └── confidence.py          # Confidence scoring logic
├── Dockerfile
├── pyproject.toml
└── .env.example
```

---

## 3. Celery Task (`app/tasks.py`)

```python
from celery import shared_task
from app.celery_app import celery_app
from app.services.db import get_db_connection
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.user_prompt import build_user_prompt
from app.schemas.llm_output import LlmOutput
from app.schemas.confidence import compute_confidence
from app.services.llm_client import llm_client  # OpenAI client (Chat Completions)
from app.config import settings

import json
import logging

logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True,
    name="app.tasks.parse_with_llm",
    queue="llm_processing_queue",
    max_retries=3,
    # Fixed retry delay: 65s (respects the 1-min rate limit window + safety buffer)
    default_retry_delay=65,
    acks_late=True,
)
def parse_with_llm(
    self,
    property_id: str,
    property_report_id: str,
    address_string: str,
) -> None:
    db = get_db_connection()
    try:
        # 1. Mark as PROCESSING
        with db.cursor() as cur:
            cur.execute(
                "UPDATE property_reports SET status='PROCESSING', updated_at=NOW() WHERE id=%s",
                (property_report_id,)
            )
            db.commit()

        # 2. Fetch raw scraped data
        with db.cursor() as cur:
            cur.execute(
                "SELECT raw_scraped_data FROM property_reports WHERE id=%s",
                (property_report_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"No report found for id={property_report_id}")
            raw_data: dict = row[0]

        # 3. Build prompt
        user_prompt = build_user_prompt(address_string, raw_data)

        # 4. Call configured LLM API (blocks until a rate limit token is available)
        raw_json_str = llm_client.generate_json(SYSTEM_PROMPT, user_prompt)

        # 5. Parse + validate with Pydantic v2
        try:
            parsed = LlmOutput.model_validate_json(raw_json_str)
        except Exception as e:
            raise ValueError(f"LLM output failed Pydantic validation: {e}\nRaw: {raw_json_str[:500]}")

        # 6. Compute confidence scores
        confidence = compute_confidence(parsed)

        # 7. Determine final status
        new_status = "READY"

        # 8. Upsert results into property_reports
        # Use configured OpenAI model name as the model version
        model_version = settings.OPENAI_MODEL
        
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
                    model_version,
                    property_report_id,
                )
            )
            
            # 9. Fetch user email to send notification
            cur.execute(
                """SELECT u.email 
                   FROM property_reports r
                   JOIN users u ON u.id = r.requested_by_user_id
                   WHERE r.id = %s""",
                (property_report_id,)
            )
            user_row = cur.fetchone()
            
            db.commit()

        # Send email if user requested
        if user_row and user_row[0]:
            from app.services.email_service import send_report_ready_email
            try:
                send_report_ready_email(user_row[0], address_string, property_id)
            except Exception as e:
                logger.warning(f"Failed to send email to {user_row[0]}: {e}")

        logger.info(f"[LLM] {address_string} → {new_status} (confidence={confidence.overall}, model={model_version})")

    except Exception as exc:
        db.rollback()
        err_msg = str(exc)

        if "RATE_LIMIT" in err_msg or "DAILY_QUOTA" in err_msg:
            # Rate limit/quota hit — retry after 65s (Celery default_retry_delay)
            logger.warning(f"[LLM] Rate limited/quota on {address_string}. Retrying in 65s.")
            raise self.retry(exc=exc)

        if self.request.retries >= self.max_retries:
            # Exhausted retries — mark as FAILED
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE property_reports
                       SET status='FAILED', error_message=%s, updated_at=NOW()
                       WHERE id=%s""",
                    (err_msg[:1000], property_report_id)
                )
                db.commit()
            logger.error(f"[LLM] FAILED after max retries: {address_string} — {err_msg}")
        else:
            raise self.retry(exc=exc)
    finally:
        db.close()
```

---

## 4. Redis Token Bucket Rate Limiter (`services/rate_limiter.py`)

Using Redis for the token bucket makes it **cross-process safe** — multiple Celery worker processes on the same pod all share one rate limit counter.

```python
import time
import redis as redis_lib
from app.config import settings

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

MAX_RPM = settings.OPENAI_MAX_RPM
WINDOW_SECONDS = 60
TOKEN_KEY = "openai:rate_limit:tokens"
LAST_REFILL_KEY = "openai:rate_limit:last_refill"
DAILY_COUNT_KEY_PREFIX = "openai:daily_count:"


def wait_for_token() -> None:
    """
    Blocks the calling thread until a rate limit token is available.
    Safe to call from multiple Celery worker processes simultaneously.
    """
    while True:
        with redis_client.pipeline() as pipe:
            try:
                pipe.watch(TOKEN_KEY, LAST_REFILL_KEY)
                tokens = int(redis_client.get(TOKEN_KEY) or MAX_RPM)
                last_refill = float(redis_client.get(LAST_REFILL_KEY) or time.time())
                now = time.time()
                elapsed = now - last_refill
                tokens_to_add = int(elapsed / (WINDOW_SECONDS / MAX_RPM))

                if tokens_to_add > 0:
                    tokens = min(MAX_RPM, tokens + tokens_to_add)
                    last_refill = now

                if tokens > 0:
                    pipe.multi()
                    pipe.set(TOKEN_KEY, tokens - 1)
                    pipe.set(LAST_REFILL_KEY, last_refill)
                    pipe.execute()
                    return   # Token acquired — proceed with API call
                else:
                    # No tokens — wait one token interval before retrying
                    sleep_secs = (WINDOW_SECONDS / MAX_RPM) - elapsed % (WINDOW_SECONDS / MAX_RPM)
                    time.sleep(max(0.5, sleep_secs))
            except redis_lib.WatchError:
                continue   # Another worker modified the keys — retry


def check_daily_quota() -> None:
    """
    Raises an exception if the daily quota is exhausted.
    Job stays in queue and will retry the next day.
    """
    daily_limit = int(settings.OPENAI_DAILY_QUOTA)
    today = time.strftime("%Y-%m-%d")
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 86_400)   # Expire at end of day
    if count > daily_limit:
        raise RuntimeError(
            f"DAILY_QUOTA_EXCEEDED: {count}/{daily_limit} OpenAI requests used today. "
            "Task will retry tomorrow."
        )
```

---

## 5. OpenAI Client (`services/llm_client.py`)

```python
import json
import httpx
from app.config import settings
from app.services.rate_limiter import wait_for_token, check_daily_quota


class OpenAIClient:
    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """
        Blocks until a rate limit token is available, then calls the OpenAI Chat Completions API.
        Returns the raw JSON string from the model.
        """
        check_daily_quota()   # Raises if daily limit hit
        wait_for_token()      # Blocks until RPM token available

        try:
            response = httpx.post(
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.OPENAI_MODEL,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RuntimeError(f"RATE_LIMIT: {e}")
            raise


llm_client = OpenAIClient()
```

---

## 6. Prompts

### System Prompt (`prompts/system_prompt.py`)

```python
SYSTEM_PROMPT = """
You are a structured data extraction engine for an Australian property intelligence platform.

Your job is to read raw property data sourced from Australian government APIs and local council
planning portals, and extract structured investment-relevant information.

CRITICAL RULES:
1. Return ONLY valid JSON. No markdown, no preamble, no explanation outside the JSON.
2. If you cannot find a data point in the source text, set it to null. NEVER invent data.
3. Assign a confidence_score between 0.0 and 1.0 to every field:
   - 1.0 = explicitly stated in an authoritative source (government API response)
   - 0.7–0.9 = clearly stated in scraped council text
   - 0.5–0.69 = reasonably inferred from available context
   - < 0.5 = uncertain or ambiguous
4. ROI scenarios MUST include the disclaimer field. Never omit it.
5. Never state that a property "is a good investment" or use language implying a recommendation.
   Describe data and risks only.
6. The JSON must exactly match the provided schema. Do not add extra keys.
"""
```

### User Prompt Builder (`prompts/user_prompt.py`)

```python
import json

# The exact JSON schema pasted into the prompt so the model knows what to return
OUTPUT_SCHEMA = {
    "zoning_and_planning": {
        "zoning_code": "string | null",
        "zoning_label": "string | null",
        "lga_name": "string | null",
        "epi_name": "string | null",
        "epi_type": "string | null",
        "overlays": ["string"],
        "overlay_descriptions": ["string"],
        "heritage_area": "bool | null",
        "subdivision_potential": "string | null",
        "conflict_note": "string | null",
        "confidence_score": 0.0
    },
    "risk_factors": {
        "flood": {"risk": "NONE|LOW|MEDIUM|HIGH|null", "detail": "string|null", "confidence_score": 0.0},
        "bushfire": {"risk": "NONE|LOW|MEDIUM|HIGH|null", "detail": "string|null", "confidence_score": 0.0},
        "crime_density": {"rating": "BELOW_AVERAGE|AVERAGE|ABOVE_AVERAGE|null", "detail": "string|null", "confidence_score": 0.0}
    },
    "connectivity": {
        "nbn_tech_type": "FTTP|HFC|FTTN|FTTB|FTTC|WIRELESS|SATELLITE|null",
        "nbn_service_status": "string | null",
        "nbn_tech_change_status": "string | null",
        "nbn_target_eligibility_quarter": "string | null",
        "confidence_score": 0.0
    },
    "infrastructure": [
        {"type": "TRANSPORT|HEALTH|EDUCATION|COMMERCIAL|OTHER", "description": "string",
         "distance_km": 0.0, "expected_completion_year": 0, "source_url": "string|null",
         "confidence_score": 0.0}
    ],
    "roi_scenarios": {
        "disclaimer": "Illustrative scenarios only. Not financial advice.",
        "scenarios": [
            {"label": "Conservative|Base|Optimistic",
             "assumptions": {"interest_rate_percent": 0.0, "weekly_rent_aud": 0,
                             "vacancy_rate_percent": 0.0, "maintenance_percent": 0.0,
                             "council_rates_annual_aud": 0, "insurance_annual_aud": 0},
             "gross_yield_percent": 0.0, "net_yield_percent": 0.0, "annual_cash_flow_aud": 0}
        ]
    },
    "demographic_snapshot": {
        "suburb": "string|null", "median_household_weekly_income_aud": 0,
        "owner_occupier_percent": 0.0, "median_age": 0,
        "primary_household_type": "string|null", "source": "string|null",
        "confidence_score": 0.0
    }
}


def build_user_prompt(address: str, raw_data: dict) -> str:
    return f"""
Extract structured property intelligence for the following Australian property:
Address: {address}

## RAW DATA SOURCES

### State Planning API Response (Authoritative — weight: HIGH)
Zoning Code: {raw_data.get('zoning_code', 'NOT AVAILABLE')}
Zoning Label: {raw_data.get('zoning_label', 'NOT AVAILABLE')}
Overlays: {', '.join(raw_data.get('overlay_codes', [])) or 'NONE DETECTED'}
Flood Risk Classification: {raw_data.get('flood_risk', 'NOT AVAILABLE')}
Bushfire Risk Classification: {raw_data.get('bushfire_risk', 'NOT AVAILABLE')}

### NBN Co API Response (Authoritative — weight: HIGH)
NBN Details: {json.dumps(raw_data.get('nbn') or {}, indent=2)}

### ABS Census Data (Authoritative — weight: HIGH)
{json.dumps(raw_data.get('demographics') or {}, indent=2)}

### Council Planning Portal — Applications (Scraped HTML — weight: MEDIUM)
{raw_data.get('council_planning_applications_text') or 'NOT AVAILABLE'}

### Council Meeting Minutes (Extracted PDF Text — weight: MEDIUM)
{raw_data.get('council_meeting_minutes_text') or 'NOT AVAILABLE'}

---

Return a JSON object exactly matching this schema:
{json.dumps(OUTPUT_SCHEMA, indent=2)}
"""
```

---

## 7. Email Notification (`services/email.py`)

After a report status is set to `READY`, the worker looks up the requesting user's email from `property_reports.requested_by_user_id` and sends a report-ready notification via Resend.

```python
import html
import resend
from app.config import settings

resend.api_key = settings.RESEND_API_KEY


def send_report_ready_email(to_email: str, address: str, property_id: str) -> None:
    safe_address = html.escape(address)
    safe_id = html.escape(property_id)
    url = f"{settings.PUBLIC_WEB_URL}/property/{safe_id}"

    resend.Emails.send({
        "from": "OZ Property Report <reports@ozpropertyreport.com>",
        "to": to_email,
        "subject": f"Your report is ready — {safe_address}",
        "html": f"""
            <p>Hi,</p>
            <p>Your property report for <strong>{safe_address}</strong> is ready.</p>
            <p><a href="{url}">View your report</a></p>
        """,
    })
```

- `address` and `property_id` are HTML-escaped before interpolation
- `PUBLIC_WEB_URL` is configurable — set to `http://localhost:3000` in dev
- Email failures are non-fatal: logged as a warning, report status is still `READY`

---

## 8. Pydantic v2 Output Schema (`schemas/llm_output.py`)

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class RiskEntry(BaseModel):
    risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None
    detail: str | None
    confidence_score: float = Field(ge=0.0, le=1.0)


class CrimeDensityEntry(BaseModel):
    rating: Literal["BELOW_AVERAGE", "AVERAGE", "ABOVE_AVERAGE"] | None
    detail: str | None
    confidence_score: float = Field(ge=0.0, le=1.0)


class ZoningAndPlanning(BaseModel):
    zoning_code: str | None = None
    zoning_label: str | None = None
    lga_name: str | None = None
    epi_name: str | None = None
    epi_type: str | None = None
    overlays: list[str] = Field(default_factory=list)
    overlay_descriptions: list[str] = Field(default_factory=list)
    heritage_area: bool | None = None
    subdivision_potential: str | None = None
    conflict_note: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class RiskFactors(BaseModel):
    flood: RiskEntry
    bushfire: RiskEntry
    crime_density: CrimeDensityEntry


class Connectivity(BaseModel):
    nbn_tech_type: Literal["FTTP", "HFC", "FTTN", "FTTB", "FTTC", "WIRELESS", "SATELLITE"] | None = None
    nbn_service_status: str | None = None
    nbn_tech_change_status: str | None = None
    nbn_target_eligibility_quarter: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class InfrastructureItem(BaseModel):
    type: Literal["TRANSPORT", "HEALTH", "EDUCATION", "COMMERCIAL", "OTHER"]
    description: str
    distance_km: float | None = None
    expected_completion_year: int | None = None
    source_url: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class ScenarioAssumptions(BaseModel):
    interest_rate_percent: float
    weekly_rent_aud: int
    vacancy_rate_percent: float
    maintenance_percent: float
    council_rates_annual_aud: int
    insurance_annual_aud: int


class RoiScenario(BaseModel):
    label: Literal["Conservative", "Base", "Optimistic"]
    assumptions: ScenarioAssumptions
    gross_yield_percent: float
    net_yield_percent: float
    annual_cash_flow_aud: int


class RoiScenarios(BaseModel):
    disclaimer: str
    scenarios: list[RoiScenario]

    @model_validator(mode="after")
    def disclaimer_must_be_present(self):
        if not self.disclaimer or len(self.disclaimer) < 10:
            raise ValueError("ROI disclaimer is required and cannot be empty.")
        return self


class DemographicSnapshot(BaseModel):
    suburb: str | None = None
    median_household_weekly_income_aud: int | None = None
    owner_occupier_percent: float | None = None
    median_age: int | None = None
    primary_household_type: str | None = None
    source: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class LlmOutput(BaseModel):
    """
    Pydantic v2 model enforcing the exact structure expected from the OpenAI response.
    model_config strict=True rejects any extra keys the LLM might add.
    """
    model_config = {"strict": True, "extra": "forbid"}

    zoning_and_planning: ZoningAndPlanning
    risk_factors: RiskFactors
    connectivity: Connectivity
    infrastructure: list[InfrastructureItem]
    roi_scenarios: RoiScenarios
    demographic_snapshot: DemographicSnapshot
```

---

## 9. Confidence Scoring (`schemas/confidence.py`)

```python
from dataclasses import dataclass
from app.schemas.llm_output import LlmOutput


@dataclass
class ConfidenceResult:
    overall: str             # "HIGH", "MEDIUM", "LOW"
    scores: dict


def compute_confidence(output: LlmOutput) -> ConfidenceResult:
    scores = {
        "zoning_and_planning": output.zoning_and_planning.confidence_score,
        "flood": output.risk_factors.flood.confidence_score,
        "bushfire": output.risk_factors.bushfire.confidence_score,
        "crime_density": output.risk_factors.crime_density.confidence_score,
        "connectivity": output.connectivity.confidence_score,
        "demographics": output.demographic_snapshot.confidence_score,
        "infrastructure": (
            sum(i.confidence_score for i in output.infrastructure) / len(output.infrastructure)
            if output.infrastructure else 0.0
        ),
    }

    values = list(scores.values())
    avg = sum(values) / len(values) if values else 0.0
    has_low_field = any(v < 0.6 for v in values)

    overall = "HIGH" if avg >= 0.85 else "MEDIUM" if avg >= 0.65 else "LOW"

    return ConfidenceResult(
        overall=overall,
        scores={
            **scores,
            "overall_avg": round(avg, 3),
        },
    )
```

---



## 10. Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runner
COPY --from=builder /app/.venv ./.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
CMD ["celery", "-A", "app.celery_app", "worker",
     "--queues", "llm_processing_queue",
     "--concurrency", "2",
     "--loglevel", "info"]
```

> Worker concurrency is fixed at 2 for the LLM parser — the Redis token bucket controls actual OpenAI API throughput, so more workers just means more threads waiting on the rate limiter.

> In production, one pod is started with `--beat` appended to embed the Celery Beat scheduler:
> ```bash
> celery -A app.celery_app worker --queues llm_processing_queue --concurrency 2 --beat --loglevel info
> ```
> Only one instance should have `--beat` (singleton constraint). All other replicas omit this flag.
