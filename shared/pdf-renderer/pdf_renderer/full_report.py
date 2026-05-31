"""Property Intelligence PDF Report Generator.

Converts structured LLM report JSON into an investor-ready PDF document.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from datetime import datetime
from io import BytesIO
from typing import Any

import httpx
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.platypus import (
    BaseDocTemplate,
    HRFlowable,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.frames import Frame

NAVY = HexColor("#0D1F3C")
TEAL = HexColor("#0B7A75")
TEAL_LIGHT = HexColor("#E6F4F3")
GOLD = HexColor("#C9963A")
GOLD_LIGHT = HexColor("#FDF5E6")
MID_GREY = HexColor("#6B7280")
LIGHT_GREY = HexColor("#F3F4F6")
RED = HexColor("#DC2626")
RED_LIGHT = HexColor("#FEF2F2")
GREEN = HexColor("#16A34A")
GREEN_LIGHT = HexColor("#F0FDF4")
AMBER = HexColor("#D97706")
AMBER_LIGHT = HexColor("#FFFBEB")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def signal_colours(signal: str | None) -> tuple[Any, Any, Any]:
    mapping = {
        "POSITIVE": (GREEN_LIGHT, GREEN, GREEN),
        "IMPROVING": (GREEN_LIGHT, GREEN, GREEN),
        "STRONG": (GREEN_LIGHT, GREEN, GREEN),
        "ACCELERATING": (GREEN_LIGHT, GREEN, GREEN),
        "STRENGTHENING": (GREEN_LIGHT, GREEN, GREEN),
        "UNDERSUPPLY": (AMBER_LIGHT, AMBER, AMBER),
        "STABLE": (LIGHT_GREY, MID_GREY, MID_GREY),
        "BALANCED": (LIGHT_GREY, MID_GREY, MID_GREY),
        "NEUTRAL": (LIGHT_GREY, MID_GREY, MID_GREY),
        "MODERATE": (GOLD_LIGHT, GOLD, GOLD),
        "DECELERATING": (AMBER_LIGHT, AMBER, AMBER),
        "WEAKENING": (AMBER_LIGHT, AMBER, AMBER),
        "NEGATIVE": (RED_LIGHT, RED, RED),
        "CAUTIONARY": (RED_LIGHT, RED, RED),
        "DETERIORATING": (RED_LIGHT, RED, RED),
        "OVERSUPPLY": (RED_LIGHT, RED, RED),
        "WEAK": (RED_LIGHT, RED, RED),
    }
    return mapping.get(signal or "", (LIGHT_GREY, MID_GREY, MID_GREY))


def make_styles() -> dict[str, ParagraphStyle]:
    getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=WHITE,
            leading=28,
            alignment=TA_LEFT,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            fontName="Helvetica",
            fontSize=11,
            textColor=HexColor("#B8C8DC"),
            leading=15,
        ),
        "section_header": ParagraphStyle(
            "section_header",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            leading=16,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "subsection_header": ParagraphStyle(
            "subsection_header",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=TEAL,
            leading=13,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=8.5,
            textColor=HexColor("#374151"),
            leading=12,
            spaceAfter=4,
        ),
        "body_small": ParagraphStyle(
            "body_small",
            fontName="Helvetica",
            fontSize=7.5,
            textColor=MID_GREY,
            leading=10,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=MID_GREY,
            leading=10,
        ),
        "value": ParagraphStyle(
            "value",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=NAVY,
            leading=12,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=NAVY,
            leading=18,
            alignment=TA_CENTER,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName="Helvetica",
            fontSize=7,
            textColor=MID_GREY,
            leading=9,
            alignment=TA_CENTER,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer",
            fontName="Helvetica-Oblique",
            fontSize=6.5,
            textColor=MID_GREY,
            leading=9,
            alignment=TA_CENTER,
        ),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 10 * mm, PAGE_W, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGIN, PAGE_H - 6.5 * mm, "PROPERTY INTELLIGENCE REPORT")
    canvas.setFillColor(LIGHT_GREY)
    canvas.rect(0, 0, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(MID_GREY)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(
        MARGIN,
        2.8 * mm,
        "This report is factual data only and does not constitute financial advice.",
    )
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(PAGE_W - MARGIN, 2.8 * mm, f"Page {doc.page}")
    canvas.restoreState()


class PropertyReportDoc(BaseDocTemplate):
    def __init__(self, output: BytesIO):
        super().__init__(
            output,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=14 * mm,
            bottomMargin=12 * mm,
            title="Property Intelligence Report",
        )
        body_frame = Frame(
            MARGIN,
            12 * mm,
            CONTENT_W,
            PAGE_H - 28 * mm,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=2 * mm,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(id="body", frames=[body_frame], onPage=_header_footer),
            ]
        )


def divider(colour=TEAL, thickness=0.6) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=colour, spaceAfter=4, spaceBefore=2)


def section_title(text: str, styles: dict[str, ParagraphStyle]) -> list:
    return [divider(NAVY, 1.2), Paragraph(text.upper(), styles["section_header"])]


def two_col_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(k, styles["label"]), Paragraph(str(v), styles["value"])] for k, v in rows]
    t = Table(data, colWidths=[CONTENT_W * 0.42, CONTENT_W * 0.58])
    t.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def overlay_table(overlays: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[Any]] = []
    for ov in overlays:
        code = ov.get("code") or ""
        family = ov.get("family") or "other"
        summary = ov.get("summary") or ""
        severity = ov.get("severity")
        rows.append(
            [
                Paragraph(f"<b>{code}</b>", styles["body"]),
                Paragraph(f"{family}", styles["body_small"]),
                Paragraph(f"{severity if severity is not None else '—'}/10", styles["body_small"]),
                Paragraph(summary, styles["body_small"]),
            ]
        )
    t = Table(rows, colWidths=[20 * mm, 24 * mm, 16 * mm, CONTENT_W - 60 * mm])
    t.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def build_cover(data: dict[str, Any], address: str, styles: dict[str, ParagraphStyle]) -> list:
    trend = data.get("demographic_trend_analysis", {})
    signal = (trend.get("overall_investment_signal") or "PENDING").replace("_", " ")
    signal_bg, signal_fg, _ = signal_colours(trend.get("overall_investment_signal"))

    banner = Table(
        [
            [
                Paragraph("PROPERTY INTELLIGENCE", styles["subsection_header"]),
            ],
            [Paragraph(address or "Property Report", styles["cover_title"])],
            [Paragraph(f"Overall investment signal: <b>{signal}</b>", styles["cover_sub"])],
        ],
        colWidths=[CONTENT_W],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 1, signal_fg if signal_bg else TEAL),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    snap = data.get("demographic_snapshot", {})
    kpis = [
        ("Population", f"{snap.get('total_population', 0):,}" if snap.get("total_population") else "—"),
        (
            "House Median",
            f"${snap.get('established_house_median_price_aud', 0):,}" if snap.get("established_house_median_price_aud") else "—",
        ),
        ("Rental Outlook", (trend.get("rental_demand_outlook") or "—").replace("_", " ")),
    ]
    kpi_t = Table(
        [[Paragraph(v, styles["kpi_value"]) for _, v in kpis], [Paragraph(k, styles["kpi_label"]) for k, _ in kpis]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    kpi_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
            ]
        )
    )

    cover_story: list[Any] = [banner, Spacer(1, 5 * mm), kpi_t]
    cover_story += _build_cover_map_block(data, styles)
    cover_story += [Spacer(1, 2 * mm), Paragraph(f"Generated {datetime.now():%d %b %Y %H:%M}", styles["body_small"])]
    return cover_story


def build_narrative(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    narrative = data.get("narrative") or {}
    story = section_title("Analyst Narrative", styles)
    ordered_keys = [
        ("Executive Summary", "executive_summary"),
        ("Zoning Summary", "zoning_summary"),
        ("Demographic Story", "demographic_story"),
        ("Market Momentum", "market_momentum"),
        ("Rental Case", "rental_case"),
        ("Risk Summary", "risk_summary"),
        ("Investor Context", "investor_context"),
    ]
    for title, key in ordered_keys:
        value = narrative.get(key)
        if value:
            story.append(Paragraph(title, styles["subsection_header"]))
            story.append(Paragraph(value, styles["body"]))
    return story


def build_zoning(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    z = data.get("zoning_and_planning", {})
    story = section_title("Zoning & Planning", styles)
    rows = [
        ("Zoning Code", z.get("zoning_code") or "—"),
        ("Zoning Label", z.get("zoning_label") or "—"),
        ("LGA", z.get("lga_name") or "—"),
        ("Heritage Area", "Yes" if z.get("heritage_area") else "No"),
        ("Subdivision", z.get("subdivision_potential") or "—"),
        ("EPI Name", z.get("epi_name") or "—"),
        ("Confidence", f"{(z.get('confidence_score') or 0) * 100:.0f}%"),
    ]
    story.append(two_col_table(rows, styles))
    overlays = z.get("overlays") or []
    if overlays:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Planning Overlays", styles["subsection_header"]))
        story.append(overlay_table(overlays, styles))
    return story


def build_risk(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    rf = data.get("risk_factors", {})
    story = section_title("Risk Factors", styles)
    rows = [
        ("Flood Risk", rf.get("flood", {}).get("risk") or "—"),
        ("Bushfire Risk", rf.get("bushfire", {}).get("risk") or "—"),
        ("Crime Density", rf.get("crime_density", {}).get("rating") or "—"),
    ]
    story.append(two_col_table(rows, styles))
    return story


def build_connectivity(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    conn = data.get("connectivity", {})
    story = section_title("Connectivity", styles)
    rows = [
        ("NBN Technology", conn.get("nbn_tech_type") or "—"),
        ("Service Status", conn.get("nbn_service_status") or "—"),
        ("Tech Change Status", conn.get("nbn_tech_change_status") or "—"),
        ("Target Quarter", conn.get("nbn_target_eligibility_quarter") or "—"),
    ]
    story.append(two_col_table(rows, styles))
    story += _build_location_context(data, styles)
    return story


def build_education(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    """Build education section with nearby schools."""
    edu = data.get("education", {})
    story = section_title("Local Schools", styles)
    
    # Add summary narrative if available
    summary = edu.get("nearby_schools_summary")
    if summary:
        story.append(Paragraph(summary, styles["body"]))
        story.append(Spacer(1, 3 * mm))
    
    # Build schools table
    primary = edu.get("primary_schools", [])
    secondary = edu.get("secondary_schools", [])
    
    # Combine schools with their type; limit to 8 total for readability
    all_schools = []
    for school in primary[:4]:  # Max 4 primary
        all_schools.append({
            "name": school.get("name", ""),
            "distance": school.get("distance_km", 0),
            "in_catchment": school.get("in_catchment", False),
            "enrolments": school.get("enrolments"),
            "type": "Primary",
        })
    for school in secondary[:4]:  # Max 4 secondary
        all_schools.append({
            "name": school.get("name", ""),
            "distance": school.get("distance_km", 0),
            "in_catchment": school.get("in_catchment", False),
            "enrolments": school.get("enrolments"),
            "type": "Secondary",
        })
    
    if all_schools:
        rows: list[list[Any]] = []
        for school in all_schools:
            catchment_badge = "✓ IN" if school["in_catchment"] else "Outside"
            enrol_text = f"{school['enrolments']:,}" if school["enrolments"] else "—"
            
            rows.append(
                [
                    Paragraph(f"<b>{school['type']}</b>", styles["body_small"]),
                    Paragraph(school["name"], styles["body_small"]),
                    Paragraph(f"{school['distance']:.2f} km", styles["body_small"]),
                    Paragraph(catchment_badge, styles["body_small"]),
                    Paragraph(enrol_text, styles["body_small"]),
                ]
            )
        
        t = Table(rows, colWidths=[18 * mm, CONTENT_W * 0.45, 18 * mm, 20 * mm, 22 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),  # Bold catchment column
                ]
            )
        )
        story.append(t)
    else:
        story.append(Paragraph("No schools found within 3km radius.", styles["body"]))
    
    return story


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    value = value * 100 if abs(value) < 1 else value
    return f"{value:+.2f}%"


def _currency(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _signed_int(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):+,}"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_property_location(data: dict[str, Any]) -> tuple[float | None, float | None]:
    location = data.get("_property_location") or {}
    latitude = _safe_float(location.get("latitude"))
    longitude = _safe_float(location.get("longitude"))
    return latitude, longitude


def _map_unavailable_detail(reason: str | None) -> str:
    if reason == "disabled":
        return "Property imagery disabled (set PROPERTY_IMAGE_ENRICHMENT_ENABLED=true)."
    if reason == "missing_api_key":
        return "GOOGLE_MAPS_API_KEY is not configured."
    if reason and reason.startswith("request_error:"):
        err = reason.split(":", 1)[1]
        return f"Image provider unreachable ({err}). Check DNS/egress configuration."
    if reason and reason.startswith("status:"):
        status = reason.split(":", 1)[1]
        return f"Image provider returned HTTP {status}."
    if reason == "invalid_content_type":
        return "Image provider returned a non-image response."
    return "Property imagery unavailable."


def _extract_time_series(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_time_series = data.get("_raw_demographics_time_series")
    if not isinstance(raw_time_series, dict):
        return {}

    extracted: dict[str, dict[str, Any]] = {}
    for year, values in raw_time_series.items():
        if not isinstance(year, str) or not isinstance(values, dict):
            continue
        extracted[year] = values
    return extracted


def _build_metric_series(
    time_series: dict[str, dict[str, Any]],
    metric_key: str,
) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for year in sorted(time_series.keys()):
        raw_val = time_series[year].get(metric_key)
        value = _safe_float(raw_val)
        if value is not None:
            points.append((year, value))
    return points


def _line_chart(
    title: str,
    points: list[tuple[str, float]],
    width: float,
    height: float,
    line_color: HexColor,
    value_formatter,
) -> Drawing:
    chart = Drawing(width, height)
    chart.add(Rect(0, 0, width, height, fillColor=WHITE, strokeColor=HexColor("#E5E7EB"), strokeWidth=0.8))
    chart.add(String(8, height - 12, title, fontName="Helvetica-Bold", fontSize=7, fillColor=MID_GREY))

    plot_left = 18
    plot_right = width - 10
    plot_bottom = 16
    plot_top = height - 18

    chart.add(Line(plot_left, plot_bottom, plot_right, plot_bottom, strokeColor=HexColor("#E5E7EB"), strokeWidth=0.8))
    chart.add(Line(plot_left, plot_bottom, plot_left, plot_top, strokeColor=HexColor("#E5E7EB"), strokeWidth=0.8))

    if len(points) < 2:
        chart.add(String(plot_left + 6, (plot_bottom + plot_top) / 2, "No trend data", fontName="Helvetica", fontSize=7, fillColor=MID_GREY))
        return chart

    values = [v for _, v in points]
    min_v = min(values)
    max_v = max(values)
    if abs(max_v - min_v) < 1e-9:
        min_v -= 1.0
        max_v += 1.0

    x_step = (plot_right - plot_left) / (len(points) - 1)

    def x_pos(index: int) -> float:
        return plot_left + index * x_step

    def y_pos(value: float) -> float:
        return plot_bottom + (value - min_v) / (max_v - min_v) * (plot_top - plot_bottom)

    coords: list[float] = []
    for idx, (_, value) in enumerate(points):
        coords.extend([x_pos(idx), y_pos(value)])

    chart.add(PolyLine(coords, strokeColor=line_color, strokeWidth=1.6))
    for idx, (_, value) in enumerate(points):
        chart.add(Circle(x_pos(idx), y_pos(value), 1.8, fillColor=line_color, strokeColor=WHITE, strokeWidth=0.5))

    chart.add(String(plot_left, 4, points[0][0], fontName="Helvetica", fontSize=6, fillColor=MID_GREY))
    chart.add(String(plot_right - 18, 4, points[-1][0], fontName="Helvetica", fontSize=6, fillColor=MID_GREY))
    chart.add(String(plot_left + 2, plot_top + 2, value_formatter(max_v), fontName="Helvetica", fontSize=6, fillColor=MID_GREY))
    chart.add(String(plot_left + 2, plot_bottom + 2, value_formatter(min_v), fontName="Helvetica", fontSize=6, fillColor=MID_GREY))

    return chart


def _build_demographic_charts(
    data: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    variant: str,
) -> list[Any]:
    time_series = _extract_time_series(data)
    if not time_series:
        return [Paragraph("Trend charts unavailable (no time-series data).", styles["body_small"])]

    chart_specs: list[tuple[str, list[tuple[str, float]], HexColor, Any]] = [
        (
            "Population",
            _build_metric_series(time_series, "total_population"),
            TEAL,
            lambda v: f"{int(v):,}",
        ),
        (
            "House Median Price",
            _build_metric_series(time_series, "established_house_median_price_aud"),
            GOLD,
            lambda v: f"${int(v):,}",
        ),
        (
            "Dwelling Approvals",
            _build_metric_series(time_series, "total_dwelling_approvals"),
            AMBER,
            lambda v: f"{int(v):,}",
        ),
    ]

    available = [spec for spec in chart_specs if len(spec[1]) >= 2]
    if not available:
        return [Paragraph("Trend charts unavailable (insufficient data points).", styles["body_small"])]

    max_charts = 1 if variant == "lite" else 3
    selected = available[:max_charts]

    full_chart_width = CONTENT_W
    half_chart_width = (CONTENT_W - 6) / 2
    chart_height = 55 * mm

    drawings = [
        _line_chart(
            title=title,
            points=points,
            width=full_chart_width if variant == "lite" else half_chart_width,
            height=chart_height,
            line_color=color,
            value_formatter=formatter,
        )
        for title, points, color, formatter in selected
    ]

    if variant == "lite" or len(drawings) == 1:
        table_data = [[drawings[0]]]
        col_widths = [CONTENT_W]
    else:
        rows: list[list[Any]] = []
        row: list[Any] = []
        for drawing in drawings:
            row.append(drawing)
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            row.append("")
            rows.append(row)
        table_data = rows
        col_widths = [half_chart_width, half_chart_width]

    table = Table(table_data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return [table]


def _fetch_satellite_bytes(lat: float, lng: float) -> tuple[bytes | None, str | None]:
    """Fetch a Google Maps Static API satellite hybrid image centred on the property.

    Returns (image_bytes, None) on success, or (None, reason_str) on failure.
    """
    if os.getenv("PROPERTY_IMAGE_ENRICHMENT_ENABLED", "false").lower() != "true":
        return None, "disabled"
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return None, "missing_api_key"

    timeout = float(os.getenv("PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS", "4.0"))
    try:
        response = httpx.get(
            "https://maps.googleapis.com/maps/api/staticmap",
            params={
                "center": f"{lat:.6f},{lng:.6f}",
                "zoom": 20,
                "size": "640x640",
                "scale": 2,
                "maptype": "hybrid",
                "markers": f"color:red|{lat:.6f},{lng:.6f}",
                "key": api_key,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return None, f"request_error:{type(exc).__name__}"

    if response.status_code != 200:
        return None, f"status:{response.status_code}"
    if "image" not in (response.headers.get("content-type") or "").lower():
        return None, "invalid_content_type"
    return response.content, None


def _fetch_streetview_bytes(lat: float, lng: float, heading: int) -> tuple[bytes | None, str | None]:
    """Fetch a single Google Street View Static API image at the given heading.

    Returns (None, 'no_coverage') when Google returns its grey placeholder (< 8 KB).
    Returns (None, reason_str) on network / API errors.
    """
    if os.getenv("PROPERTY_IMAGE_ENRICHMENT_ENABLED", "false").lower() != "true":
        return None, "disabled"
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return None, "missing_api_key"

    timeout = float(os.getenv("PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS", "4.0"))
    try:
        response = httpx.get(
            "https://maps.googleapis.com/maps/api/streetview",
            params={
                "size": "640x420",
                "location": f"{lat:.6f},{lng:.6f}",
                "heading": heading,
                "pitch": 0,
                "fov": 90,
                "key": api_key,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return None, f"request_error:{type(exc).__name__}"

    if response.status_code != 200:
        return None, f"status:{response.status_code}"
    if "image" not in (response.headers.get("content-type") or "").lower():
        return None, "invalid_content_type"
    # Google returns a small grey placeholder (~5-6 KB) when no coverage exists.
    if len(response.content) < 8_000:
        return None, "no_coverage"
    return response.content, None


def _fetch_all_streetview_bytes(lat: float, lng: float) -> dict[int, bytes]:
    """Fetch Street View images for 6 compass headings concurrently.

    Returns a dict of {heading: image_bytes} for headings that returned valid imagery.
    Missing headings (no coverage, API errors) are simply omitted from the result.
    """
    headings = [315, 0, 45, 135, 180, 225]
    results: dict[int, bytes] = {}

    def fetch_one(h: int) -> tuple[int, bytes | None]:
        img_bytes, _ = _fetch_streetview_bytes(lat, lng, h)
        return h, img_bytes

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_one, h): h for h in headings}
        for future in concurrent.futures.as_completed(futures):
            h, img_bytes = future.result()
            if img_bytes is not None:
                results[h] = img_bytes

    return results


def _build_cover_map_block(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    latitude, longitude = _extract_property_location(data)
    if latitude is None or longitude is None:
        return [
            Spacer(1, 4 * mm),
            Paragraph("Location map unavailable (missing property coordinates).", styles["body_small"]),
        ]

    map_bytes, reason = _fetch_satellite_bytes(latitude, longitude)
    if map_bytes:
        map_image = Image(BytesIO(map_bytes), width=CONTENT_W, height=130 * mm)
        map_image.hAlign = "LEFT"
        return [
            Spacer(1, 4 * mm),
            map_image,
            Spacer(1, 1.5 * mm),
            Paragraph(
                "Map imagery \u00a9 Google. Approximate location shown.",
                styles["body_small"],
            ),
        ]

    placeholder = Table(
        [[Paragraph(_map_unavailable_detail(reason), styles["body_small"])]],
        colWidths=[CONTENT_W],
        rowHeights=[130 * mm],
    )
    placeholder.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                ("BOX", (0, 0), (-1, -1), 0.6, HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return [Spacer(1, 4 * mm), placeholder]


def _build_location_context(
    data: dict[str, Any],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    latitude, longitude = _extract_property_location(data)
    if latitude is None or longitude is None:
        return []

    story: list[Any] = [Spacer(1, 3 * mm), Paragraph("Location Context", styles["subsection_header"])]
    story.append(
        Paragraph(
            f"Coordinates: {latitude:.5f}, {longitude:.5f}",
            styles["body_small"],
        )
    )
    return story


_STREETVIEW_HEADING_LABELS: dict[int, str] = {
    315: "NW 315\u00b0",
    0: "N 0\u00b0",
    45: "NE 45\u00b0",
    135: "SE 135\u00b0",
    180: "S 180\u00b0",
    225: "SW 225\u00b0",
}


def _build_street_view_grid(images: dict[int, bytes], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Build a 2×3 grid Table of Street View images for 6 compass headings.

    Missing headings are rendered as a light-grey placeholder cell.
    """
    # Ordered heading sequence: row 1 = NW, N; row 2 = NE, SE; row 3 = S, SW
    heading_order = [315, 0, 45, 135, 180, 225]
    cell_w = CONTENT_W / 2 - 2 * mm
    cell_h = 65 * mm

    placeholder_cell_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
            ("BOX", (0, 0), (-1, -1), 0.4, HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]
    )

    def make_cell(h: int) -> Any:
        label = _STREETVIEW_HEADING_LABELS.get(h, str(h))
        if h in images:
            img = Image(BytesIO(images[h]), width=cell_w, height=cell_h)
            img.hAlign = "CENTER"
            cell_table = Table([[img], [Paragraph(label, styles["body_small"])]], colWidths=[cell_w])
            cell_table.setStyle(
                TableStyle(
                    [
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ]
                )
            )
            return cell_table
        else:
            placeholder = Table(
                [[Paragraph(f"No coverage<br/>{label}", styles["body_small"])]],
                colWidths=[cell_w],
                rowHeights=[cell_h],
            )
            placeholder.setStyle(placeholder_cell_style)
            return placeholder

    row1 = [make_cell(h) for h in heading_order[:2]]
    row2 = [make_cell(h) for h in heading_order[2:4]]
    row3 = [make_cell(h) for h in heading_order[4:]]

    grid = Table([row1, row2, row3], colWidths=[CONTENT_W / 2] * 2)
    grid.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    attribution = Paragraph(
        "\u00a9 Google Street View. Images may not reflect current state of the property.",
        styles["body_small"],
    )
    return [grid, Spacer(1, 1.5 * mm), attribution]


def build_property_street_view(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Build the Street View page section (full report only).

    Returns an empty list when:
    - PROPERTY_IMAGE_ENRICHMENT_ENABLED is false
    - Property coordinates are unavailable
    """
    if os.getenv("PROPERTY_IMAGE_ENRICHMENT_ENABLED", "false").lower() != "true":
        return []

    latitude, longitude = _extract_property_location(data)
    if latitude is None or longitude is None:
        return []

    story: list[Any] = section_title("Property Street View", styles)
    sv_images = _fetch_all_streetview_bytes(latitude, longitude)

    if not sv_images:
        story.append(Paragraph("No Street View coverage available at this location.", styles["body"]))
        return story

    story += _build_street_view_grid(sv_images, styles)
    return story


def _build_demographic_kpi_strip(snap: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    kpis = [
        ("Population", f"{snap.get('total_population', 0):,}" if snap.get("total_population") else "—"),
        ("Pop Growth", _pct(snap.get("population_growth_pct_yoy"))),
        ("House Median", _currency(snap.get("established_house_median_price_aud"))),
        ("Approvals", f"{snap.get('total_dwelling_approvals', 0):,}" if snap.get("total_dwelling_approvals") else "—"),
    ]

    data = [
        [Paragraph(value, styles["kpi_value"]) for _, value in kpis],
        [Paragraph(label, styles["kpi_label"]) for label, _ in kpis],
    ]
    t = Table(data, colWidths=[CONTENT_W / len(kpis)] * len(kpis))
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                ("BACKGROUND", (0, 0), (-1, 0), WHITE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, HexColor("#E5E7EB")),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
            ]
        )
    )
    return t


def _build_demographic_timeline(
    time_series: dict[str, Any],
    styles: dict[str, ParagraphStyle],
) -> Table:
    years = sorted(time_series.keys())[-6:]
    headers = [Paragraph("Metric", styles["label"]) ] + [Paragraph(y, styles["label"]) for y in years]

    def metric_row(label: str, key: str, formatter) -> list[Paragraph]:
        row: list[Paragraph] = [Paragraph(label, styles["body_small"])]
        for year in years:
            year_data = time_series.get(year) or {}
            value = year_data.get(key)
            row.append(Paragraph(formatter(value), styles["body_small"]))
        return row

    rows = [
        headers,
        metric_row("Population", "total_population", lambda v: f"{int(v):,}" if isinstance(v, (int, float)) else "—"),
        metric_row("Pop growth", "population_growth_pct_yoy", _pct),
        metric_row("House median", "established_house_median_price_aud", _currency),
        metric_row("House price YoY", "house_price_growth_pct_yoy", _pct),
        metric_row("Dwelling approvals", "total_dwelling_approvals", lambda v: f"{int(v):,}" if isinstance(v, (int, float)) else "—"),
        metric_row("Net overseas mig.", "net_overseas_migration", _signed_int),
    ]

    metric_col = CONTENT_W * 0.24
    year_col = (CONTENT_W - metric_col) / max(len(years), 1)
    col_widths = [metric_col] + [year_col] * len(years)

    t = Table(rows, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def _build_demographic_narrative(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table | None:
    trend = data.get("demographic_trend_analysis") or {}
    narrative = data.get("narrative") or {}

    notes: list[str] = []
    for key in [
        "demographic_story",
        "market_momentum",
        "population_momentum_note",
        "housing_supply_pressure_note",
    ]:
        source = narrative if key in narrative else trend
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            notes.append(value.strip())

    if not notes:
        return None

    text = "<br/><br/>".join(notes[:3])
    p = Paragraph(text, styles["body"])
    box = Table([[p]], colWidths=[CONTENT_W])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.4, TEAL),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, TEAL),
            ]
        )
    )
    return box


def build_demographic_snapshot(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    snap = data.get("demographic_snapshot", {})
    raw_time_series = data.get("_raw_demographics_time_series") or {}
    story = section_title("Demographic Snapshot", styles)

    story.append(_build_demographic_kpi_strip(snap, styles))
    story.append(Spacer(1, 3 * mm))

    rows = [
        ("LGA", snap.get("lga_name") or "—"),
        ("Reference Year", snap.get("reference_year") or "—"),
        ("Total Population", f"{snap.get('total_population', 0):,}" if snap.get("total_population") else "—"),
        ("Population Growth (YoY)", _pct(snap.get("population_growth_pct_yoy"))),
        ("Population CAGR (5yr)", _pct(snap.get("population_cagr_5yr_pct"))),
        ("Median Age", f"{snap.get('median_age')} years" if snap.get("median_age") is not None else "—"),
        ("Net Overseas Migration", f"{snap.get('net_overseas_migration', 0):+,}" if snap.get("net_overseas_migration") is not None else "—"),
        ("Net Internal Migration", f"{snap.get('net_internal_migration', 0):+,}" if snap.get("net_internal_migration") is not None else "—"),
        ("House Median Price", f"${snap.get('established_house_median_price_aud', 0):,}" if snap.get("established_house_median_price_aud") else "—"),
        ("House Price Growth (YoY)", _pct(snap.get("house_price_growth_pct_yoy"))),
        ("Dwelling Approvals", f"{snap.get('total_dwelling_approvals', 0):,}" if snap.get("total_dwelling_approvals") else "—"),
        ("Approvals Growth", _pct(snap.get("dwelling_approvals_growth_pct_yoy"))),
    ]
    story.append(two_col_table(rows, styles))

    story.extend([Spacer(1, 3 * mm), Paragraph("Trend Charts", styles["subsection_header"])])
    story += _build_demographic_charts(data, styles, variant="full")

    if isinstance(raw_time_series, dict) and raw_time_series:
        story.extend([Spacer(1, 3 * mm), Paragraph("Year-over-Year Infographic", styles["subsection_header"])])
        story.append(_build_demographic_timeline(raw_time_series, styles))

    narrative_box = _build_demographic_narrative(data, styles)
    if narrative_box is not None:
        story.extend([Spacer(1, 3 * mm), Paragraph("What happened over the years", styles["subsection_header"]), narrative_box])

    return story


def build_demographic_snapshot_lite(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    snap = data.get("demographic_snapshot", {})
    story = section_title("Demographic Snapshot (Lite)", styles)

    story.append(_build_demographic_kpi_strip(snap, styles))
    story.append(Spacer(1, 3 * mm))

    rows = [
        ("LGA", snap.get("lga_name") or "—"),
        ("Reference Year", snap.get("reference_year") or "—"),
        ("Total Population", f"{snap.get('total_population', 0):,}" if snap.get("total_population") else "—"),
        ("Population Growth (YoY)", _pct(snap.get("population_growth_pct_yoy"))),
        ("Net Overseas Migration", f"{snap.get('net_overseas_migration', 0):+,}" if snap.get("net_overseas_migration") is not None else "—"),
        ("House Median Price", f"${snap.get('established_house_median_price_aud', 0):,}" if snap.get("established_house_median_price_aud") else "—"),
        ("House Price Growth (YoY)", _pct(snap.get("house_price_growth_pct_yoy"))),
        ("Dwelling Approvals", f"{snap.get('total_dwelling_approvals', 0):,}" if snap.get("total_dwelling_approvals") else "—"),
        ("Primary Household Type", snap.get("primary_household_type") or "—"),
    ]
    story.append(two_col_table(rows, styles))
    story.extend([Spacer(1, 3 * mm), Paragraph("Trend Preview", styles["subsection_header"])])
    story += _build_demographic_charts(data, styles, variant="lite")

    return story


def build_lite_upgrade_cta(styles: dict[str, ParagraphStyle]) -> list:
    story = section_title("Unlock Full Report", styles)
    body = (
        "The Lite report is a high-level preview. Purchase the Full report to access:"
        "<br/>• Year-over-year demographic infographic with trend interpretation"
        "<br/>• Full demographic trend analysis across momentum, migration, supply and price"
        "<br/>• 3-scenario ROI table with assumptions, yields and annual cash flow"
        "<br/>• Complete analyst narrative and risk context"
    )

    box = Table([[Paragraph(body, styles["body"])]], colWidths=[CONTENT_W])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), GOLD_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.5, GOLD),
                ("LINEBEFORE", (0, 0), (0, -1), 3, GOLD),
            ]
        )
    )
    story.append(box)
    story.append(Spacer(1, 3 * mm))

    teaser_rows = [
        [
            Paragraph("<b>Premium Insight</b>", styles["label"]),
            Paragraph("<b>Lite Preview</b>", styles["label"]),
            Paragraph("<b>Full Report</b>", styles["label"]),
        ],
        [
            Paragraph("Population Momentum", styles["body_small"]),
            Paragraph("🔒 Hidden", styles["body_small"]),
            Paragraph("ACCELERATING / STABLE / DECELERATING + evidence", styles["body_small"]),
        ],
        [
            Paragraph("Supply vs Demand Signal", styles["body_small"]),
            Paragraph("🔒 Hidden", styles["body_small"]),
            Paragraph("UNDERSUPPLY / BALANCED / OVERSUPPLY + implications", styles["body_small"]),
        ],
        [
            Paragraph("3-Scenario Cash Flow", styles["body_small"]),
            Paragraph("🔒 Hidden", styles["body_small"]),
            Paragraph("Conservative / Base / Optimistic with assumptions", styles["body_small"]),
        ],
        [
            Paragraph("Investor Thesis", styles["body_small"]),
            Paragraph("High-level only", styles["body_small"]),
            Paragraph("Yield vs capital-growth framing with risk trade-offs", styles["body_small"]),
        ],
    ]

    teaser_table = Table(
        teaser_rows,
        colWidths=[CONTENT_W * 0.30, CONTENT_W * 0.18, CONTENT_W * 0.52],
    )
    teaser_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(teaser_table)
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Upgrade to unlock full diagnostics, quantified scenarios, and complete evidence-backed analysis.",
            styles["body_small"],
        )
    )
    return story


def build_trend_analysis(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    trend = data.get("demographic_trend_analysis", {})
    story = section_title("Demographic Trend Analysis", styles)
    rows = [
        ("Population Momentum", trend.get("population_momentum") or "—"),
        ("Migration Trend", trend.get("migration_trend") or "—"),
        ("Housing Supply Pressure", trend.get("housing_supply_pressure") or "—"),
        ("Price Growth Trend", trend.get("price_growth_trend") or "—"),
        ("Business Health Trend", trend.get("business_health_trend") or "—"),
        ("Rental Demand Outlook", trend.get("rental_demand_outlook") or "—"),
        ("Overall Investment Signal", trend.get("overall_investment_signal") or "—"),
    ]
    story.append(two_col_table(rows, styles))

    note = trend.get("overall_investment_signal_note")
    if note:
        box = Table([[Paragraph(note, styles["body"])]], colWidths=[CONTENT_W])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("BOX", (0, 0), (-1, -1), 0.4, TEAL),
                ]
            )
        )
        story.extend([Spacer(1, 3 * mm), box])
    return story


def build_roi(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    roi = data.get("roi_scenarios", {})
    story = section_title("ROI Scenarios", styles)
    scenarios = roi.get("scenarios") or []
    if scenarios:
        rows = [[Paragraph("", styles["label"]), Paragraph("Conservative", styles["label"]), Paragraph("Base", styles["label"]), Paragraph("Optimistic", styles["label"])]]
        labels = [
            ("Interest rate", "interest_rate_percent", True),
            ("Weekly rent", "weekly_rent_aud", False),
            ("Vacancy rate", "vacancy_rate_percent", True),
            ("Gross yield", "gross_yield_percent", True),
            ("Net yield", "net_yield_percent", True),
        ]
        for label, key, is_pct in labels:
            row = [Paragraph(label, styles["body_small"])]
            for sc in scenarios:
                if key in {"gross_yield_percent", "net_yield_percent"}:
                    value = sc.get(key)
                else:
                    value = (sc.get("assumptions") or {}).get(key)
                if value is None:
                    txt = "—"
                elif is_pct:
                    num = value * 100 if abs(value) < 1 else value
                    txt = f"{num:.2f}%"
                elif key == "weekly_rent_aud":
                    txt = f"${value:,}"
                else:
                    txt = str(value)
                row.append(Paragraph(txt, styles["body_small"]))
            rows.append(row)
        t = Table(rows, colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.24, CONTENT_W * 0.24, CONTENT_W * 0.24])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#E5E7EB")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
                ]
            )
        )
        story.append(t)
    if roi.get("disclaimer"):
        story.extend([Spacer(1, 4 * mm), Paragraph(roi.get("disclaimer"), styles["disclaimer"])])
    return story




def build_report(
    data: dict[str, Any],
    output: BytesIO,
    address: str = "",
    variant: str = "full",
) -> None:
    styles = make_styles()
    doc = PropertyReportDoc(output)

    story = []
    story += build_cover(data, address, styles)
    story.append(PageBreak())
    if variant == "full":
        sv_content = build_property_street_view(data, styles)
        if sv_content:
            story += sv_content
            story.append(PageBreak())
        story += build_narrative(data, styles)
        story.append(PageBreak())
        story += build_zoning(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_risk(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_connectivity(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_education(data, styles)
        story.append(PageBreak())
        story += build_demographic_snapshot(data, styles)
        story.append(PageBreak())
        story += build_trend_analysis(data, styles)
        story.append(PageBreak())
        story += build_roi(data, styles)
    else:
        story += build_zoning(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_risk(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_connectivity(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_education(data, styles)
        story.append(PageBreak())
        story += build_demographic_snapshot_lite(data, styles)
        story.append(Spacer(1, 4 * mm))
        story += build_lite_upgrade_cta(styles)

    doc.build(story)


def generate_report_pdf_bytes(
    data: dict[str, Any] | str,
    address: str = "",
    variant: str = "full",
) -> bytes:
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("PDF generator expected report data as a JSON object")

    output = BytesIO()
    build_report(data, output, address, variant=variant)
    return output.getvalue()
