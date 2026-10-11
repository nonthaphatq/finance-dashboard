# -*- coding: utf-8 -*-
"""
test_c3_supabase.py
Verify Stage C3: Test duplicate prevention with ref_no on Supabase.

Pass criteria:
- Run insert twice with the same ref_no.
- Round 1 inserts successfully.
- Round 2 skips duplicate (returns False).
- Row count does not increase on second run.
- Clean up test mock data afterward.
"""

import sys
from datetime import datetime, timezone
from database import (
    get_connection,
    insert_transaction,
    log_parse_error,
    get_last_synced_at,
    update_last_synced_at,
)

print("=" * 60)
print("STAGE C3 TEST: Testing Supabase Duplicate Prevention")
print("=" * 60)

client = get_connection()

if not hasattr(client, "table"):
    print("ERROR: Connection is not Supabase! Check your .env file.")
    sys.exit(1)

MOCK_REF = "MOCK_TEST_C3_REF_99999"

# Clean up any leftover test data first
client.table("transactions").delete().eq("ref_no", MOCK_REF).execute()

mock_txn = {
    "ref_no": MOCK_REF,
    "txn_at": datetime.now(timezone.utc),
    "direction": "out",
    "type": "promptpay_transfer",
    "amount_satang": 5000,
    "fee_satang": 0,
    "available_balance_satang": 200000,
    "account_last4": "9999",
    "counterparty": "Test Receiver",
    "bank": "KBANK",
}

# ---------------------------------------------------------------------------
# Round 1: First Insertion
# ---------------------------------------------------------------------------
print("\n[Round 1] Inserting mock transaction...")
res1 = insert_transaction(client, mock_txn, email_id="gmail_mock_001")
rows_round1 = client.table("transactions").select("id").eq("ref_no", MOCK_REF).execute()
count1 = len(rows_round1.data)

print(f"  Result 1 : {res1} (Expected: True)")
print(f"  Rows in DB: {count1} (Expected: 1)")

if not res1 or count1 != 1:
    print("FAIL: Round 1 insert failed!")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Round 2: Duplicate Insertion (Same ref_no)
# ---------------------------------------------------------------------------
print("\n[Round 2] Inserting the EXACT SAME transaction again...")
res2 = insert_transaction(client, mock_txn, email_id="gmail_mock_001")
rows_round2 = client.table("transactions").select("id").eq("ref_no", MOCK_REF).execute()
count2 = len(rows_round2.data)

print(f"  Result 2 : {res2} (Expected: False - duplicate skipped)")
print(f"  Rows in DB: {count2} (Expected: 1 - row count did not increase)")

if res2 is not False or count2 != 1:
    print("FAIL: Duplicate was not prevented! Row count increased!")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Test Sync State & Parse Error
# ---------------------------------------------------------------------------
print("\n[Testing sync_state & parse_error]...")
now_time = datetime.now(timezone.utc)
update_last_synced_at(client, now_time)
synced = get_last_synced_at(client)
print(f"  Sync state updated & read back: {synced is not None}")

log_parse_error(client, "err_001", "2026-10-11", "Mock Subject", "Mock Reason")
err_rows = client.table("parse_errors").select("id").eq("email_id", "err_001").execute()
print(f"  Parse error logged: {len(err_rows.data) > 0}")

# ---------------------------------------------------------------------------
# Cleanup Test Data
# ---------------------------------------------------------------------------
print("\n[Cleanup] Removing mock test rows...")
client.table("transactions").delete().eq("ref_no", MOCK_REF).execute()
client.table("parse_errors").delete().eq("email_id", "err_001").execute()
print("  Test data cleaned up successfully.")

print("\n" + "=" * 60)
print("STAGE C3 VERIFICATION: DUPLICATE PREVENTION PASSED!")
print("=" * 60)
