#!/usr/bin/env python3
"""Test script to diagnose NVIDIA API timeout with real data."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.prompts.user_prompt import build_user_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.services.llm_client import llm_client
from app.config import settings

# Raw data from the timeout error
RAW_DATA = {
  "nbn": {
    "loc_id": "LOC000183023766",
    "latitude": -37.81753433,
    "postcode": None,
    "longitude": 144.9586353,
    "tech_type": "FTTP",
    "service_type": "Fixed line",
    "service_status": "available",
    "formatted_address": "COLLINS ST - 1 UNIT 5601 464 COLLINS ST MELBOURNE VIC 3000 Australia",
    "tech_change_status": None,
    "target_eligibility_quarter": None
  },
  "lga_code": "343",
  "lga_name": "MELBOURNE",
  "nbn_type": "FTTP",
  "overlays": [
    {
      "code": "HO1012",
      "detail": "The Heritage Overlay (HO) protects places of cultural heritage significance. A planning permit is required for demolition, external alterations, tree removal, and subdivision. The schedule number corresponds to a specific entry in the Victorian Heritage Register or local heritage study. Internal works to non-contributory buildings may be exempt — check the schedule.",
      "family": "heritage",
      "scheme": "HO",
      "status": "g",
      "summary": "Heritage Overlay — demolition, alterations, and subdivision require a permit.",
      "gazetted": "2013-07-25",
      "schedule": 11212,
      "severity": 7,
      "description": "HERITAGE OVERLAY (HO1012)",
      "permit_trigger": True,
      "heritage_register": True,
      "heritage_register_url": "https://www.heritage.vic.gov.au/heritage-register?search=HO1012"
    },
    {
      "code": "DDO10",
      "detail": "The Design and Development Overlay (DDO) sets specific design requirements including height limits, setbacks, wall-to-boundary controls, and design objectives. A planning permit is required for buildings and works. The schedule contains the specific controls and should be consulted before any design work.",
      "family": "development",
      "scheme": "DDO",
      "status": "g",
      "summary": "Design & Development Overlay — height, setback, and design controls apply.",
      "gazetted": "2020-12-07",
      "schedule": 2615,
      "severity": 5,
      "description": "DESIGN AND DEVELOPMENT OVERLAY - SCHEDULE 10",
      "permit_trigger": True,
      "heritage_register": False,
      "heritage_register_url": None
    },
    {
      "code": "PO1",
      "detail": "The Parking Overlay (PO) modifies standard car parking requirements, typically reducing or removing minimum parking rates in areas well-served by public transport or in activity centres. Can benefit development feasibility for higher-density projects.",
      "family": "infrastructure",
      "scheme": "PO",
      "status": "g",
      "summary": "Parking Overlay — car parking requirements are modified for this area.",
      "gazetted": "2021-12-24",
      "schedule": 6981,
      "severity": 2,
      "description": "PARKING OVERLAY - PRECINCT 1",
      "permit_trigger": False,
      "heritage_register": False,
      "heritage_register_url": None
    },
    {
      "code": "DDO1",
      "detail": "The Design and Development Overlay (DDO) sets specific design requirements including height limits, setbacks, wall-to-boundary controls, and design objectives. A planning permit is required for buildings and works. The schedule contains the specific controls and should be consulted before any design work.",
      "family": "development",
      "scheme": "DDO",
      "status": "g",
      "summary": "Design & Development Overlay — height, setback, and design controls apply.",
      "gazetted": "2021-09-30",
      "schedule": 2606,
      "severity": 5,
      "description": "DESIGN AND DEVELOPMENT OVERLAY - SCHEDULE 1",
      "permit_trigger": True,
      "heritage_register": False,
      "heritage_register_url": None
    }
  ],
  "zone_num": 6890,
  "flood_risk": "NONE",
  "zoning_code": "CCZ1",
  "data_sources": [
    {
      "url": "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/Vicmap_Planning/FeatureServer",
      "name": "Vicmap Planning FeatureServer (data.vic.gov.au)",
      "fetched_at": "2026-03-01T06:04:55.049152+00:00"
    },
    {
      "url": "https://places.nbnco.net.au/places/",
      "name": "NBN Co Places API (unofficial)",
      "fetched_at": "2026-03-01T06:04:54.498000+00:00"
    },
    {
      "url": "https://data.api.abs.gov.au/rest/data/ABS,ABS_REGIONAL_LGA2021,1.5.0/.LGA2021.24600.A.?dimensionAtObservation=AllDimensions&format=jsondata",
      "name": "ABS DataAPI — Data by Region",
      "dataflow": "ABS,ABS_REGIONAL_LGA2021,1.5.0",
      "fetched_at": "2026-03-01T06:04:56.965128+00:00"
    }
  ],
  "demographics": {
    "latest": {
      "total_businesses": 44708,
      "total_population": 189381,
      "total_business_exits": 5771,
      "net_internal_migration": -3719,
      "net_overseas_migration": 14823,
      "total_business_entries": 6529,
      "private_house_approvals": 1,
      "median_age_persons_years": 29.3,
      "total_dwelling_approvals": 1514,
      "population_growth_pct_yoy": 6.52,
      "solar_panel_installations": 163,
      "house_price_growth_pct_yoy": -5.34,
      "internal_migration_arrivals": 13466,
      "overseas_migration_arrivals": 25880,
      "population_density_per_sqkm": 5044.1,
      "business_count_growth_pct_yoy": 2.58,
      "internal_migration_departures": 17185,
      "dva_service_pension_recipients": 57,
      "attached_dwelling_transfers_count": 6451,
      "dwelling_approvals_growth_pct_yoy": -44.85,
      "established_house_transfers_count": 279,
      "attached_dwelling_median_price_aud": 570000,
      "established_house_median_price_aud": 1330000,
      "total_building_approvals_value_aud_millions": 3279
    },
    "source": "ABS Data by Region (newly cached)",
    "lga_code": "24600",
    "lga_name": "Melbourne",
    "latest_year": "2024",
    "time_series": {
      "2019": {
        "total_population": 168952,
        "registered_births": 1216,
        "total_fertility_rate": 0.74,
        "median_age_persons_years": 29.2,
        "solar_panel_installations": 134,
        "children_enrolled_preschool": 755,
        "population_density_per_sqkm": 4500,
        "standardised_death_rate_per_1000": 4.9,
        "attached_dwelling_transfers_count": 6984,
        "established_house_transfers_count": 252,
        "attached_dwelling_median_price_aud": 618000,
        "established_house_median_price_aud": 1150000
      },
      "2020": {
        "total_businesses": 40612,
        "total_population": 170589,
        "registered_births": 1213,
        "total_fertility_rate": 0.69,
        "median_age_persons_years": 29.7,
        "population_growth_pct_yoy": 0.97,
        "solar_panel_installations": 113,
        "house_price_growth_pct_yoy": 13.91,
        "children_enrolled_preschool": 793,
        "population_density_per_sqkm": 4543.6,
        "dva_service_pension_recipients": 87,
        "standardised_death_rate_per_1000": 5.1,
        "attached_dwelling_transfers_count": 5559,
        "established_house_transfers_count": 226,
        "attached_dwelling_median_price_aud": 595000,
        "established_house_median_price_aud": 1310000
      },
      "2021": {
        "total_businesses": 41627,
        "total_population": 153110,
        "registered_births": 1255,
        "total_business_exits": 5022,
        "total_fertility_rate": 0.67,
        "net_internal_migration": -917,
        "net_overseas_migration": -13579,
        "total_business_entries": 6026,
        "private_house_approvals": 12,
        "median_age_persons_years": 30.5,
        "total_dwelling_approvals": 912,
        "population_growth_pct_yoy": -10.25,
        "solar_panel_installations": 150,
        "house_price_growth_pct_yoy": 6.91,
        "children_enrolled_preschool": 767,
        "internal_migration_arrivals": 17465,
        "overseas_migration_arrivals": 3588,
        "population_density_per_sqkm": 4078,
        "business_count_growth_pct_yoy": 2.5,
        "internal_migration_departures": 18382,
        "dva_service_pension_recipients": 74,
        "standardised_death_rate_per_1000": 5.5,
        "attached_dwelling_transfers_count": 4361,
        "established_house_transfers_count": 287,
        "attached_dwelling_median_price_aud": 568000,
        "established_house_median_price_aud": 1400500,
        "total_building_approvals_value_aud_millions": 3018
      },
      "2022": {
        "total_businesses": 43451,
        "total_population": 160328,
        "registered_births": 1091,
        "total_business_exits": 5403,
        "total_fertility_rate": 0.65,
        "net_internal_migration": -39,
        "net_overseas_migration": 6498,
        "total_business_entries": 7346,
        "private_house_approvals": 10,
        "median_age_persons_years": 30.1,
        "total_dwelling_approvals": 2462,
        "population_growth_pct_yoy": 4.71,
        "solar_panel_installations": 139,
        "house_price_growth_pct_yoy": 7.46,
        "children_enrolled_preschool": 717,
        "internal_migration_arrivals": 21591,
        "overseas_migration_arrivals": 17272,
        "population_density_per_sqkm": 4270.3,
        "business_count_growth_pct_yoy": 4.38,
        "internal_migration_departures": 21630,
        "dva_service_pension_recipients": 72,
        "standardised_death_rate_per_1000": 5.2,
        "attached_dwelling_transfers_count": 5836,
        "dwelling_approvals_growth_pct_yoy": 169.96,
        "established_house_transfers_count": 416,
        "attached_dwelling_median_price_aud": 586000,
        "established_house_median_price_aud": 1505000,
        "total_building_approvals_value_aud_millions": 4319
      },
      "2023": {
        "total_businesses": 43583,
        "total_population": 177785,
        "registered_births": 937,
        "total_business_exits": 6285,
        "total_fertility_rate": 0.6,
        "net_internal_migration": -2424,
        "net_overseas_migration": 19400,
        "total_business_entries": 6214,
        "private_house_approvals": 5,
        "median_age_persons_years": 29.5,
        "total_dwelling_approvals": 2745,
        "population_growth_pct_yoy": 10.89,
        "solar_panel_installations": 170,
        "house_price_growth_pct_yoy": -6.64,
        "children_enrolled_preschool": 846,
        "internal_migration_arrivals": 15484,
        "overseas_migration_arrivals": 29086,
        "population_density_per_sqkm": 4735.2,
        "business_count_growth_pct_yoy": 0.3,
        "internal_migration_departures": 17908,
        "dva_service_pension_recipients": 60,
        "standardised_death_rate_per_1000": 5.3,
        "attached_dwelling_transfers_count": 5680,
        "dwelling_approvals_growth_pct_yoy": 11.49,
        "established_house_transfers_count": 276,
        "attached_dwelling_median_price_aud": 550000,
        "established_house_median_price_aud": 1405000,
        "total_building_approvals_value_aud_millions": 4856
      },
      "2024": {
        "total_businesses": 44708,
        "total_population": 189381,
        "total_business_exits": 5771,
        "net_internal_migration": -3719,
        "net_overseas_migration": 14823,
        "total_business_entries": 6529,
        "private_house_approvals": 1,
        "median_age_persons_years": 29.3,
        "total_dwelling_approvals": 1514,
        "population_growth_pct_yoy": 6.52,
        "solar_panel_installations": 163,
        "house_price_growth_pct_yoy": -5.34,
        "internal_migration_arrivals": 13466,
        "overseas_migration_arrivals": 25880,
        "population_density_per_sqkm": 5044.1,
        "business_count_growth_pct_yoy": 2.58,
        "internal_migration_departures": 17185,
        "dva_service_pension_recipients": 57,
        "attached_dwelling_transfers_count": 6451,
        "dwelling_approvals_growth_pct_yoy": -44.85,
        "established_house_transfers_count": 279,
        "attached_dwelling_median_price_aud": 570000,
        "established_house_median_price_aud": 1330000,
        "total_building_approvals_value_aud_millions": 3279
      }
    }
  },
  "zoning_label": "CAPITAL CITY ZONE - SCHEDULE 1",
  "bushfire_risk": "NONE",
  "gazetted_date": "2020-12-07",
  "overlay_codes": [
    "HO1012",
    "DDO10",
    "PO1",
    "DDO1"
  ],
  "zoning_scheme": "ZN",
  "zoning_status": "g",
  "overlay_groups": {
    "heritage": [
      {
        "code": "HO1012",
        "detail": "The Heritage Overlay (HO) protects places of cultural heritage significance. A planning permit is required for demolition, external alterations, tree removal, and subdivision. The schedule number corresponds to a specific entry in the Victorian Heritage Register or local heritage study. Internal works to non-contributory buildings may be exempt — check the schedule.",
        "family": "heritage",
        "scheme": "HO",
        "status": "g",
        "summary": "Heritage Overlay — demolition, alterations, and subdivision require a permit.",
        "gazetted": "2013-07-25",
        "schedule": 11212,
        "severity": 7,
        "description": "HERITAGE OVERLAY (HO1012)",
        "permit_trigger": True,
        "heritage_register": True,
        "heritage_register_url": "https://www.heritage.vic.gov.au/heritage-register?search=HO1012"
      }
    ],
    "development": [
      {
        "code": "DDO10",
        "detail": "The Design and Development Overlay (DDO) sets specific design requirements including height limits, setbacks, wall-to-boundary controls, and design objectives. A planning permit is required for buildings and works. The schedule contains the specific controls and should be consulted before any design work.",
        "family": "development",
        "scheme": "DDO",
        "status": "g",
        "summary": "Design & Development Overlay — height, setback, and design controls apply.",
        "gazetted": "2020-12-07",
        "schedule": 2615,
        "severity": 5,
        "description": "DESIGN AND DEVELOPMENT OVERLAY - SCHEDULE 10",
        "permit_trigger": True,
        "heritage_register": False,
        "heritage_register_url": None
      },
      {
        "code": "DDO1",
        "detail": "The Design and Development Overlay (DDO) sets specific design requirements including height limits, setbacks, wall-to-boundary controls, and design objectives. A planning permit is required for buildings and works. The schedule contains the specific controls and should be consulted before any design work.",
        "family": "development",
        "scheme": "DDO",
        "status": "g",
        "summary": "Design & Development Overlay — height, setback, and design controls apply.",
        "gazetted": "2021-09-30",
        "schedule": 2606,
        "severity": 5,
        "description": "DESIGN AND DEVELOPMENT OVERLAY - SCHEDULE 1",
        "permit_trigger": True,
        "heritage_register": False,
        "heritage_register_url": None
      }
    ],
    "infrastructure": [
      {
        "code": "PO1",
        "detail": "The Parking Overlay (PO) modifies standard car parking requirements, typically reducing or removing minimum parking rates in areas well-served by public transport or in activity centres. Can benefit development feasibility for higher-density projects.",
        "family": "infrastructure",
        "scheme": "PO",
        "status": "g",
        "summary": "Parking Overlay — car parking requirements are modified for this area.",
        "gazetted": "2021-12-24",
        "schedule": 6981,
        "severity": 2,
        "description": "PARKING OVERLAY - PRECINCT 1",
        "permit_trigger": False,
        "heritage_register": False,
        "heritage_register_url": None
      }
    ]
  },
  "airport_corridor": False,
  "constraint_score": 4.7,
  "heritage_overlay": True,
  "constraint_summary": [
    "This site is zoned CCZ1 (Capital City Zone - Schedule 1).",
    "Heritage Overlay — demolition, alterations, and subdivision require a permit.",
    "Design & Development Overlay — height, setback, and design controls apply.",
    "Parking Overlay — car parking requirements are modified for this area."
  ],
  "has_design_overlay": True,
  "public_acquisition": False,
  "has_vegetation_overlay": False,
  "has_environment_overlay": False,
  "requires_planning_permit": True,
  "development_contributions": False,
  "development_plan_required": False,
  "incorporated_plan_applies": False,
  "contamination_audit_required": False,
  "council_meeting_minutes_text": None,
  "council_planning_applications_text": None
}

def main():
    print("=" * 80)
    print("TIMEOUT DIAGNOSIS")
    print("=" * 80)
    
    # Build prompts
    print("\n1. Building prompts...")
    address = "Unit 5601, 464 Collins St, Melbourne VIC 3000"
    user_prompt = build_user_prompt(address, RAW_DATA)
    
    # Analyze sizes
    system_len = len(SYSTEM_PROMPT)
    user_len = len(user_prompt)
    total_len = system_len + user_len
    
    print(f"\n2. Prompt sizes:")
    print(f"   System prompt:  {system_len:,} chars ({system_len/1024:.1f} KB)")
    print(f"   User prompt:    {user_len:,} chars ({user_len/1024:.1f} KB)")
    print(f"   Total:          {total_len:,} chars ({total_len/1024:.1f} KB)")
    
    # Estimate tokens (rough: 1 token ≈ 4 chars)
    est_tokens = total_len // 4
    print(f"   Est. tokens:    ~{est_tokens:,} tokens")
    
    # Show demographics breakdown
    demo = RAW_DATA.get("demographics", {})
    years = demo.get("time_series", {})
    print(f"\n3. Demographics data:")
    print(f"   Years in time_series: {len(years)}")
    for year, data in sorted(years.items()):
        print(f"   {year}: {len(data)} fields")
    
    # Show overlay breakdown
    overlays = RAW_DATA.get("overlays", [])
    print(f"\n4. Overlays data:")
    print(f"   Total overlays: {len(overlays)}")
    for ov in overlays:
        detail_len = len(ov.get("detail", ""))
        print(f"   {ov['code']}: severity={ov['severity']}, detail={detail_len} chars")
    
    print(f"\n5. LLM Provider: OpenAI (Chat Completions)")
    print(f"   Model: {settings.OPENAI_MODEL}")
    
    # Automatically run the test (no prompt)
    print("\n" + "=" * 80)
    print("6. Sending to LLM (timeout: 180s)...")
    print("=" * 80)
    
    try:
        start = time.time()
        result = llm_client.generate_json(SYSTEM_PROMPT, user_prompt)
        elapsed = time.time() - start
        
        print(f"\n✅ SUCCESS in {elapsed:.1f}s")
        print(f"   Response length: {len(result):,} chars")
        
        # Save raw response first (in case JSON parsing fails)
        with open("debug_llm_raw_response.txt", "w") as f:
            f.write(result)
        print(f"   Saved raw: debug_llm_raw_response.txt")
        
        # Try to parse and validate
        parsed = json.loads(result)
        print(f"   Valid JSON: ✅")
        print(f"   Top-level keys: {list(parsed.keys())}")
        
        # Save response to file
        with open("debug_llm_response.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print(f"   Saved: debug_llm_response.json")
        
        # Print formatted response
        print("\n" + "=" * 80)
        print("LLM RESPONSE PREVIEW")
        print("=" * 80)
        print(json.dumps(parsed, indent=2)[:3000])  # First 3000 chars
        if len(result) > 3000:
            print(f"\n... (truncated, see debug_llm_response.json for full output)")
            
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n❌ FAILED after {elapsed:.1f}s")
        print(f"   Error: {type(e).__name__}: {e}")
        # Print the raw response if parsing failed
        if 'result' in locals():
            print(f"\n   Raw response (first 500 chars):")
            print(f"   {result[:500]}")
            print(f"\n   (see debug_llm_raw_response.txt for full response)")
    
    # Save prompts to files for inspection
    print("\n7. Saving prompts to files...")
    with open("debug_system_prompt.txt", "w") as f:
        f.write(SYSTEM_PROMPT)
    with open("debug_user_prompt.txt", "w") as f:
        f.write(user_prompt)
    print("   Saved: debug_system_prompt.txt")
    print("   Saved: debug_user_prompt.txt")
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
