"""TechnologyOne council adapter — headless browser scraping.

Used by many VIC, NSW, and QLD councils that run TechnologyOne planning
portals. Launches Playwright Chromium, fills the address search, extracts
planning applications text, and optionally extracts PDF minutes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.browser_base import BaseBrowserAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# How long (ms) to wait for the results list to appear after search
_RESULTS_TIMEOUT_MS = 15_000
# Polite crawl delay between page actions (ms) — avoids hammering council servers
_CRAWL_DELAY_MS = 3_000
# Max PDFs to extract minutes from (avoid runaway downloads)
_MAX_PDF_DOWNLOADS = 3


class TechOneCouncilAdapter(BaseBrowserAdapter):
    """Scrapes council planning applications from TechnologyOne portals."""

    def _run_scrape(self, page: "Page", job: dict) -> dict:
        search_selector = self.config.get("search_input_selector", "#AddressSearch")
        results_selector = self.config.get("results_selector", ".application-list")

        # Use "domcontentloaded" — more reliable than "networkidle" on SPAs
        page.goto(self.base_url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for the search input to be ready before interacting
        page.wait_for_selector(search_selector, state="visible", timeout=10_000)

        # Polite crawl delay (non-blocking — uses Playwright's internal loop)
        page.wait_for_timeout(_CRAWL_DELAY_MS)

        page.fill(search_selector, job["address_string"])
        page.keyboard.press("Enter")

        # Wait for results — raise clearly if they never appear
        try:
            page.wait_for_selector(
                results_selector, state="visible", timeout=_RESULTS_TIMEOUT_MS
            )
        except Exception:
            raise RuntimeError(
                f"Results selector {results_selector!r} not found after search "
                f"on {self.base_url} — portal structure may have changed"
            )

        # Extract text using the configurable results selector (not hardcoded)
        planning_text: str | None = page.evaluate(
            "(selector) => { const el = document.querySelector(selector); "
            "return el ? el.innerText.trim() || null : null; }",
            results_selector,
        )

        # Collect PDF links and download up to _MAX_PDF_DOWNLOADS
        pdf_links: list[str] = page.eval_on_selector_all(
            "a[href$='.pdf']",
            "els => els.map(e => e.href)",
        )

        minutes_texts: list[str] = []
        for pdf_url in pdf_links[:_MAX_PDF_DOWNLOADS]:
            # Pass the browser page so we share session cookies
            text = self._extract_pdf(pdf_url, job["property_id"], page)
            if text:
                minutes_texts.append(text)

        return {
            "council_planning_applications_text": planning_text,
            # Join multiple PDFs with a separator so callers can split if needed
            "council_meeting_minutes_text": "\n\n---\n\n".join(minutes_texts) or None,
            "data_sources": [
                {
                    "name": f"{job.get('lga_name', 'Unknown')} Planning Portal",
                    "url": self.base_url,
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
            ],
        }
