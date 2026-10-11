# -*- coding: utf-8 -*-
"""
migrate_real_to_supabase.py
Stage C7: Clean mock data, migrate verified real transactions from finance.db to Supabase.
"""

import sqlite3
from database import get_supabase_client, insert_transaction

client = get_supabase_client()
if not client:
    print("Error: Supabase client could not connect.")
    exit(1)

print("=" * 60)
print("STAGE C7: MIGRATING REAL DATA TO SUPABASE")
print("=" * 60)

# 1. Clean up mock data from Supabase
print("\n[1] Cleaning mock transactions from Supabase...")
client.table("transactions").delete().like("ref_no", "MOCK_%").execute()
print("    Mock data cleared.")

# 2. Read verified real transactions from local SQLite
print("\n[2] Reading real transactions from local finance.db...")
sqlite_conn = sqlite3.connect("finance.db")
sqlite_conn.row_factory = sqlite3.Row
rows = sqlite_conn.execute("SELECT * FROM transactions ORDER BY txn_at ASC").fetchall()
print(f"    Found {len(rows)} real transaction(s) in local SQLite.")

# 3. Insert each verified transaction into Supabase
print("\n[3] Migrating to Supabase...")
migrated_count = 0
for r in rows:
    data = dict(r)
    inserted = insert_transaction(client, data, email_id=data.get("email_id") or "")
    if inserted:
        migrated_count += 1
        print(f"    [MIGRATED] ref={data['ref_no']} amount={data['amount_satang']/100:.2f} THB ({data['direction']})")
    else:
        print(f"    [EXISTS]   ref={data['ref_no']}")

# 4. Check rows in Supabase
sb_rows = client.table("transactions").select("ref_no, txn_at, amount_satang, available_balance_satang, direction, type").order("txn_at", desc=False).execute()
print(f"\n[4] Total real transactions now in Supabase: {len(sb_rows.data)}")
for r in sb_rows.data:
    amt = r['amount_satang'] / 100
    bal = (r.get('available_balance_satang') or 0) / 100
    print(f"    {r['txn_at']} | {r['ref_no']} | {amt:.2f} THB | balance: {bal:.2f} THB | {r['type']}")

sqlite_conn.close()
print("\n" + "=" * 60)
print("DATA MIGRATION TO SUPABASE COMPLETE!")
print("=" * 60)
