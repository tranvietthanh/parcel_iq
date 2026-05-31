"""Quick demo: Real Playwright browser test (no mocks)

Run this to verify Playwright works end-to-end with real browser automation.

Prerequisites:
    uv sync --extra dev          # Install pytest
    uv run playwright install chromium  # Install browser

Run:
    uv run python tests/manual/demo_real_browser_simple.py
"""

from playwright.sync_api import sync_playwright

print("🚀 Launching Playwright browser...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Test 1: Navigate to example.com
    print("\n📄 Test 1: Navigating to example.com...")
    page.goto("https://example.com")
    title = page.title()
    h1_text = page.locator("h1").inner_text()
    print(f"   ✓ Page title: {title}")
    print(f"   ✓ H1 text: {h1_text}")
    
    # Test 2: Execute JavaScript
    print("\n🔧 Test 2: Executing JavaScript...")
    result = page.evaluate("() => { return document.body.innerText.length; }")
    print(f"   ✓ Page has {result} characters of text")
    
    # Test 3: Find elements
    print("\n🔍 Test 3: Finding elements...")
    paragraphs = page.locator("p").count()
    print(f"   ✓ Found {paragraphs} paragraphs")
    
    browser.close()

print("\n✅ All tests passed! Playwright works correctly with real browser.")
print("=" * 60)
print("You can now run adapter tests that use Playwright:")
print("   uv run pytest tests/manual/test_real_browser.py -v -m manual")
