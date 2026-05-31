"""Fixtures for manual browser tests."""

from __future__ import annotations

import sys
import pytest


@pytest.fixture(scope="function", autouse=True)
def ensure_real_playwright():
    """Ensure we're using the real Playwright module, not mocks.
    
    This removes any mock modules that might be injected by integration tests.
    Runs before each test to ensure clean state.
    """
    print("\n🔧 Checking playwright module...")
    
    # Only remove if it's a mock, not the real module
    if 'playwright' in sys.modules:
        mod = sys.modules['playwright']
        # Check if it's a MagicMock
        if 'MagicMock' in str(type(mod)) or 'Mock' in str(type(mod)):
            print("   Removing mock playwright module")
            sys.modules.pop('playwright', None)
            sys.modules.pop('playwright.sync_api', None)
        else:
            print(f"   Real playwright module already loaded: {type(mod)}")
    else:
        print("   playwright not in sys.modules")
    
    yield
    
    # Keep the real module loaded for subsequent tests


@pytest.fixture
def sample_property_job():
    """Sample property scraping job for testing."""
    return {
        "job_id": "test-job-123",
        "address_string": "1 Collins Street, Melbourne VIC 3000",
        "lat": -37.8136,
        "lng": 144.9631,
        "lga_name": "Melbourne",
        "state_name": "VIC",
    }


def pytest_configure(config):
    """Register custom marker for manual tests."""
    config.addinivalue_line(
        "markers", "manual: mark test as manual (requires real browser, not run in CI)"
    )
