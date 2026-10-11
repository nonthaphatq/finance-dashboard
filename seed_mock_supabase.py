# -*- coding: utf-8 -*-
"""
seed_mock_supabase.py
Insert 3 mock transactions into Supabase to test Vercel dashboard features (KPIs, Charts, Table).
"""

from datetime import datetime, timezone, timedelta
from database import get_supabase_client

client = get_supabase_client()
if not client:
    print("Error: Supabase not configured.")
    exit(1)

now = datetime.now(timezone.utc)

mock_data = [
    {
        "ref_no": "MOCK_20261011_001",
        "email_id": "mock_email_001",
        "txn_at": (now - timedelta(days=2)).isoformat(),
        "direction": "in",
        "type": "deposit_transfer",
        "amount_satang": 500000,           # 5,000.00 THB
        "fee_satang": 0,
        "available_balance_satang": 849027, # 8,490.27 THB
        "account_last4": "7534",
        "counterparty": "บริษัท สมมุติ จำกัด (เงินเดือน)",
        "bank": "KBANK",
    },
    {
        "ref_no": "MOCK_20261011_002",
        "email_id": "mock_email_002",
        "txn_at": (now - timedelta(days=1)).isoformat(),
        "direction": "out",
        "type": "promptpay_transfer",
        "amount_satang": 5000,             # 50.00 THB
        "fee_satang": 0,
        "available_balance_satang": 844027, # 8,440.27 THB
        "account_last4": "7534",
        "counterparty": "สมหมาย ค้าขาย",
        "bank": "KBANK",
    },
    {
        "ref_no": "MOCK_20261011_003",
        "email_id": "mock_email_003",
        "txn_at": now.isoformat(),
        "direction": "out",
        "type": "bank_transfer",
        "amount_satang": 100000,           # 1,000.00 THB
        "fee_satang": 0,
        "available_balance_satang": 744027, # 7,440.27 THB
        "account_last4": "7534",
        "counterparty": "นาย นนทภัทร (บัญชีตนเอง)",
        "bank": "KBANK",
    },
]

print("Seeding mock transactions to Supabase...")
for item in mock_data:
    client.table("transactions").upsert(item, on_conflict="ref_no").execute()
    print(f"  Inserted: {item['ref_no']} ({item['direction']})")

print("Done! Refresh your dashboard on Vercel to see the data.")

