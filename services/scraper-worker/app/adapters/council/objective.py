"""Objective council adapter — headless browser scraping.

Used by councils that run the Objective ECM planning portal (common in VIC).
Similar pattern to TechOneCouncilAdapter but with Objective-specific
selectors and a submit-button navigation flow.

Inherits shared browser lifecycle, proxy config, robots.txt checking,
PDF extraction, and failure screenshot logic from BaseBrowserAdapter.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.browser_base import BaseBrowserAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

_RESULTS_TIMEOUT_MS = 15_000
_CRAWL_DELAY_MS = 3_000
_MAX_PDF_DOWNLOADS = 3


class ObjectiveCouncilAdapter(BaseBrowserAdapter):
    """Scrapes council planning applications from Objective ECM portals."""

    def _run_scrape(self, page: "Page", job: dict) -> dict:
        search_selector = self.config.get("search_input_selector", "#txtSearch")
        submit_selector = self.config.get("submit_selector", "#btnSearch")
        results_selector = self.config.get("results_selector", ".search-results")

        page.goto(self.base_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector(search_selector, state="visible", timeout=10_000)
        page.wait_for_timeout(_CRAWL_DELAY_MS)

        page.fill(search_selector, job["address_string"])

        # Objective portals have an explicit search button; fall back to Enter
        if page.query_selector(submit_selector):
            page.click(submit_selector)
        else:
            page.keyboard.press("Enter")

        try:
            page.wait_for_selector(
                results_selector, state="visible", timeout=_RESULTS_TIMEOUT_MS
            )
        except Exception:
            raise RuntimeError(
                f"Results selector {results_selector!r} not found after search "
                f"on {self.base_url} — portal structure may have changed"
            )

        # Pass selector as an argument — never interpolate config values into JS strings
        planning_text: str | None = page.evaluate(
            "(selector) => { const el = document.querySelector(selector); "
            "return el ? el.innerText.trim() || null : null; }",
            results_selector,
        )

        pdf_links: list[str] = page.eval_on_selector_all(
            "a[href$='.pdf']",
            "els => els.map(e => e.href)",
        )

        minutes_texts: list[str] = []
        for pdf_url in pdf_links[:_MAX_PDF_DOWNLOADS]:
            text = self._extract_pdf(pdf_url, job["property_id"], page)
            if text:
                minutes_texts.append(text)

        return {
            "council_planning_applications_text": planning_text,
            "council_meeting_minutes_text": "\n\n---\n\n".join(minutes_texts) or None,
            "data_sources": [
                {
                    "name": f"{job.get('lga_name', 'Unknown')} Planning Portal",
                    "url": self.base_url,
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
            ],
        }
