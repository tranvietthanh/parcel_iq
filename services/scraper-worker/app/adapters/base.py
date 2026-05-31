"""Base adapter and parallel execution engine.

Every scraper adapter (national, state, council) inherits from
:class:`BaseAdapter` and implements a synchronous :meth:`scrape` method
that returns a *partial* ``ScrapedPropertyData`` dict.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from app.utils.retry import retry_with_backoff
from app.services.scraper_rate_limiter import wait_for_token

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Abstract base for all scraper adapters."""

    def __init__(self, base_url: str = "", config: dict | None = None):
        self.base_url = base_url
        self.config = config or {}

    @abstractmethod
    def scrape(self, job: dict) -> dict:
        """Return a partial ScrapedPropertyData dict to be merged.

        ``job`` contains at minimum:
        - property_id, gnaf_pid, address_string, latitude, longitude,
          lga_name, state
        """
        ...

    def fetch_json(
        self,
        url: str,
        timeout: int = 15,
        method: str = "GET",
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Synchronous HTTP request with retry. Supports GET and POST.

        Args:
            url: Target URL
            timeout: Request timeout in seconds
            method: HTTP method (GET or POST)
            json_body: JSON body for POST requests
            headers: Custom HTTP headers

        Returns:
            Parsed JSON response
        """

        def _request() -> dict:
            # Enforce global scraper rate limit before making outbound requests
            try:
                wait_for_token()
            except Exception:
                # If rate limiter fails (e.g., Redis down), proceed without blocking
                logger.exception("Scraper rate limiter failed — proceeding without throttle")

            req_headers = headers or {}
            resp = httpx.request(
                method=method,
                url=url,
                json=json_body,
                headers=req_headers,
                timeout=timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
            return resp.json()

        return retry_with_backoff(_request, retries=3, delay=2.0)
