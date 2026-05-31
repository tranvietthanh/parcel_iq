"""Lite PDF report generator for raw property scraped data."""

from __future__ import annotations

from io import BytesIO
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.frames import Frame

# Color palette
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


def make_styles() -> dict[str, ParagraphStyle]:
    """Create a set of paragraph styles for the report."""
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
    }


def _header_footer(canvas, doc):
    """Render page header and footer."""
    canvas.saveState()
    # Header
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 10 * mm, PAGE_W, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGIN, PAGE_H - 6.5 * mm, "PROPERTY INTELLIGENCE LITE REPORT")
    # Footer
    canvas.setFillColor(LIGHT_GREY)
    canvas.rect(0, 0, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(MID_GREY)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(
        MARGIN,
        2.8 * mm,
        "This report contains publicly available data and does not constitute financial advice.",
    )
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(PAGE_W - MARGIN, 2.8 * mm, f"Page {doc.page}")
    canvas.restoreState()


class LiteReportDoc(BaseDocTemplate):
    """PDF document template for lite reports."""

    def __init__(self, output: BytesIO):
        super().__init__(
            output,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=14 * mm,
            bottomMargin=12 * mm,
            title="Property Lite Report",
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
    """Create a horizontal divider line."""
    return HRFlowable(width="100%", thickness=thickness, color=colour, spaceAfter=4, spaceBefore=2)


def section_title(text: str, styles: dict[str, ParagraphStyle]) -> list:
    """Create a section title with divider."""
    return [divider(NAVY, 1.2), Paragraph(text.upper(), styles["section_header"])]


def two_col_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    """Create a two-column key-value table."""
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


def build_cover(address: str, styles: dict[str, ParagraphStyle]) -> list:
    """Build the cover page."""
    banner = Table(
        [
            [Paragraph("PROPERTY INTELLIGENCE", styles["subsection_header"])],
            [Paragraph(address or "Property Report", styles["cover_title"])],
            [Paragraph("Lite Report — Public Data Preview", styles["cover_sub"])],
        ],
        colWidths=[CONTENT_W],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 1, TEAL),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    return [
        banner,
        Spacer(1, 5 * mm),
        Paragraph(
            "This lite report summarizes key property information from public data sources. "
            "Sign in for full analysis with LLM-powered insights.",
            styles["body"],
        ),
        Spacer(1, 2 * mm),
        Paragraph(f"Generated {datetime.now():%d %b %Y %H:%M}", styles["body_small"]),
    ]


def build_demographics(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    """Build demographics section from raw scraped data."""
    story = section_title("Demographics", styles)

    demographics = data.get("demographics", {})
    latest = demographics.get("latest", {})

    if not latest:
        story.append(Paragraph("No demographic data available.", styles["body_small"]))
        return story

    rows = [
        ("Total Population", f"{latest.get('total_population', 0):,}"),
        ("Median Age", f"{latest.get('median_age_persons_years', '—')} years"),
        ("LGA", latest.get("lga_name", "—")),
    ]
    story.append(two_col_table(rows, styles))

    return story


def build_nbn(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    """Build NBN connectivity section."""
    story = section_title("Connectivity (NBN)", styles)

    nbn = data.get("nbn", {})

    if not nbn:
        story.append(Paragraph("No NBN data available.", styles["body_small"]))
        return story

    rows = [
        ("Technology Type", nbn.get("tech_type", "—")),
        ("Service Status", nbn.get("service_status", "—")),
        ("Target Quarter", nbn.get("target_eligibility_quarter", "—")),
    ]
    story.append(two_col_table(rows, styles))

    return story


def build_risk_factors(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    """Build risk factors section."""
    story = section_title("Risk Summary", styles)

    rows = [
        ("Flood Risk", data.get("flood_risk", "—")),
        ("Bushfire Risk", data.get("bushfire_risk", "—")),
        ("Zoning Code", data.get("zoning_code", "—")),
    ]
    story.append(two_col_table(rows, styles))

    return story


def build_schools(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list:
    """Build nearby schools section."""
    story = section_title("Local Schools", styles)

    schools = data.get("nearby_schools", [])

    if not schools or not isinstance(schools, list) or len(schools) == 0:
        story.append(Paragraph("No school data available in lite preview.", styles["body_small"]))
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "Sign in to see detailed school catchment information, enrolments, and distance analysis.",
                styles["body_small"],
            )
        )
        return story

    # Build schools table
    rows: list[list[Any]] = []
    for school in schools[:6]:  # Max 6 schools for readability
        rows.append(
            [
                Paragraph(school.get("name", ""), styles["body_small"]),
                Paragraph(f"{school.get('distance_km', 0):.2f} km", styles["body_small"]),
            ]
        )

    t = Table(rows, colWidths=[CONTENT_W * 0.7, CONTENT_W * 0.3])
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
    story.append(t)

    return story


def build_cta(styles: dict[str, ParagraphStyle]) -> list:
    """Build call-to-action section."""
    story = [Spacer(1, 4 * mm)]
    
    cta_box = Table(
        [
            [
                Paragraph(
                    "<b>Want Full Analysis?</b><br/>Sign in to unlock "
                    "LLM-powered insights, investment signals, trend analysis, and more.",
                    styles["body"],
                )
            ]
        ],
        colWidths=[CONTENT_W],
    )
    cta_box.setStyle(
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
    story.append(cta_box)

    return story


def generate_lite_pdf_bytes(
    raw_data: dict[str, Any],
    address: str = "",
) -> bytes:
    """
    Generate a lite PDF report from raw scraped property data.

    Args:
        raw_data: Dictionary with keys: demographics, nbn, flood_risk, bushfire_risk,
                  zoning_code, nearby_schools
        address: Property address string for the cover page

    Returns:
        PDF document as bytes
    """
    output = BytesIO()
    styles = make_styles()
    doc = LiteReportDoc(output)

    story = []
    story += build_cover(address, styles)
    story.append(PageBreak())
    story += build_demographics(raw_data, styles)
    story.append(Spacer(1, 4 * mm))
    story += build_nbn(raw_data, styles)
    story.append(Spacer(1, 4 * mm))
    story += build_risk_factors(raw_data, styles)
    story.append(Spacer(1, 4 * mm))
    story += build_schools(raw_data, styles)
    story += build_cta(styles)

    doc.build(story)
    return output.getvalue()
