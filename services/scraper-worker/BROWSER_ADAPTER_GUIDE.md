# Developer Guide: BaseBrowserAdapter Pattern

## Quick Start: Adding a New Council Adapter

If you need to add a new council adapter for Playwright-based scraping:

### 1. Create Your Adapter File

```python
# services/scraper-worker/app/adapters/council/new_council.py

from typing import TYPE_CHECKING

from app.adapters.browser_base import BaseBrowserAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class NewCouncilAdapter(BaseBrowserAdapter):
    """Scrapes planning data from NewCouncil portal."""
    
    async def _run_scrape(self, page: "Page", job: dict) -> dict:
        """
        Implement your portal-specific logic here.
        
        The base class handles:
        - robots.txt checking
        - Playwright launch/cleanup
        - Proxy configuration
        - Context/page creation
        - Exception handling
        - Failure screenshots
        
        You only implement navigation & extraction.
        """
        
        # Navigate to portal
        await page.goto(
            self.base_url,
            wait_until="domcontentloaded",
            timeout=30_000
        )
        
        # Get selector from config (not hardcoded!)
        search_selector = self.config.get("search_selector", "input[type=search]")
        
        # Always wait for element visibility before interaction
        await page.wait_for_selector(search_selector, state="visible", timeout=10_000)
        
        # Respectful crawl delay (non-blocking)
        await page.wait_for_timeout(3_000)
        
        # Fill and submit search
        await page.fill(search_selector, job["address_string"])
        
        # Wait for results
        results_selector = self.config.get("results_selector", ".results")
        await page.wait_for_selector(results_selector, timeout=15_000)
        
        # Extract data using page.evaluate() with parameters (never f-strings!)
        planning_text = await page.evaluate(
            """
            (selector) => {
                const results = Array.from(document.querySelectorAll(selector));
                return results.map(r => r.innerText).join('\\n');
            }
            """,
            results_selector  # Pass selector as parameter, don't interpolate!
        )
        
        # Extract PDFs (inherited method, handles session cookies)
        pdf_text = await self._extract_pdf(
            pdf_url=...,
            property_id=job["property_id"],
            page=page
        )
        
        return {
            "council_planning_applications_text": planning_text,
            "council_meeting_minutes_text": pdf_text,
            "data_sources": [{"name": "NewCouncil Planning Portal", "url": self.base_url}],
        }
```

### 2. Register in Configuration Database

```sql
-- Add the new adapter to data_source_configs
INSERT INTO data_source_configs (
    adapter_type,
    base_url,
    config,
    enabled,
    created_at
) VALUES (
    'NewCouncilAdapter',
    'https://planning.newcouncil.gov.au/',
    '{
        "search_selector": "input#address-search",
        "results_selector": ".application-row",
        "crawl_delay_ms": 3000
    }'::jsonb,
    true,
    NOW()
);
```

### 3. Write Tests

```python
# tests/unit/adapters/council/test_new_council.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.council.new_council import NewCouncilAdapter


@pytest.fixture
def adapter():
    return NewCouncilAdapter(
        base_url="https://planning.newcouncil.gov.au/",
        config={
            "search_selector": "input#address",
            "results_selector": ".app-list",
        }
    )


@pytest.mark.asyncio
async def test_scrape_success(adapter, mock_page):
    """Test successful scrape with planning data."""
    
    # Mock page navigation
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="Application ABC-123\nApproved")
    
    job = {
        "address_string": "123 Main St, NewCity VIC 3000",
        "property_id": "prop-456",
        "lga_name": "NewCouncil",
    }
    
    # Mock robot checking
    with patch("app.adapters.browser_base.is_scraping_allowed", return_value=True):
        with patch("app.adapters.browser_base.sync_playwright"):
            with patch.object(adapter, "_extract_pdf", return_value="PDF Text"):
                result = await adapter.scrape(job)
    
    assert "council_planning_applications_text" in result
    assert result["council_planning_applications_text"] == "Application ABC-123\nApproved"
```

### 4. Key Rules

#### ✅ DO

- ✅ Use `page.wait_for_selector(selector, state="visible")` before interaction
- ✅ Use `page.evaluate(js, param1, param2)` for JS execution with config parameters
- ✅ Use `page.wait_for_timeout(ms)` for delays (non-blocking)
- ✅ Inherit from `BaseBrowserAdapter` (not `BaseAdapter`)
- ✅ Override only `_run_scrape()` method
- ✅ Use `self.config.get("key", "default")` for all selectors/URLs
- ✅ Call `self._extract_pdf()` for PDF extraction (inherited)
- ✅ Let base class handle exceptions (propagate descriptive errors)
- ✅ Use `TYPE_CHECKING` import for `Page` type hints

#### ❌ DON'T

- ❌ Don't store `browser` or `context` - base class manages lifecycle
- ❌ Don't call `browser.close()` manually - it's in finally blocks
- ❌ Don't use `httpx.get()` for PDF downloads - use `page.context.request.get()` (preserves session)
- ❌ Don't hardcode selectors in JavaScript - pass as parameters
- ❌ Don't use `time.sleep()` - use `page.wait_for_timeout()` (non-blocking)
- ❌ Don't use `wait_until="networkidle"` - it's flaky on SPAs
- ❌ Don't try to manage Playwright manually - inherit and override `_run_scrape()` only
- ❌ Don't interpolate config into f-strings: `f"...{config_value}..."` - use parameters
- ❌ Don't ignore return value structure - must have `council_planning_applications_text` key

## Configuration Pattern

### Storing Selectors in Database

```python
# app/adapters/council/new_council.py
adapter_config = {
    "search_selector": "input#property-address",      # CSS selector for address input
    "submit_selector": "button[type=submit]",         # CSS selector for submit button
    "results_selector": ".search-results .item",      # CSS selector for results
    "pdf_link_selector": "a.pdf-download",            # CSS selector for PDF links
    "crawl_delay_ms": 3000,                           # Respectful delay between requests
}

# Later, loaded from config:
# self.config.get("search_selector")
# self.config.get("results_selector")
# etc.
```

### Using Configuration in _run_scrape()

```python
async def _run_scrape(self, page: "Page", job: dict) -> dict:
    # All selectors from config (configurable per council)
    search_selector = self.config.get("search_selector", "input[name=address]")
    submit_selector = self.config.get("submit_selector", "button")
    results_selector = self.config.get("results_selector", ".results")
    
    # Crawl delay from config
    crawl_delay = self.config.get("crawl_delay_ms", 3000)
    
    # Use them
    await page.wait_for_selector(search_selector, state="visible")
    await page.fill(search_selector, job["address_string"])
    await page.click(submit_selector)
    await page.wait_for_timeout(crawl_delay)
    await page.wait_for_selector(results_selector)
    
    # Never hardcode selectors!
```

## Method Reference

### Base Class Methods (Inherited - Use These!)

```python
# Data extraction
async def _extract_pdf(
    self, 
    url: str, 
    property_id: str, 
    page: "Page"
) -> str | None:
    """
    Extract PDF text from URL using browser session.
    Handles up to 3 PDFs, joins with separator.
    Preserves session cookies (for auth).
    Returns: Text content or None if PDF unavailable
    """

# Error handling  
async def _save_failure_screenshot(
    self,
    page: "Page",
    job: dict
) -> None:
    """
    Capture PNG screenshot on error (for debugging).
    Auto-called by base class if exception occurs.
    Saved to MinIO: scraper-failures/{timestamp}.png
    """

# Empty result
@staticmethod
def _empty_result() -> dict:
    """
    Returns normalized empty/no-data result:
    {
        "council_planning_applications_text": None,
        "council_meeting_minutes_text": None,
        "data_sources": []
    }
    """

# Lifecycle (DON'T OVERRIDE)
async def scrape(self, job: dict) -> dict:
    """
    Main entry point (inherited - don't override).
    Handles: robots.txt, Playwright, proxy, context, exceptions.
    Calls your: _run_scrape(page, job)
    Returns: Results dict or empty result on error.
    """
```

### Abstract Method (YOU IMPLEMENT)

```python
async def _run_scrape(self, page: "Page", job: dict) -> dict:
    """
    Your portal-specific logic here.
    
    Args:
        page: Playwright Page object (ready to use)
        job: Scraping job {address_string, property_id, lga_name, ...}
    
    Returns: Dict with keys:
        - council_planning_applications_text: str or None
        - council_meeting_minutes_text: str or None  
        - data_sources: List[{name, url}]
    """
    # Your implementation
    pass
```

## Common Patterns

### Pattern 1: Search + Extract

```python
async def _run_scrape(self, page: "Page", job: dict) -> dict:
    # Navigate
    await page.goto(self.base_url, wait_until="domcontentloaded")
    
    # Search
    search_sel = self.config.get("search_selector")
    await page.wait_for_selector(search_sel, state="visible")
    await page.fill(search_sel, job["address_string"])
    await page.wait_for_timeout(3_000)
    
    # Extract
    results_sel = self.config.get("results_selector")
    await page.wait_for_selector(results_sel)
    text = await page.evaluate(
        "(sel) => Array.from(document.querySelectorAll(sel)).map(e => e.innerText).join('\\n')",
        results_sel,
    )
    
    return {
        "council_planning_applications_text": text,
        "council_meeting_minutes_text": None,
        "data_sources": [{"name": ..., "url": self.base_url}],
    }
```

### Pattern 2: Multi-Step Form

```python
async def _run_scrape(self, page: "Page", job: dict) -> dict:
    await page.goto(self.base_url, wait_until="domcontentloaded")
    
    # Step 1: Select LGA
    lga_sel = self.config.get("lga_dropdown_selector")
    await page.wait_for_selector(lga_sel, state="visible")
    await page.select_option(lga_sel, label=job["lga_name"])
    await page.wait_for_timeout(2_000)
    
    # Step 2: Enter address
    addr_sel = self.config.get("address_input_selector")
    await page.wait_for_selector(addr_sel, state="visible")
    await page.fill(addr_sel, job["address_string"])
    await page.wait_for_timeout(2_000)
    
    # Step 3: Submit and extract
    submit_sel = self.config.get("submit_button_selector")
    await page.click(submit_sel)
    
    results_sel = self.config.get("results_selector")
    await page.wait_for_selector(results_sel)
    text = await page.evaluate(f"(sel) => document.querySelector(sel).innerText", results_sel)
    
    return {
        "council_planning_applications_text": text,
        "council_meeting_minutes_text": None,
        "data_sources": [{"name": ..., "url": self.base_url}],
    }
```

### Pattern 3: Extract PDF + Text

```python
async def _run_scrape(self, page: "Page", job: dict) -> dict:
    # ... navigate and search ...
    
    # Extract planning text
    text = await page.evaluate("() => document.body.innerText")
    
    # Extract PDF (inherited method)
    pdf_text = await self._extract_pdf(
        url="https://council.com/pdf/application-123.pdf",
        property_id=job["property_id"],
        page=page,  # Preserves session cookies
    )
    
    return {
        "council_planning_applications_text": text,
        "council_meeting_minutes_text": pdf_text,
        "data_sources": [{"name": ..., "url": self.base_url}],
    }
```

## Testing Your Adapter

### Unit Test Template

```python
@pytest.mark.asyncio
async def test_your_adapter_scrape(adapter, mock_page):
    # Setup mocks
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="Result text")
    
    job = {
        "address_string": "123 Main St",
        "property_id": "prop-123",
        "lga_name": "TestLGA",
    }
    
    # Mock external dependencies
    with patch("app.adapters.browser_base.is_scraping_allowed", return_value=True):
        with patch("app.adapters.browser_base.sync_playwright"):
            with patch.object(adapter, "_extract_pdf", return_value="PDF"):
                result = await adapter.scrape(job)
    
    # Verify
    assert result["council_planning_applications_text"] == "Result text"
    assert result["council_meeting_minutes_text"] == "PDF"
    mock_page.fill.assert_called_once()
```

### Manual Testing

```python
# tests/manual/test_your_council.py
import asyncio
from playwright.async_api import async_playwright
from app.adapters.council.new_council import NewCouncilAdapter

async def manual_test():
    config = {
        "search_selector": "input#address",
        "results_selector": ".results",
    }
    
    adapter = NewCouncilAdapter(
        base_url="https://planning.council.gov.au/",
        config=config,
    )
    
    result = await adapter.scrape({
        "address_string": "123 Main St",
        "property_id": "test-123",
        "lga_name": "TestCouncil",
    })
    
    print(result)

if __name__ == "__main__":
    asyncio.run(manual_test())
```

## Troubleshooting

### Issue: "Element not found"
**Root cause**: Didn't wait for element visibility
```python
# ❌ Wrong
await page.fill(selector, value)

# ✅ Right
await page.wait_for_selector(selector, state="visible")
await page.fill(selector, value)
```

### Issue: "Timeout waiting for selector"
**Root cause**: Selector doesn't exist, wrong selector, or page didn't load
```python
# Debug: Save screenshot to see what's on page
from pathlib import Path
Path("debug.png").write_bytes(await page.screenshot())

# Check config
print(self.config.get("selector"))

# Adjust timeout if page is slow
await page.wait_for_selector(selector, timeout=30_000)
```

### Issue: "Connection refused / proxy error"
**Root cause**: Proxy config issue
```python
# Verify proxy
print(self.config.get("proxy_url"))

# Check is_scraping_allowed() first
# Check robots.txt not blocking
```

### Issue: "PDF extraction returns None"
**Root cause**: URL not accessible, PDF not downloadable
```python
# Check URL is correct
# Check page.context.request.get() doesn't hit auth
# Try direct page.goto(pdf_url) to test
```

---

**Key Takeaway**: Inherit from `BaseBrowserAdapter`, implement `_run_scrape()`, use config for selectors, and let the base class handle everything else! 🚀
