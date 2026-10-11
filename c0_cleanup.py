"""
c0_cleanup.py
C0: Remove test data, clean parse_errors from test runs, backup DB.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB   = Path("finance.db")
TZ   = ZoneInfo("Asia/Bangkok")
now  = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")

# --- 1. Backup ---
backup = Path(f"finance_backup_{now}.db")
shutil.copy2(DB, backup)
print(f"Backup created: {backup}")

# --- 2. Connect ---
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# --- 3. Show before ---
rows = conn.execute("SELECT ref_no, amount_satang, direction FROM transactions ORDER BY txn_at").fetchall()
print(f"\nBefore cleanup: {len(rows)} transaction(s)")
for r in rows:
    print(f"  {r['ref_no']}  {r['amount_satang']/100:.2f} THB  {r['direction']}")

errs_before = conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
print(f"  parse_errors: {errs_before} row(s)")

# --- 4. Delete only TEST001 (the clearly fake ref_no) ---
deleted_txn = conn.execute("DELETE FROM transactions WHERE ref_no = 'TEST001'").rowcount
conn.commit()
print(f"\nDeleted {deleted_txn} test transaction(s) (ref_no=TEST001)")

# --- 5. Clean parse_errors (all from test runs, safe to clear) ---
conn.execute("DELETE FROM parse_errors")
conn.commit()
print("Cleared parse_errors (all were from test runs)")

# --- 6. Show after ---
rows = conn.execute("SELECT ref_no, txn_at, amount_satang, direction, type FROM transactions ORDER BY txn_at").fetchall()
print(f"\nAfter cleanup: {len(rows)} transaction(s)  ← should match K PLUS app")
for r in rows:
    print(f"  {r['txn_at']}  {r['ref_no']}  {r['amount_satang']/100:.2f} THB  {r['type']}")

errs_after = conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
print(f"  parse_errors: {errs_after} row(s)")

conn.close()
print("\nC0 cleanup DONE")

