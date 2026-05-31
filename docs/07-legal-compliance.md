# OZ Property Report – Legal, Compliance & Data Quality Specification

## 1. Overview

This document defines the mandatory compliance requirements, legal guardrails, and data quality controls that should be considered when hosting your own instance of ParcelIQ. Failure to implement these correctly may expose the host to negligence claims, Privacy Act penalties, or AFSL enforcement depending on your jurisdiction.

---

## 2. Financial Advice Regulation (AFSL)

### 2.1 The Risk

Under the *Corporations Act 2001 (Cth)*, providing **personal financial product advice** without an Australian Financial Services Licence (AFSL) is a criminal offence. Section 766B defines "financial advice" broadly — it can include recommending investment in real property if the recommendation relates to a "financial product" (e.g. through a managed investment scheme).

Even for direct real estate (not a managed scheme), providing **general advice** that a reasonable person could interpret as a recommendation requires care.

### 2.2 What ParcelIQ Must NOT Do

The platform must never:
- State or imply a property is a "good" or "bad" investment
- Say "you should buy this property"
- Guarantee or strongly imply a specific ROI
- Rank properties by investment quality using a single "score"
- Provide advice tailored to an individual user's financial situation

### 2.3 What ParcelIQ CAN Do (General Information Only)

The platform can:
- Present factual, verifiable data (zoning codes, council decisions, flood maps)
- Present **scenario calculators** with clearly labelled assumptions
- Present historical price data and suburb median trends
- Describe risks (flooding, overlays) without characterising them as "deal-breakers"
- Provide information that a reasonable investor would use as one input among many

### 2.4 Mandatory Legal Language

The following disclaimer text is **required in the codebase** and must be rendered in the UI exactly as specified.

#### Short Disclaimer (appears on every page in the footer and in the Lite panel):
```
GENERAL INFORMATION ONLY. Data provided is aggregated from third-party 
public sources and is for general informational purposes only. It does not constitute 
financial, legal, property, or investment advice. The operator of this instance is not a licensed 
financial adviser. Always seek independent professional advice before making investment 
decisions. Data may not be current, complete, or accurate.
```

#### Full Disclaimer (appears at the top of every Full Report — user must scroll past it):
```
IMPORTANT — PLEASE READ BEFORE PROCEEDING

This report is provided for general informational purposes only. It is not personalised 
financial advice and does not take into account your individual financial objectives, 
situation, or needs.

The host of this service is not a licensed financial adviser, real 
estate agent, valuator, or conveyancer. The data in this report has been automatically 
aggregated from publicly available government sources and processed using artificial 
intelligence. It may contain errors, omissions, or outdated information.

ROI scenarios presented in this report are illustrative only, based on generalised 
assumptions, and are NOT predictions of future returns. Past performance does not 
guarantee future results. Property values can go up or down.

Before making any property investment decision, you must:
1. Conduct your own independent due diligence
2. Engage a licensed conveyancer or solicitor for legal advice
3. Engage a licensed financial adviser for personalised financial advice
4. Engage a licensed building inspector for structural assessment
5. Verify all zoning and planning information with the relevant local council

By downloading or viewing this report, you acknowledge and agree that the authors and operators 
shall not be liable for any loss or damage arising from your reliance on this report.
```

#### Mandatory Acknowledgement Checkbox (user must tick before viewing Full Report):
```
☐ I confirm I have read and understood the disclaimer above. I acknowledge this report 
is general information only and does not constitute financial advice. I will not make 
investment decisions based solely on this report.
```

**Implementation requirement:** The "Download Report" button must be disabled until this checkbox is ticked. Store acknowledgement per user per property in `localStorage` so user doesn't see it on every revisit.

---

## 3. ROI Scenarios — Safe Framing

Every ROI scenario must follow these rules:

1. **Always 3 scenarios** — Conservative, Base, Optimistic — never a single figure
2. **Always show assumptions** — every number must have its assumptions visible
3. **Never call it a "prediction"** — use "illustrative scenario" or "hypothetical scenario"
4. **Always show pre-tax figures** — explicitly note "Pre-tax. Consult a tax adviser for after-tax analysis."
5. **Interest rate assumptions must include a note** — e.g. "Assumes fixed rate of 6.0% p.a. Rates may change."

### Frontend Display Requirement
ROI scenarios must be rendered as a **scenario calculator** where the user can adjust inputs (interest rate, rent, vacancy), not as a fixed table that looks like a prediction.

---

## 4. Liability Limitation — Data Accuracy

### 4.1 The Risk

If ParcelIQ states a property is outside a flood zone and the property subsequently floods, the investor may have a negligence claim if they can demonstrate they relied on the report.

### 4.2 Mitigation Controls

**In the data layer:**
- Every data point in `llm_parsed_insights` must have a `confidenceScore`
- Every data point must have a `source` field referencing the original data provider
- Reports with `overall_confidence = 'LOW'` are served to users with a visible low-confidence warning indicator

**In the UI:**
- Low-confidence fields (< 0.7) must display a warning indicator: `⚠️ Lower confidence data — verify independently`
- Every data point must display its source (e.g. "Source: DELWP VicPlan API, February 2026")
- Zoning and flood data must always include: "Verify with [Council Name] and DELWP before relying on this data."

**In the Terms of Service:**
```
DATA ACCURACY DISCLAIMER: The operator does not warrant the accuracy, completeness, 
or timeliness of any data in its reports. Data is sourced from third-party 
government databases that may contain errors. In particular:

- Flood and bushfire risk data is sourced from state government mapping services 
  and may not reflect actual flood or fire risk.
- Zoning information reflects data at the time of scraping and may have changed.
- Estimated property values are algorithmic estimates, not formal valuations.

Users must verify all data independently before relying on it for any purpose.
```

---

## 5. Privacy Act 1988 (Cth) Compliance

### 5.1 Personal Information in Property Data

Some government data sources may incidentally include names of property owners (from title records or council correspondence). ParcelIQ must NOT:
- Store or display names of private individuals linked to specific properties
- Store or display contact details of current owners or tenants
- Publish scraped data that identifies individuals without their consent

**Implementation:** The scraper worker must strip any PII from `raw_scraped_data` before storing. Specifically:
```python
# In scraper worker, before DB insert (services/scraper-worker/app/utils/pii.py):
import re

# Australian phone formats: 04xx xxx xxx, (0x) xxxx xxxx, +61 x xxxx xxxx
PHONE_PATTERN = re.compile(
    r'(\+61|0)\s*[2-578]\s*\d{4}\s*\d{4}|04\d{2}\s*\d{3}\s*\d{3}'
)
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
# Common name-before-address patterns in council text
NAME_PATTERN = re.compile(r'(?:Owner|Applicant|Tenant|Occupier):\s*[A-Z][a-z]+ [A-Z][a-z]+')


def strip_pii(raw_data: dict) -> dict:
    """Redact PII from scraped text fields before storing in the database."""
    text_fields = [
        'council_planning_applications_text',
        'council_meeting_minutes_text',
    ]
    sanitised = {**raw_data}
    for field in text_fields:
        if sanitised.get(field):
            text = sanitised[field]
            text = PHONE_PATTERN.sub('[PHONE REDACTED]', text)
            text = EMAIL_PATTERN.sub('[EMAIL REDACTED]', text)
            text = NAME_PATTERN.sub('[NAME REDACTED]', text)
            sanitised[field] = text
    return sanitised
```

### 5.2 User Data

- Users must be provided with a **Privacy Policy** at signup (link in footer + signup flow)
- Users have the right to request deletion of their account and all associated data
- Implement `DELETE /api/users/me` endpoint that deletes all user data.
- Do NOT sell or share user data with third parties without explicit opt-in consent

### 5.3 Cookies and Tracking

MVP must display a cookie consent banner (Australian Privacy Principles apply to tracking). Only essential cookies (session auth) are set without consent. Analytics (if added later) require opt-in.

---

## 6. Scraping: Terms of Service Compliance

### 6.1 Government Open Data

All state government APIs (VicPlan, ABS, NBN Co) provide data under the **Creative Commons Attribution 4.0 (CC BY 4.0)** licence. ParcelIQ must:
- Attribute the source in all reports (e.g. "© State of Victoria (Department of Transport and Planning) 2026")
- Comply with any rate limits specified in the API terms

### 6.2 Council Planning Portals

Many council portals do not explicitly prohibit scraping but do not explicitly permit it either. For the MVP:
- Only scrape publicly accessible (no login required) pages
- Respect `robots.txt` — if a council's `robots.txt` disallows scraping their planning register, do not scrape it
- Do not circumvent any access controls (CAPTCHA, login walls, IP blocks)
- Implement request throttling: no more than 1 request per 3 seconds to any single council domain
- Cache scraped data — do not re-scrape more frequently than once per 30 days per property

### 6.3 `robots.txt` Checker

The scraper worker must check `robots.txt` before scraping any council domain:
```typescript
async function isScrapingAllowed(domain: string, path: string): Promise<boolean> {
  const robotsUrl = `https://${domain}/robots.txt`;
  try {
    const res = await fetch(robotsUrl, { signal: AbortSignal.timeout(5000) });
    const text = await res.text();
    // Parse with 'robots-txt-guard' npm package
    const guard = new RobotsTxtGuard(text, 'ParcelIQBot/1.0');
    return guard.isAllowed(path);
  } catch {
    return true;  // If robots.txt is not accessible, assume allowed
  }
}
```

---

## 7. Data Quality Controls — Hallucination Prevention

### 7.1 The Problem

LLMs hallucinate. For a property intelligence platform, a hallucinated "no flood risk" assessment or a fabricated infrastructure project could cause real financial harm to an investor.

### 7.2 Two-Layer Defence

**Layer 1 — Source Grounding in the Prompt:**
The LLM is explicitly instructed to base every answer on the provided source text only, set confidence < 0.6 for anything not explicitly in the source, and set any unknown field to `null`. This is enforced via the system prompt (see LLM Parser Worker spec).

**Layer 2 — Confidence Display:**
Reports are published to users immediately when parsing is complete. Confidence is displayed as an informational indicator only — users are not blocked from viewing low-confidence reports, but are shown a clear warning:
```typescript
// In public UI:
if (report.overall_confidence === 'LOW') {
  // Show warning: "Some fields in this report have lower confidence. Verify independently."
}
```

### 7.3 Admin Monitoring

Admins can monitor report confidence via the Admin Console:
1. The **Properties** page shows `overall_confidence` per property
2. Reports with `FAILED` status can be re-processed via the Re-scrape or Re-AI-Validate actions
3. Admins can force a re-scrape at any time to get fresher data

### 7.4 Key Fields That Must Always Have Source Attribution

The following fields must NEVER be served to users without an explicit source URL or reference:

| Field | Required Source |
|---|---|
| Flood risk | DELWP VicPlan API (must be stated) |
| Bushfire risk | DELWP VicPlan API (must be stated) |
| Zoning code | VicPlan API (must be stated) |
| Demographics | ABS Census (year must be stated) |
| Infrastructure projects | Council minutes URL or state government announcement URL |
| Crime density | Source and year must be stated |

---

## 8. Terms of Service & Privacy Policy

Before deploying publicly, ensure you have appropriate Terms of Service and Privacy Policies that comply with local regulations (such as the Australian Privacy Principles). This is critical if your deployment of the open-source software provides data that could influence users' financial decisions.
