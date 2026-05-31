#!/usr/bin/env python3
"""Quick test script to run VicPlan and ABS Census adapters directly.

Usage:
    cd services/scraper-worker
    uv run python test_adapters.py
"""

import json
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.adapters.state.vic_plan import VicPlanAdapter
from app.adapters.national.abs_census import AbsCensusAdapter

# Property: 7 ST LAWRENCE CL WERRIBEE VIC 3030
PROPERTY = {
    "property_id": "test-property",
    "latitude": -37.881426,
    "longitude": 144.658523,
    "address": "7 ST LAWRENCE CL WERRIBEE VIC 3030",
    "mode": "FORCE_ALL",  # Force refresh, bypass cache
}


def test_vic_plan():
    """Test VicPlan adapter."""
    print("=" * 80)
    print("TESTING VicPlan Adapter")
    print("=" * 80)
    print(f"Coordinates: {PROPERTY['latitude']}, {PROPERTY['longitude']}")
    print(f"Address: {PROPERTY['address']}\n")
    
    adapter = VicPlanAdapter()
    
    try:
        result = adapter.scrape(PROPERTY)
        print("✓ Scrape completed")
        print(f"\nResult keys: {list(result.keys())}\n")
        print(json.dumps(result, indent=2, default=str))
        return result
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_abs_census():
    """Test ABS Census adapter."""
    print("\n\n")
    print("=" * 80)
    print("TESTING ABS Census Adapter")
    print("=" * 80)
    print(f"Coordinates: {PROPERTY['latitude']}, {PROPERTY['longitude']}")
    print(f"Address: {PROPERTY['address']}\n")
    
    adapter = AbsCensusAdapter()
    
    try:
        # First, resolve LGA to see what we're querying
        lga_code = adapter._resolve_lga(PROPERTY['latitude'], PROPERTY['longitude'])
        print(f"Resolved LGA Code: {lga_code}\n")
        
        if lga_code:
            # Fetch raw data
            print("Fetching raw ABS API data...")
            url = adapter._build_url(lga_code)
            print(f"URL: {url}\n")
            
            raw_data = adapter._fetch_lga_data(lga_code)
            
            # Dump structure to understand what we got
            print("Response top-level keys:", list(raw_data.keys()) if isinstance(raw_data, dict) else "NOT A DICT")
            if isinstance(raw_data, dict):
                if 'data' in raw_data:
                    print("  data keys:", list(raw_data['data'].keys()) if isinstance(raw_data['data'], dict) else "NOT A DICT")
                    if isinstance(raw_data['data'], dict):
                        if 'structures' in raw_data['data']:
                            structures = raw_data['data']['structures']
                            print(f"    structures: {type(structures)} with {len(structures) if isinstance(structures, list) else 'N/A'}  items")
                            if isinstance(structures, list) and structures:
                                print(f"      structures[0] keys: {list(structures[0].keys()) if isinstance(structures[0], dict) else 'NOT A DICT'}")
                                if isinstance(structures[0], dict) and 'dimensions' in structures[0]:
                                    print(f"        dimensions keys: {list(structures[0]['dimensions'].keys())}")
                        if 'structure' in raw_data['data']:
                            print("    structure keys:", list(raw_data['data']['structure'].keys()) if isinstance(raw_data['data']['structure'], dict) else "NOT A DICT")
                if 'structure' in raw_data:
                    print("  structure keys:", list(raw_data['structure'].keys()) if isinstance(raw_data['structure'], dict) else "NOT A DICT")
            print()
            
            # Check observations
            observations = adapter._get_observations(raw_data)
            print(f"Total observations in response: {len(observations)}")
            
            if observations:
                print("\nFirst 5 observation keys:")
                for i, (key, value) in enumerate(list(observations.items())[:5]):
                    print(f"  {key}: {value}")
                
                # Debug dimension lookups
                print("\n" + "-" * 40)
                print("Dimension Analysis")
                print("-" * 40)
                dim_positions, dim_code_lists = adapter._build_dimension_lookups(raw_data)
                
                print(f"\nDimension positions: {dim_positions}")
                print(f"\nMEASURE codes (first 10): {dim_code_lists.get('MEASURE', [])[:10]}")
                print(f"REGIONTYPE codes: {dim_code_lists.get('REGIONTYPE', [])}")
                print(f"TIME_PERIOD codes (first 10): {dim_code_lists.get('TIME_PERIOD', [])[:10]}")
                print(f"LGA_2021 codes (first 5): {dim_code_lists.get('LGA_2021', [])[:5]}")
                
                # Check if any investor measures are present
                measure_codes = dim_code_lists.get('MEASURE', [])
                from app.adapters.national.abs_census import INVESTOR_MEASURES
                found_measures = [m for m in measure_codes if m in INVESTOR_MEASURES]
                print(f"\nInvestor measures found in response: {len(found_measures)}/{len(INVESTOR_MEASURES)}")
                if found_measures:
                    print(f"Examples: {found_measures[:5]}")
                else:
                    print("⚠️  NO INVESTOR MEASURES FOUND!")
                    print(f"First 20 measure codes in response: {measure_codes[:20]}")
            else:
                print("\n⚠️  No observations found in response!")
                print("\nResponse structure:")
                print(json.dumps(raw_data, indent=2)[:2000] + "...(truncated)")
        
        print("\n" + "-" * 40)
        print("Now running full scrape()...")
        print("-" * 40 + "\n")
        
        result = adapter.scrape(PROPERTY)
        print("✓ Scrape completed")
        print(f"\nResult keys: {list(result.keys())}\n")
        
        # Print demographics structure
        if "demographics" in result and result["demographics"]:
            demo = result["demographics"]
            print(f"LGA Code: {demo.get('lga_code')}")
            print(f"LGA Name: {demo.get('lga_name')}")
            print(f"Latest Year: {demo.get('latest_year')}")
            print(f"Time Series Years: {list(demo.get('time_series', {}).keys())}")
            print(f"\nLatest data fields: {list(demo.get('latest', {}).keys())}")
            print(f"Total fields in latest: {len(demo.get('latest', {}))}")
        
        print("\n" + "=" * 40)
        print("Full JSON:")
        print("=" * 40)
        print(json.dumps(result, indent=2, default=str))
        return result
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run both adapter tests."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "ADAPTER INTEGRATION TEST" + " " * 34 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")
    
    vic_result = test_vic_plan()
    abs_result = test_abs_census()
    
    print("\n\n")
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if vic_result:
        print("✓ VicPlan adapter returned data")
        print(f"  - Zone: {vic_result.get('zoning_code')} ({vic_result.get('zoning_label')})")
        print(f"  - Overlays: {len(vic_result.get('overlay_codes', []))} found")
        print(f"  - Constraint Score: {vic_result.get('constraint_score')}")
    else:
        print("✗ VicPlan adapter failed")
    
    if abs_result and abs_result.get("demographics"):
        demo = abs_result["demographics"]
        print("✓ ABS Census adapter returned data")
        print(f"  - LGA: {demo.get('lga_name')} ({demo.get('lga_code')})")
        print(f"  - Years available: {list(demo.get('time_series', {}).keys())}")
        print(f"  - Latest metrics: {len(demo.get('latest', {}))} fields")
    else:
        print("✗ ABS Census adapter failed or returned no data")


if __name__ == "__main__":
    main()
