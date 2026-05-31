#!/usr/bin/env python3
"""Auto-run timeout test (non-interactive)."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.prompts.user_prompt import build_user_prompt
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.services.llm_client import llm_client
from app.config import settings

# Import raw data
from test_timeout import RAW_DATA

print("=" * 80)
print("AUTO TIMEOUT TEST (with API call)")
print("=" * 80)

address = "Unit 5601, 464 Collins St, Melbourne VIC 3000"
user_prompt = build_user_prompt(address, RAW_DATA)

system_len = len(SYSTEM_PROMPT)
user_len = len(user_prompt)
total_len = system_len + user_len

print(f"\n1. Prompt sizes:")
print(f"   Total: {total_len:,} chars ({total_len/1024:.1f} KB)")
print(f"   Est. tokens: ~{total_len//4:,}")

print(f"\n2. LLM Config:")
print("   Provider: OpenAI (Chat Completions)")
print(f"   Model: {settings.OPENAI_MODEL}")

print(f"\n3. Sending to LLM API...")
print(f"   (This may take up to 3 minutes for large models...)")

try:
    start = time.time()
    result = llm_client.generate_json(SYSTEM_PROMPT, user_prompt)
    elapsed = time.time() - start
    
    print(f"\n✅ SUCCESS in {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    print(f"   Response length: {len(result):,} chars")
    
    # Validate JSON
    parsed = json.loads(result)
    print(f"   Valid JSON: ✅")
    print(f"   Top-level keys: {', '.join(list(parsed.keys())[:5])}...")
    
    # Show overlay extraction
    if "zoning_and_planning" in parsed:
        overlays = parsed["zoning_and_planning"].get("overlays", [])
        print(f"\n4. Extracted overlays: {len(overlays)}")
        for ov in overlays[:3]:
            if isinstance(ov, dict):
                print(f"   • {ov.get('code', '?')}: severity={ov.get('severity', '?')}")
    
except Exception as e:
    elapsed = time.time() - start
    print(f"\n❌ FAILED after {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    print(f"   Error: {type(e).__name__}")
    print(f"   Message: {str(e)[:200]}")
    sys.exit(1)

print("\n" + "=" * 80)
