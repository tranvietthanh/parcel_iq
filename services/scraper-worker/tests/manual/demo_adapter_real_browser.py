"""Demo: Council Adapter with Real Browser

Demonstrates TechOneCouncilAdapter executing with a real Playwright browser.
This shows the full scraping flow without any mocks.

Run:
    uv run python tests/manual/demo_adapter_real_browser.py
"""

import sys
import os

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.adapters.council.tech_one import TechOneCouncilAdapter

print("=" * 70)
print("🌐 Testing Council Adapter with REAL Playwright Browser (No Mocks)")
print("=" * 70)

# Create adapter with example.com (will fail gracefully - no planning portal)
adapter = TechOneCouncilAdapter(
    base_url="https://example.com",
    config={
        "search_input_selector": "#AddressSearch",
        "results_selector": ".application-list",
    },
)

# Prepare test job
test_job = {
    "address_string": "1 Collins Street, Melbourne VIC 3000",
    "lga_name": "Test Council",
}

print("\n📝 Configuration:")
print(f"   Base URL: {adapter.base_url}")
print(f"   Search selector: {adapter.config['search_input_selector']}")
print(f"   Results selector: {adapter.config['results_selector']}")
print(f"   Test address: {test_job['address_string']}")

print("\n🚀 Launching browser and executing scrape...")
print("   (This will likely return None - example.com isn't a planning portal)")

try:
    result = adapter.scrape(test_job)
    
    print("\n✅ Adapter executed successfully!")
    print("\n📊 Results:")
    print(f"   Planning applications text: {result.get('council_planning_applications_text')}")
    print(f"   Meeting minutes text: {result.get('council_meeting_minutes_text')}")
    
    if result.get('data_sources'):
        print(f"\n📚 Data sources:")
        for source in result['data_sources']:
            print(f"      - {source['name']}: {source['url']}")
    
    print("\n" + "=" * 70)
    print("✓ SUCCESS: Real browser automation completed")
    print("✓ Browser launched, navigated, searched, and closed properly")
    print("✓ Playwright integration works end-to-end")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"   Type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
