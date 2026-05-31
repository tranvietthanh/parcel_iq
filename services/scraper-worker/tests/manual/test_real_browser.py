"""Real Browser Tests - Manual Execution Only

These tests actually launch Playwright browsers and make real network requests.
They are NOT run in CI/CD. Only run manually when you need to verify:
- Playwright browser automation works end-to-end
- Council adapter logic functions with real browsers
- Troubleshoot scraping issues

Prerequisites:
    playwright install chromium

Run with:
    pytest tests/manual/test_real_browser.py -v -s
    pytest tests/manual/test_real_browser.py::test_basic_playwright_works -v -s
"""

from __future__ import annotations

import pytest


@pytest.mark.manual
def test_basic_playwright_works():
    """Verify Playwright can launch browser and navigate to a page."""
    import sys
    print(f"\nPython executable: {sys.executable}")
    print(f"Python path: {sys.path[:3]}")
    print(f"Playwright in sys.modules: {'playwright' in sys.modules}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"Import error: {e}")
        # Try to find where playwright should be
        import os
        venv_path = os.path.join(os.path.dirname(sys.executable), '..', 'lib', 'python3.12', 'site-packages')
        print(f"Expected site-packages: {os.path.abspath(venv_path)}")
        if os.path.exists(venv_path):
            contents = os.listdir(venv_path)
            playwright_items = [item for item in contents if 'playwright' in item.lower()]
            print(f"Playwright-related items: {playwright_items}")
        raise
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        
        try:
            # Navigate to a simple public page
            page.goto("https://example.com", timeout=10_000)
            
            # Verify page loaded
            title = page.title()
            assert "Example" in title
            
            # Extract some text
            h1_text = page.locator("h1").inner_text()
            assert h1_text is not None
            
            print(f"\n✓ Browser launched successfully")
            print(f"✓ Page title: {title}")
            print(f"✓ H1 text: {h1_text}")
            
        finally:
            browser.close()


@pytest.mark.manual
def test_tech_one_adapter_real_browser(sample_property_job):
    """Test TechOne adapter with a real browser (no mocks).
    
    This test demonstrates the full browser automation flow:
    - Launches headless Chromium
    - Navigates to a council portal
    - Fills search form
    - Waits for results
    - Extracts text
    
    NOTE: This test is marked as EXPECTED TO FAIL because:
    - We don't have a real council portal URL configured
    - Council websites may be slow or unavailable
    - This is for manual testing/debugging only
    """
    from app.adapters.council.tech_one import TechOneCouncilAdapter
    
    # Create adapter with a test configuration
    # NOTE: This will fail unless you configure a real council portal
    adapter = TechOneCouncilAdapter(
        base_url="https://example.com",  # Replace with real council URL
        config={
            "search_input_selector": "#AddressSearch",
            "results_selector": ".application-list",
        },
    )
    
    # Prepare a test job
    test_job = {
        "address_string": "1 Collins Street, Melbourne VIC 3000",
        "lga_name": "Test Council",
    }
    
    # Execute the scrape with real browser
    result = adapter.scrape(test_job)
    
    # Verify result structure
    assert "council_planning_applications_text" in result
    assert "council_meeting_minutes_text" in result
    
    print(f"\n✓ Adapter executed successfully")
    print(f"  Planning text: {result['council_planning_applications_text'][:100] if result['council_planning_applications_text'] else 'None'}...")


@pytest.mark.manual
def test_generic_html_adapter_real_browser(sample_property_job):
    """Test GenericHtml adapter with a real browser.
    
    Similar to TechOne test but uses the generic HTML adapter.
    """
    from app.adapters.council.generic_html import GenericHtmlCouncilAdapter
    
    adapter = GenericHtmlCouncilAdapter(
        base_url="https://example.com",
        config={
            "search_input_selector": "input[type=search]",
            "results_selector": ".results",
        },
    )
    
    test_job = {
        "address_string": "1 Test Street",
        "lga_name": "Test Council",
    }
    
    result = adapter.scrape(test_job)
    
    assert "council_planning_applications_text" in result
    assert "council_meeting_minutes_text" in result
    
    print(f"\n✓ GenericHtmlAdapter executed")
    print(f"  Result: {result}")


@pytest.mark.manual
def test_robots_txt_real_check():
    """Test real robots.txt compliance checking."""
    from app.utils.robots import is_scraping_allowed
    
    # Test with a known public site
    allowed = is_scraping_allowed("https://example.com", "/")
    print(f"\n✓ robots.txt check for example.com: {'allowed' if allowed else 'disallowed'}")
    
    # Test with a path that's typically disallowed
    allowed_admin = is_scraping_allowed("https://github.com", "/admin")
    print(f"✓ robots.txt check for github.com/admin: {'allowed' if allowed_admin else 'disallowed'}")
    
    assert isinstance(allowed, bool)
    assert isinstance(allowed_admin, bool)
