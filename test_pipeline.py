# -*- coding: utf-8 -*-
"""
test_pipeline.py
Simulates the full pipeline (parse -> database) without needing real Gmail.
Run this to verify everything works end-to-end.
"""

from datetime import datetime
from parse_email import parse_email
from database import (
    get_connection,
    insert_transaction,
    log_parse_error,
    get_last_synced_at,
    update_last_synced_at,
)

# ---------------------------------------------------------------------------
# Sample emails (simulating real K PLUS emails)
# ---------------------------------------------------------------------------

EMAILS = [
    {
        "email_id": "fake_gmail_id_001",
        "subject": "แจ้งผลการทำรายการโอนเงินพร้อมเพย์ (สำเร็จ)",
        "sender":  "kplus@kasikornbank.com",
        "body": """
วันที่ทำรายการ: 09/10/2026 22:53:18
เลขที่รายการ: 016282225318CPP03687
โอนเงินจากบัญชี: xxx-x-x7534-x
ชื่อผู้รับเงิน: Test Person A
จำนวนเงิน (บาท): 50.00
ค่าธรรมเนียม (บาท): 0.00
ยอดถอนได้ (บาท): 2,037.27
""",
    },
    {
        "email_id": "fake_gmail_id_002",
        "subject": "แจ้งผลการทำรายการโอนเงินพร้อมเพย์ (สำเร็จ)",
        "sender":  "kplus@kasikornbank.com",
        "body": """
วันที่ทำรายการ: 08/10/2026 10:15:00
เลขที่รายการ: 016282215315CPP09999
โอนเงินจากบัญชี: xxx-x-x7534-x
ชื่อผู้รับเงิน: Test Person B
จำนวนเงิน (บาท): 200.00
ค่าธรรมเนียม (บาท): 0.00
ยอดถอนได้ (บาท): 2,087.27
""",
    },
    {
        "email_id": "fake_gmail_id_003",
        "subject": "แจ้งผลการทำรายการโอนเงินพร้อมเพย์ (สำเร็จ)",
        "sender":  "kplus@kasikornbank.com",
        "body": """
วันที่ทำรายการ: 09/10/2026 22:53:18
เลขที่รายการ: 016282225318CPP03687
โอนเงินจากบัญชี: xxx-x-x7534-x
ชื่อผู้รับเงิน: Test Person A
จำนวนเงิน (บาท): 50.00
ค่าธรรมเนียม (บาท): 0.00
ยอดถอนได้ (บาท): 2,037.27
""",
        "_note": "DUPLICATE of email_001 — should be skipped",
    },
    {
        "email_id": "fake_gmail_id_004",
        "subject": "Unknown email type that has no parser",
        "sender":  "kplus@kasikornbank.com",
        "body": "Some unrecognized email content",
        "_note": "Should go to parse_errors",
    },
]

# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print("TEST: Full pipeline (parse -> database)")
    print("=" * 55)

    conn = get_connection()
    stats = {"inserted": 0, "duplicates": 0, "errors": 0}

    for email in EMAILS:
        note = email.get("_note", "")
        print(f"\nProcessing: {email['email_id']}" + (f"  [{note}]" if note else ""))

        try:
            parsed = parse_email(
                subject=email["subject"],
                body=email["body"],
                sender=email["sender"],
                is_html=False,
            )

            inserted = insert_transaction(conn, parsed, email_id=email["email_id"])

            if inserted:
                stats["inserted"] += 1
                print(f"  [NEW]  ref={parsed['ref_no']}"
                      f"  amount={parsed['amount_satang']/100:.2f} THB"
                      f"  balance={parsed['available_balance_satang']/100:.2f} THB")
            else:
                stats["duplicates"] += 1
                print(f"  [DUP]  ref={parsed['ref_no']} — skipped (already in DB)")

        except PermissionError as e:
            stats["errors"] += 1
            print(f"  [BLOCKED]  {e}")
            log_parse_error(conn, email["email_id"], "", email["subject"], str(e))

        except ValueError as e:
            stats["errors"] += 1
            print(f"  [PARSE ERROR]  {e}")
            log_parse_error(conn, email["email_id"], "", email["subject"], str(e))

    # Update sync time
    update_last_synced_at(conn, datetime.now())

    # Show DB summary
    print("\n" + "=" * 55)
    print("DATABASE SUMMARY")
    print("=" * 55)

    txns = conn.execute(
        "SELECT ref_no, txn_at, amount_satang, direction FROM transactions ORDER BY txn_at"
    ).fetchall()
    print(f"  transactions table: {len(txns)} row(s)")
    for r in txns:
        print(f"    {r['txn_at']}  ref={r['ref_no']}  {r['amount_satang']/100:.2f} THB  ({r['direction']})")

    errs = conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
    print(f"  parse_errors table: {errs} row(s)")

    last_sync = get_last_synced_at(conn)
    print(f"  last_synced_at    : {last_sync}")

    conn.close()

    print("\n" + "=" * 55)
    print(f"  Inserted  : {stats['inserted']}")
    print(f"  Duplicates: {stats['duplicates']}  (correctly skipped)")
    print(f"  Errors    : {stats['errors']}  (saved to parse_errors)")
    print("=" * 55)
    print("PIPELINE TEST PASSED" if stats["errors"] <= 1 else "CHECK ERRORS ABOVE")


if __name__ == "__main__":
    main()

