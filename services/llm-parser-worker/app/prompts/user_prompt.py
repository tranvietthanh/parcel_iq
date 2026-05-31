"""User prompt builder for the Gemini extraction model.

Constructs a prompt from raw scraped data, including the expected JSON schema
so the model knows exactly what to return.

Source: docs/06-llm-parser-worker.md §6
"""

from __future__ import annotations

import json
import re

# Max characters of scraped free text to include — prevents context overflow
# and limits prompt injection surface area
_MAX_SCRAPED_TEXT_CHARS = 4_000
_MAX_COUNCIL_MINUTES_CHARS = 2_000

# The exact disclaimer string mandated by the system prompt
_ROI_DISCLAIMER = (
    "This output is factual data only and does not constitute financial advice. "
    "Past performance is not indicative of future results."
)

# JSON schema sent to the model. Uses string type annotations rather than
# literal values so the model understands these are targets, not defaults.
OUTPUT_SCHEMA = {
    "zoning_and_planning": {
        "zoning_code": "string | null",
        "zoning_label": "string | null",
        "lga_name": "string | null",
        "epi_name": "string | null",
        "epi_type": "string | null",
        "overlays": [
            {
                "code": "string",
                "severity": "integer 1-10 | null",
                "family": "string | null",
                "summary": "string | null",
            }
        ],
        "heritage_area": "boolean | null",
        "subdivision_potential": "string | null",
        "conflict_note": "string | null",
        "confidence_score": "float 0.0–1.0",
    },
    "risk_factors": {
        "flood": {
            "risk": "NONE | LOW | MEDIUM | HIGH | null",
            "detail": "string | null",
            "confidence_score": "float 0.0–1.0",
        },
        "bushfire": {
            "risk": "NONE | LOW | MEDIUM | HIGH | null",
            "detail": "string | null",
            "confidence_score": "float 0.0–1.0",
        },
        "crime_density": {
            "rating": "BELOW_AVERAGE | AVERAGE | ABOVE_AVERAGE | null",
            "detail": "string | null",
            "confidence_score": "float 0.0–1.0",
        },
    },
    "connectivity": {
        "nbn_tech_type": "FTTP | HFC | FTTN | FTTB | FTTC | WIRELESS | SATELLITE | null",
        "nbn_service_status": "string | null",
        "nbn_tech_change_status": "string | null",
        "nbn_target_eligibility_quarter": "string | null",
        "confidence_score": "float 0.0–1.0",
    },
    "infrastructure": [
        {
            "type": "TRANSPORT | HEALTH | EDUCATION | COMMERCIAL | OTHER",
            "description": "string",
            "distance_km": "float | null",
            "expected_completion_year": "integer | null",
            "source_url": "string | null",
            "confidence_score": "float 0.0–1.0",
        }
    ],
    "roi_scenarios": {
        "disclaimer": _ROI_DISCLAIMER,
        "scenarios": [
            {
                "label": "Conservative | Base | Optimistic",
                "assumptions": {
                    "interest_rate_percent": "float",
                    "weekly_rent_aud": "integer",
                    "vacancy_rate_percent": "float",
                    "maintenance_percent": "float",
                    "council_rates_annual_aud": "integer",
                    "insurance_annual_aud": "integer",
                },
                "gross_yield_percent": "float",
                "net_yield_percent": "float",
                "annual_cash_flow_aud": "integer",
            }
        ],
    },
    "demographic_snapshot": {
        "suburb": "string | null",
        "lga_name": "string | null",
        "reference_year": "integer | null",
        "total_population": "integer | null",
        "population_density_per_sqkm": "float | null",
        "population_growth_pct_yoy": "float | null",
        "population_cagr_5yr_pct": "float | null",
        "median_age": "float | null",
        "primary_household_type": "string | null",
        "total_fertility_rate": "float | null",
        "children_enrolled_preschool": "integer | null",
        "net_internal_migration": "integer | null",
        "net_overseas_migration": "integer | null",
        "overseas_migration_arrivals": "integer | null",
        "dominant_migration_driver": "OVERSEAS | INTERNAL | BALANCED | null",
        "total_businesses": "integer | null",
        "business_count_growth_pct_yoy": "float | null",
        "net_business_entries": "integer | null",
        "established_house_median_price_aud": "integer | null",
        "house_price_growth_pct_yoy": "float | null",
        "house_price_cagr_5yr_pct": "float | null",
        "attached_dwelling_median_price_aud": "integer | null",
        "established_house_transfers_count": "integer | null",
        "attached_dwelling_transfers_count": "integer | null",
        "total_dwelling_approvals": "integer | null",
        "dwelling_approvals_growth_pct_yoy": "float | null",
        "private_house_approvals": "integer | null",
        "total_building_approvals_value_aud_millions": "float | null",
        "solar_panel_installations": "integer | null",
        "owner_occupier_percent": "float | null",
        "median_household_weekly_income_aud": "integer | null",
        "dva_age_pension_recipients": "integer | null",
        "dva_service_pension_recipients": "integer | null",
        "source": "string | null",
        "confidence_score": "float 0.0–1.0",
    },
    "demographic_trend_analysis": {
        "population_momentum": "ACCELERATING | STABLE | DECELERATING | null",
        "population_momentum_note": "string | null",
        "migration_trend": "STRENGTHENING | STABLE | WEAKENING | null",
        "migration_trend_note": "string | null",
        "housing_supply_pressure": "UNDERSUPPLY | BALANCED | OVERSUPPLY | null",
        "housing_supply_pressure_note": "string | null",
        "price_growth_trend": "ACCELERATING | STABLE | DECELERATING | NEGATIVE | null",
        "price_growth_trend_note": "string | null",
        "business_health_trend": "IMPROVING | STABLE | DETERIORATING | null",
        "business_health_trend_note": "string | null",
        "rental_demand_outlook": "STRONG | MODERATE | WEAK | null",
        "rental_demand_outlook_note": "string | null",
        "overall_investment_signal": "POSITIVE | NEUTRAL | CAUTIONARY | null",
        "overall_investment_signal_note": "string | null",
        "confidence_score": "float 0.0–1.0",
    },
    "education": {
        "nearby_schools_summary": "string | null",
        "primary_schools": [
            {
                "name": "string",
                "distance_km": "float",
                "in_catchment": "boolean",
                "enrolments": "integer | null",
                "sector": "string | null",
            }
        ],
        "secondary_schools": [
            {
                "name": "string",
                "distance_km": "float",
                "in_catchment": "boolean",
                "enrolments": "integer | null",
                "sector": "string | null",
            }
        ],
        "confidence_score": "float 0.0–1.0",
    },
    "narrative": {
        "executive_summary": "string",
        "zoning_summary": "string",
        "demographic_story": "string",
        "market_momentum": "string",
        "rental_case": "string",
        "risk_summary": "string",
        "investor_context": "string",
    },
}


def _sanitise(text: str, max_chars: int) -> str:
    """Truncate and strip prompt-injection attempts from scraped free text.

    Removes patterns commonly used to hijack LLM instructions, then caps
    length to avoid context overflow.
    """
    # Strip null bytes and non-printable control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Neutralise common injection openers (case-insensitive)
    injection_patterns = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions?",
        r"disregard\s+(all\s+)?previous",
        r"you\s+are\s+now\s+",
        r"new\s+instructions?:",
        r"system\s*prompt\s*:",
        r"<\s*/?system\s*>",
        r"\[INST\]",
        r"\[\[SYSTEM\]\]",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text[:max_chars]


def _format_demographics(demographics: dict) -> str:
    """Render the demographics dict into a structured, LLM-readable block.

    Separates the latest snapshot from the time series so the model can
    reason about both point-in-time values and multi-year trends without
    needing to parse raw JSON itself.
    """
    if not demographics:
        return "NOT AVAILABLE"

    lines: list[str] = []

    lga = demographics.get("lga_name") or demographics.get("lga_code") or "Unknown LGA"
    year = demographics.get("latest_year") or "Unknown"
    source = demographics.get("source") or "ABS Data by Region"
    lines.append(f"Source: {source}")
    lines.append(f"LGA: {lga}  |  Latest year: {year}")

    # ── Latest snapshot ───────────────────────────────────────────────────
    latest = demographics.get("latest") or {}
    if latest:
        lines.append("")
        lines.append("### Latest Snapshot")

        def _row(label: str, key: str, fmt: str = "{}") -> None:
            val = latest.get(key)
            if val is not None:
                lines.append(f"  {label}: {fmt.format(val)}")

        _row("Total population", "total_population", "{:,}")
        _row("Population density (per km²)", "population_density_per_sqkm")
        _row("Population growth YoY (%)", "population_growth_pct_yoy")
        _row("Median age (years)", "median_age_persons_years")
        _row("Total fertility rate", "total_fertility_rate")
        _row("Children enrolled preschool", "children_enrolled_preschool", "{:,}")
        lines.append("")
        _row("Net internal migration", "net_internal_migration", "{:+,}")
        _row("Net overseas migration", "net_overseas_migration", "{:+,}")
        _row("Internal migration arrivals", "internal_migration_arrivals", "{:,}")
        _row("Internal migration departures", "internal_migration_departures", "{:,}")
        _row("Overseas migration arrivals", "overseas_migration_arrivals", "{:,}")
        _row("Registered births", "registered_births", "{:,}")
        _row("Standardised death rate (per 1,000)", "standardised_death_rate_per_1000")
        lines.append("")
        _row("Total businesses", "total_businesses", "{:,}")
        _row("Business entries", "total_business_entries", "{:,}")
        _row("Business exits", "total_business_exits", "{:,}")
        _row("Business count growth YoY (%)", "business_count_growth_pct_yoy")
        lines.append("")
        _row("Established house median price (AUD)", "established_house_median_price_aud", "${:,}")
        _row("House price growth YoY (%)", "house_price_growth_pct_yoy")
        _row("Attached dwelling median price (AUD)", "attached_dwelling_median_price_aud", "${:,}")
        _row("Established house transfers", "established_house_transfers_count", "{:,}")
        _row("Attached dwelling transfers", "attached_dwelling_transfers_count", "{:,}")
        lines.append("")
        _row("Total dwelling approvals", "total_dwelling_approvals", "{:,}")
        _row("Private house approvals", "private_house_approvals", "{:,}")
        _row("Dwelling approvals growth YoY (%)", "dwelling_approvals_growth_pct_yoy")
        _row("Total building approvals value (AUD millions)", "total_building_approvals_value_aud_millions", "${:,.0f}M")
        lines.append("")
        _row("Solar panel installations", "solar_panel_installations", "{:,}")
        _row("DVA age pension recipients", "dva_age_pension_recipients", "{:,}")
        _row("DVA service pension recipients", "dva_service_pension_recipients", "{:,}")

    # ── Legacy lightweight demographic payload fallback ──────────────────
    # Some tests and older adapter outputs provide a compact structure with
    # top-level demographic fields (without `latest`/`time_series`).
    if not latest and not demographics.get("time_series"):
        legacy_suburb = demographics.get("suburb")
        legacy_income = demographics.get("median_household_weekly_income")
        legacy_income_aud = demographics.get("median_household_weekly_income_aud")
        legacy_owner_occ = demographics.get("owner_occupier_percent")
        legacy_median_age = demographics.get("median_age")

        if any(
            val is not None
            for val in [legacy_suburb, legacy_income, legacy_income_aud, legacy_owner_occ, legacy_median_age]
        ):
            lines.append("")
            lines.append("### Snapshot (legacy fields)")
            if legacy_suburb is not None:
                lines.append(f"  Suburb: {legacy_suburb}")
            income_val = legacy_income_aud if legacy_income_aud is not None else legacy_income
            if income_val is not None:
                lines.append(f"  Median household weekly income (AUD): ${income_val:,}")
            if legacy_owner_occ is not None:
                lines.append(f"  Owner occupier (%): {legacy_owner_occ}")
            if legacy_median_age is not None:
                lines.append(f"  Median age: {legacy_median_age}")

    # ── Time series ───────────────────────────────────────────────────────
    time_series: dict = demographics.get("time_series") or {}
    if time_series:
        lines.append("")
        lines.append("### Time Series (key metrics by year)")
        headers = [
            ("Year", 6),
            ("Population", 12),
            ("Pop growth %", 13),
            ("House median $", 16),
            ("House price %", 14),
            ("Dwelling approv.", 17),
            ("Net overseas mig.", 18),
            ("Net internal mig.", 18),
        ]
        header_row = "  " + "  ".join(h.ljust(w) for h, w in headers)
        lines.append(header_row)
        lines.append("  " + "-" * (sum(w + 2 for _, w in headers)))

        for yr in sorted(time_series.keys()):
            d = time_series[yr]
            row_vals = [
                str(yr).ljust(6),
                f"{d.get('total_population', ''):>10,}".ljust(12) if d.get("total_population") else "N/A".ljust(12),
                f"{d.get('population_growth_pct_yoy', 'N/A')}".ljust(13),
                f"${d.get('established_house_median_price_aud', 0):,}".ljust(16) if d.get("established_house_median_price_aud") else "N/A".ljust(16),
                f"{d.get('house_price_growth_pct_yoy', 'N/A')}".ljust(14),
                f"{d.get('total_dwelling_approvals', 'N/A')}".ljust(17),
                f"{d.get('net_overseas_migration', 'N/A'):+}".ljust(18) if isinstance(d.get("net_overseas_migration"), (int, float)) else "N/A".ljust(18),
                f"{d.get('net_internal_migration', 'N/A'):+}".ljust(18) if isinstance(d.get("net_internal_migration"), (int, float)) else "N/A".ljust(18),
            ]
            lines.append("  " + "  ".join(row_vals))

    # ── Pre-computed trend signals ────────────────────────────────────────
    trend_hints = _compute_trend_hints(time_series)
    if trend_hints:
        lines.append(trend_hints)

    return "\n".join(lines)


def _compute_trend_hints(time_series: dict) -> str:
    """Pre-derive trend signals from the time series to guide the model.

    Rather than asking the model to compute trends from scratch, we hand it
    explicit calculated signals — reducing hallucination risk and improving
    consistency. The model should still use these as a starting point and
    apply judgement, not override them blindly.
    """
    if not time_series:
        return ""

    years = sorted(time_series.keys())
    if len(years) < 2:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("### Pre-Computed Trend Signals (use as analytical inputs)")

    def _series(key: str) -> list[tuple[str, float]]:
        """Return [(year, value), ...] for a given metric, filtering nulls."""
        return [
            (yr, time_series[yr][key])
            for yr in years
            if isinstance(time_series[yr].get(key), (int, float))
        ]

    # ── Population growth trajectory ──────────────────────────────────────
    pop_growth = _series("population_growth_pct_yoy")
    if len(pop_growth) >= 2:
        recent = [v for _, v in pop_growth[-2:]]
        earlier = [v for _, v in pop_growth[:-2]] if len(pop_growth) > 2 else None
        avg_recent = sum(recent) / len(recent)
        trend_str = (
            f"avg last 2yrs={avg_recent:.2f}%"
            + (f", avg prior={sum(earlier)/len(earlier):.2f}%" if earlier else "")
        )
        detail = ", ".join(f"{yr}={v}%" for yr, v in pop_growth)
        lines.append(f"  Population growth YoY series:  {detail}")
        lines.append(f"    → Trend calc: {trend_str}")

    # ── Migration composition ─────────────────────────────────────────────
    overseas_mig = _series("net_overseas_migration")
    internal_mig = _series("net_internal_migration")
    if overseas_mig:
        detail = ", ".join(f"{yr}={v:+,}" for yr, v in overseas_mig)
        lines.append(f"  Net overseas migration series: {detail}")
    if internal_mig:
        detail = ", ".join(f"{yr}={v:+,}" for yr, v in internal_mig)
        lines.append(f"  Net internal migration series: {detail}")

    # ── Dwelling approvals vs population pressure ──────────────────────────
    approvals = _series("total_dwelling_approvals")
    approv_growth = _series("dwelling_approvals_growth_pct_yoy")
    if approvals:
        detail = ", ".join(f"{yr}={v:,}" for yr, v in approvals)
        lines.append(f"  Dwelling approvals series:     {detail}")
    if approv_growth:
        detail = ", ".join(f"{yr}={v}%" for yr, v in approv_growth)
        lines.append(f"  Dwelling approvals growth %:   {detail}")

    # ── House price growth trajectory ─────────────────────────────────────
    price_growth = _series("house_price_growth_pct_yoy")
    if len(price_growth) >= 2:
        detail = ", ".join(f"{yr}={v}%" for yr, v in price_growth)
        peak_yr, peak_val = max(price_growth, key=lambda x: x[1])
        latest_yr, latest_val = price_growth[-1]
        lines.append(f"  House price growth % series:   {detail}")
        lines.append(f"    → Peak: {peak_val}% ({peak_yr}), Latest: {latest_val}% ({latest_yr})")

    # ── House price CAGR ──────────────────────────────────────────────────
    house_prices = _series("established_house_median_price_aud")
    if len(house_prices) >= 2:
        start_yr, start_price = house_prices[0]
        end_yr, end_price = house_prices[-1]
        n_years = int(end_yr) - int(start_yr)
        if n_years > 0 and start_price > 0:
            cagr = ((end_price / start_price) ** (1 / n_years) - 1) * 100
            lines.append(
                f"  House price CAGR ({start_yr}–{end_yr}): {cagr:.2f}%"
                f"  (${start_price:,} → ${end_price:,})"
            )

    # ── Population CAGR ───────────────────────────────────────────────────
    populations = _series("total_population")
    if len(populations) >= 2:
        start_yr, start_pop = populations[0]
        end_yr, end_pop = populations[-1]
        n_years = int(end_yr) - int(start_yr)
        if n_years > 0 and start_pop > 0:
            cagr = ((end_pop / start_pop) ** (1 / n_years) - 1) * 100
            lines.append(
                f"  Population CAGR ({start_yr}–{end_yr}): {cagr:.2f}%"
                f"  ({start_pop:,} → {end_pop:,})"
            )

    # ── Business net entries ──────────────────────────────────────────────
    entries = _series("total_business_entries")
    exits = _series("total_business_exits")
    if entries and exits:
        entries_map = dict(entries)
        exits_map = dict(exits)
        net_by_year = [
            (yr, entries_map[yr] - exits_map[yr])
            for yr in sorted(set(entries_map) & set(exits_map))
        ]
        if net_by_year:
            detail = ", ".join(f"{yr}={v:+,}" for yr, v in net_by_year)
            lines.append(f"  Business net entries series:   {detail}")

    return "\n".join(lines)


def build_user_prompt(address: str, raw_data: dict) -> str:
    """Build the user prompt for Gemini from raw scraped property data.

    Args:
        address: Full address string (e.g. "1 Collins St, Melbourne VIC 3000").
        raw_data: Dict from property_reports.raw_scraped_data column.

    Returns:
        Formatted prompt string with all data sources and the target schema.
    """
    # ── Demographics ─────────────────────────────────────────────────────────
    demographics = raw_data.get("demographics") or {}
    demographics_text = _format_demographics(demographics)

    # ── Planning overlays ────────────────────────────────────────────────────
    overlay_codes = [
        code
        for code in (raw_data.get("overlay_codes") or [])
        if isinstance(code, str) and code
    ]
    overlay_entries = [
        entry
        for entry in (raw_data.get("overlays") or [])
        if isinstance(entry, dict)
    ]

    if not overlay_codes:
        overlay_codes = [
            entry["code"]
            for entry in overlay_entries
            if isinstance(entry.get("code"), str) and entry["code"]
        ]

    overlays_text = ", ".join(overlay_codes) if overlay_codes else "NONE DETECTED"

    overlays_lines: list[str] = []
    for entry in overlay_entries:
        code = entry.get("code")
        if not isinstance(code, str) or not code:
            continue
        severity = entry.get("severity")
        family = entry.get("family")
        summary = entry.get("summary")
        meta_parts = []
        if isinstance(severity, int):
            meta_parts.append(f"severity: {severity}/10")
        if isinstance(family, str) and family:
            meta_parts.append(f"family: {family}")
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        overlays_lines.append(f"  • {code}{meta}")
        if isinstance(summary, str) and summary:
            overlays_lines.append(f"    {summary}")

    overlays_enriched_text = "\n".join(overlays_lines) if overlays_lines else "NONE DETECTED"

    def _display(value: object) -> str:
        return str(value) if value is not None else "NOT AVAILABLE"

    # ── NBN (updated adapter returns a nested dict) ───────────────────────────
    nbn = raw_data.get("nbn") or {}
    nbn_text = json.dumps(nbn, indent=2) if nbn else "NOT AVAILABLE"

    # ── Scraped council text (sanitised + capped) ─────────────────────────────
    council_apps_raw = raw_data.get("council_planning_applications_text") or ""
    council_apps = (
        _sanitise(council_apps_raw, _MAX_SCRAPED_TEXT_CHARS)
        if council_apps_raw
        else "NOT AVAILABLE"
    )

    council_minutes_raw = raw_data.get("council_meeting_minutes_text") or ""
    council_minutes = (
        _sanitise(council_minutes_raw, _MAX_COUNCIL_MINUTES_CHARS)
        if council_minutes_raw
        else "NOT AVAILABLE"
    )

    # ── Constraint summary ────────────────────────────────────────────────────
    constraint_summary = raw_data.get("constraint_summary") or []
    constraint_text = (
        "\n".join(f"  - {c}" for c in constraint_summary)
        if constraint_summary
        else "  NONE"
    )

    # ── Address is also untrusted input ───────────────────────────────────────
    safe_address = _sanitise(address, 200)

    # ── Nearby schools ───────────────────────────────────────────────────────────
    schools_data = raw_data.get("nearby_schools") or {}
    schools_by_type = schools_data.get("schools_by_type") or {}
    
    schools_text_lines = []
    if schools_by_type:
        total_schools = schools_data.get("total_count", 0)
        schools_text_lines.append(f"Total schools within {schools_data.get('search_radius_km', 3)}km: {total_schools}")
        
        for school_type, schools_list in schools_by_type.items():
            schools_text_lines.append(f"\n{school_type} Schools:")
            for school in schools_list[:5]:  # Limit to top 5 per type
                catchment_status = "IN CATCHMENT" if school.get("in_catchment") else "Outside catchment"
                enrol = f", {school.get('enrolments')} students" if school.get("enrolments") else ""
                sector = f" ({school.get('sector')})" if school.get("sector") else ""
                schools_text_lines.append(f"  • {school.get('name')}{sector} — {school.get('distance_km')}km away, {catchment_status}{enrol}")
            if len(schools_list) > 5:
                schools_text_lines.append(f"  ... and {len(schools_list) - 5} more")
    
    schools_text = "\n".join(schools_text_lines) if schools_text_lines else "NOT AVAILABLE"

    return f"""Extract structured property intelligence for the following Australian property.
Address: {safe_address}

## RAW DATA SOURCES

### State Planning API Response (Authoritative — weight: HIGH)
Zoning Code: {_display(raw_data.get('zoning_code'))}
Zoning Label: {_display(raw_data.get('zoning_label'))}
LGA Name: {_display(raw_data.get('lga_name'))}
EPI Name: {_display(raw_data.get('epi_name'))}
EPI Type: {_display(raw_data.get('epi_type'))}
Heritage Area: {_display(raw_data.get('heritage_area'))}
Overlays (codes): {overlays_text}
Overlays (enriched):
{overlays_enriched_text}
Flood Risk Classification: {_display(raw_data.get('flood_risk'))}
Bushfire Risk Classification: {_display(raw_data.get('bushfire_risk'))}
Airport Corridor: {_display(raw_data.get('airport_corridor'))}
Requires Planning Permit: {_display(raw_data.get('requires_planning_permit'))}
Development Plan Required: {_display(raw_data.get('development_plan_required'))}
Constraint Score: {raw_data.get('constraint_score') if raw_data.get('constraint_score') is not None else 'NOT AVAILABLE'}
Constraint Summary:
{constraint_text}

### NBN Co API Response (Authoritative — weight: HIGH)
{nbn_text}

### ABS Regional Demographics — {demographics.get('lga_name', 'LGA')} (Authoritative — weight: HIGH)
{demographics_text}

### Council Planning Portal — Applications (Scraped HTML — weight: MEDIUM)
{council_apps}

### Council Meeting Minutes (Extracted PDF Text — weight: MEDIUM)
{council_minutes}

### Nearby Schools (from public datasets — weight: MEDIUM)
{schools_text}

---

Return a JSON object that exactly matches this schema.
Use the type annotations as targets — do not copy the annotation strings as values.
The disclaimer field in roi_scenarios must contain exactly the string shown.

Notes on the demographic_snapshot schema:
- population_cagr_5yr_pct: use the pre-computed CAGR value from the trend signals section above
- house_price_cagr_5yr_pct: use the pre-computed house price CAGR from trend signals
- dominant_migration_driver: classify as OVERSEAS if |net_overseas_migration| > |net_internal_migration|, INTERNAL if the reverse, BALANCED if within 20%% of each other
- net_business_entries: use the pre-computed net entries series; use the latest available year

Notes on the demographic_trend_analysis schema:
- All verdict enums must be one of the exact strings listed — never null unless time_series has fewer than 2 data points for that metric
- All _note fields are REQUIRED strings of 1–2 sentences. They must cite specific numbers from the data (years, percentages, absolute values). Never write vague notes like "trend is positive".
- population_momentum: base verdict on the trend calc provided in the Pre-Computed Trend Signals section
- migration_trend: assess the direction of net_overseas_migration over 3+ years using the series above
- housing_supply_pressure: cross-reference the dwelling approvals series against the population growth series — declining approvals + sustained population growth = UNDERSUPPLY
- price_growth_trend: use the peak and latest values from the pre-computed signals; if latest YoY is <0.5%%, classify as NEGATIVE
- business_health_trend: use the net entries series — is net positive and growing, flat, or shrinking?
- rental_demand_outlook: synthesise migration_trend + population_momentum + housing_supply_pressure
- overall_investment_signal: synthesise ALL five trend dimensions; the note must name both positives and risks

Notes on the narrative schema:
All narrative fields are REQUIRED. Write in plain English as if briefing a sophisticated
property investor who is not a data analyst. Each field has a specific purpose:

- executive_summary (3–4 sentences): Open with the single most important signal for this
  property, then cover zoning character, demographic backdrop, and the rental vs. capital
  growth split. This is the first thing an investor reads — make every sentence count.

- zoning_summary (2–3 sentences): Translate the zoning code and overlays into plain English.
  Explain what an investor CAN and CANNOT do with this property. Name specific overlays and
  their practical consequences (e.g. "The Heritage Overlay means any renovation or extension
  requires a planning permit and must preserve the building's historic character").

- demographic_story (2–3 sentences): Describe WHO lives in this area and WHY that matters
  for rental demand. Lead with the dominant household type and migration driver. Connect the
  demographics to the likely tenant pool (e.g. "The median age of 29 and dominance of
  overseas arrivals points to a renter base of international students and young professionals,
  which concentrates demand in the sub-$550/week attached dwelling segment").

- market_momentum (2–3 sentences): Tell the price and supply story together — they are
  inseparable. Explain WHAT is happening to prices, WHY (using supply/approval data), and
  what the divergence between price growth and rental demand means in practical terms.
  Never just restate numbers — explain causality and implication.

- rental_case (2–3 sentences): Make the argument for or against rental demand as clearly as
  the data allows. Cite the migration and supply figures that drive the conclusion. If rental
  demand is strong but yields are compressed by high prices, say so explicitly.

- risk_summary (2–3 sentences): Name the 2–3 most material risks in plain language. These
  can be planning risks (heritage constraints), market risks (price decline), data gaps
  (crime data unavailable), or structural risks (all-cash-flow-negative scenarios).
  Do not hedge excessively — be direct about what the data shows.

- investor_context (2–3 sentences): Synthesise what this property is and is not suited for
  as an investment. Distinguish between rental income play vs. capital growth play. Note if
  the data supports one thesis more than the other. NEVER use the words "attractive",
  "recommended", "good investment", or "strong returns". Use neutral analytical language only.

NARRATIVE WRITING RULES:
1. Lead with the so-what, not the number. Wrong: "Population grew 6.52%." Right: "Melbourne's
   inner city is absorbing population at one of the fastest rates of any major Australian LGA."
2. Always explain causality. Not just WHAT happened, but WHY it matters to an investor.
3. Use concrete numbers to support claims, but embed them in sentences — never orphan a
   statistic without context.
4. Contrast signals where they diverge. "Rents are holding while prices fall" is more useful
   than two separate statements.
5. Write in active voice. Avoid "it can be seen that" or "it may be noted that".
6. Maintain a neutral, analytical tone throughout. No cheerleading, no doom.

SCHEMA:
{json.dumps(OUTPUT_SCHEMA, indent=2)}"""