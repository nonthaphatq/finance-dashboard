# -*- coding: utf-8 -*-
"""
test_c2_security.py
Verify Supabase Row Level Security (RLS) for Stage C2.

Pass criteria:
1. Unauthenticated read via anon key returns empty or is denied.
2. Unauthenticated insert via anon key is strictly denied.
3. Backend service role key can connect properly.
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY or not SUPABASE_SERVICE_ROLE_KEY:
    print("=" * 60)
    print("ERROR: Missing Supabase credentials in .env file!")
    print("Please make sure C:\\finance-dashboard\\.env exists and has:")
    print("  SUPABASE_URL=...")
    print("  SUPABASE_ANON_KEY=...")
    print("  SUPABASE_SERVICE_ROLE_KEY=...")
    print("=" * 60)
    sys.exit(1)

print("=" * 60)
print("STAGE C2 SECURITY TEST: Testing Supabase RLS")
print("=" * 60)

# ---------------------------------------------------------------------------
# Test 1: Unauthenticated Read using Anon Key
# ---------------------------------------------------------------------------
print("\n[Test 1] Testing unauthenticated read (anon key)...")
anon_client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

try:
    res = anon_client.table("transactions").select("*").execute()
    # In Supabase RLS, when policy restricts to 'authenticated',
    # an unauthenticated select returns empty list (0 rows)
    if len(res.data) == 0:
        print("  -> PASS: Unauthenticated SELECT returned 0 rows (blocked by RLS)")
    else:
        print(f"  -> FAIL: Unauthenticated user saw {len(res.data)} row(s)! Check RLS policy.")
        sys.exit(1)
except Exception as e:
    print(f"  -> PASS: Unauthenticated SELECT denied by server: {e}")

# ---------------------------------------------------------------------------
# Test 2: Unauthenticated Insert using Anon Key
# ---------------------------------------------------------------------------
print("\n[Test 2] Testing unauthenticated insert (anon key)...")
fake_payload = {
    "ref_no": "HACKER_ATTEMPT_999",
    "txn_at": "2026-10-11T00:00:00Z",
    "direction": "out",
    "amount_satang": 100,
}

try:
    anon_client.table("transactions").insert(fake_payload).execute()
    print("  -> FAIL: Hacker insert succeeded! RLS insert policy is missing!")
    sys.exit(1)
except Exception as e:
    print("  -> PASS: Insert correctly REJECTED by RLS:")
    print(f"     {str(e)[:80]}...")

# ---------------------------------------------------------------------------
# Test 3: Backend Ingestion using Service Role Key
# ---------------------------------------------------------------------------
print("\n[Test 3] Testing backend ingestion (service_role key)...")
service_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

try:
    sync_res = service_client.table("sync_state").select("*").execute()
    print(f"  -> PASS: Service role connected successfully. sync_state rows: {len(sync_res.data)}")
except Exception as e:
    print(f"  -> FAIL: Service role connection failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("STAGE C2 VERIFICATION: ALL SECURITY CHECKS PASSED!")
print("=" * 60)

