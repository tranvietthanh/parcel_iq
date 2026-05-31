"""Generic HTML council adapter — headless browser scraping.

Fallback scraper for councils without a dedicated adapter.
Uses configurable CSS selectors from ``data_source_configs.config``
to navigate, search, and extract text.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from app.adapters.base import BaseAdapter
from app.services.proxy import get_proxy_config
from app.utils.robots import is_scraping_allowed

logger = logging.getLogger(__name__)


class GenericHtmlCouncilAdapter(BaseAdapter):
    """Generic council scraper driven entirely by CSS selector config."""

    def scrape(self, job: dict) -> dict:
        if not is_scraping_allowed(self.base_url, "/"):
            logger.info(
                "ROBOTS_DISALLOWED: %s — skipping council scrape", self.base_url
            )
            return {
                "council_planning_applications_text": None,
                "council_meeting_minutes_text": None,
            }

        proxy_config = get_proxy_config()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed — cannot run council adapter")
            return {
                "council_planning_applications_text": None,
                "council_meeting_minutes_text": None,
            }

        with sync_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            if proxy_config:
                launch_kwargs["proxy"] = {
                    "server": proxy_config["url"],
                    "username": proxy_config.get("username", ""),
                    "password": proxy_config.get("password", ""),
                }

            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            try:
                page.goto(self.base_url, wait_until="networkidle", timeout=30_000)
                time.sleep(3)

                # Use configurable selectors
                search_selector = self.config.get(
                    "search_input_selector", "input[type=search]"
                )
                page.fill(search_selector, job["address_string"])
                page.keyboard.press("Enter")

                results_selector = self.config.get(
                    "results_selector", ".results"
                )
                page.wait_for_selector(results_selector, timeout=15_000)

                planning_text = page.evaluate(
                    f"""() => {{
                        const el = document.querySelector('{results_selector}');
                        return el ? el.innerText : null;
                    }}"""
                )

                return {
                    "council_planning_applications_text": planning_text,
                    "council_meeting_minutes_text": None,
                    "data_sources": [
                        {
                            "name": f"{job.get('lga_name', 'Unknown')} Planning Portal",
                            "url": self.base_url,
                            "fetched_at": datetime.now(UTC).isoformat(),
                        }
                    ],
                }

            except Exception as exc:
                logger.warning(
                    "GenericHtml adapter error for %s: %s",
                    job.get("lga_name"),
                    exc,
                )
                return {
                    "council_planning_applications_text": None,
                    "council_meeting_minutes_text": None,
                    "_adapter_error": str(exc),
                }
            finally:
                browser.close()
