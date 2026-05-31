"""Shared base for all headless-browser council adapters.

Handles: robots.txt checking, Playwright lifecycle, proxy config, context cleanup,
failure screenshots, and PDF extraction.

Subclasses only need to implement _run_scrape(page, job) → dict.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.base import BaseAdapter
from app.services.proxy import get_proxy_config
from app.utils.robots import is_scraping_allowed

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

_FULL_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BaseBrowserAdapter(BaseAdapter):
    """Manages the Playwright browser lifecycle for all council scraping adapters.

    Subclasses implement _run_scrape(page, job) → dict with their
    portal-specific navigation and extraction logic.
    """

    def scrape(self, job: dict) -> dict:
        if not is_scraping_allowed(self.base_url, "/"):
            logger.info("ROBOTS_DISALLOWED: %s — skipping", self.base_url)
            return self._empty_result()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed — cannot run browser adapter")
            return self._empty_result()

        proxy_config = get_proxy_config()
        launch_kwargs: dict = {"headless": True}
        if proxy_config:
            launch_kwargs["proxy"] = {
                "server": proxy_config["url"],
                "username": proxy_config.get("username", ""),
                "password": proxy_config.get("password", ""),
            }

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(
                    user_agent=_FULL_CHROME_UA,
                    viewport={"width": 1280, "height": 800},
                    accept_downloads=True,
                )
                page = context.new_page()
                try:
                    return self._run_scrape(page, job)
                except Exception as exc:
                    self._save_failure_screenshot(page, job)
                    logger.warning(
                        "Browser adapter error for %s (%s): %s",
                        job.get("lga_name"),
                        self.base_url,
                        exc,
                        exc_info=True,
                    )
                    return {**self._empty_result(), "_adapter_error": str(exc)}
                finally:
                    context.close()
            finally:
                browser.close()

    def _run_scrape(self, page: "Page", job: dict) -> dict:
        """Override in subclasses to implement portal-specific scraping."""
        raise NotImplementedError

    def _extract_pdf(
        self, url: str, property_id: str, page: "Page"
    ) -> str | None:
        """Download PDF via browser session (preserving auth cookies),
        cache to MinIO, and extract text with pdfminer.six."""
        try:
            from app.services.minio_client import store_raw_pdf
            from app.utils.pdf_extract import extract_text_from_pdf_bytes

            pdf_bytes: bytes = page.context.request.get(url).body()
            if not pdf_bytes:
                logger.warning("Empty PDF response from %s", url)
                return None

            store_raw_pdf(property_id, pdf_bytes)
            return extract_text_from_pdf_bytes(pdf_bytes)
        except Exception:
            logger.exception("PDF extraction failed for %s", url)
            return None

    def _save_failure_screenshot(self, page: "Page", job: dict) -> None:
        """Capture a full-page PNG to MinIO on scrape failure for debugging."""
        try:
            from app.services.minio_client import store_debug_screenshot

            screenshot = page.screenshot(full_page=True)
            store_debug_screenshot(job.get("property_id", "unknown"), screenshot)
        except Exception:
            logger.debug("Could not save failure screenshot", exc_info=True)

    @staticmethod
    def _empty_result() -> dict:
        return {
            "council_planning_applications_text": None,
            "council_meeting_minutes_text": None,
        }
