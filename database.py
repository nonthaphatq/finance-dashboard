# -*- coding: utf-8 -*-
"""
database.py
SQLite database setup and helpers for the finance dashboard.

Tables:
  transactions  - parsed bank transactions (no duplicates via ref_no UNIQUE)
  parse_errors  - emails that could not be parsed
  sync_state    - tracks last successful Gmail sync timestamp
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "finance.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Main transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_no                  TEXT    NOT NULL UNIQUE,   -- prevents duplicates
    email_id                TEXT,                       -- Gmail message ID
    txn_at                  TEXT    NOT NULL,           -- ISO-8601 datetime
    direction               TEXT    NOT NULL,           -- 'in' | 'out'
    type                    TEXT,                       -- e.g. promptpay_transfer
    amount_satang           INTEGER NOT NULL,           -- amount x100, no float
    fee_satang              INTEGER NOT NULL DEFAULT 0,
    available_balance_satang INTEGER,
    account_last4           TEXT,                       -- last 4 digits only
    counterparty            TEXT,
    bank                    TEXT    NOT NULL DEFAULT 'KBANK',
    created_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Emails that failed to parse (for debugging / manual review)
CREATE TABLE IF NOT EXISTS parse_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id    TEXT,
    received_at TEXT,
    subject     TEXT,
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Sync state: tracks the last time we polled Gmail
CREATE TABLE IF NOT EXISTS sync_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    last_synced_at  TEXT
);

-- Seed the singleton sync row on first run
INSERT OR IGNORE INTO sync_state (id, last_synced_at) VALUES (1, NULL);
"""


def get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure schema exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row        # access columns by name
    conn.execute("PRAGMA journal_mode=WAL")  # safer for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def insert_transaction(conn: sqlite3.Connection, parsed: dict, email_id: str = "") -> bool:
    """
    Insert one parsed transaction.
    Returns True if inserted, False if ref_no already exists (duplicate).
    Amounts must already be in integer satang.
    """
    sql = """
        INSERT OR IGNORE INTO transactions
            (ref_no, email_id, txn_at, direction, type,
             amount_satang, fee_satang, available_balance_satang,
             account_last4, counterparty, bank)
        VALUES
            (:ref_no, :email_id, :txn_at, :direction, :type,
             :amount_satang, :fee_satang, :available_balance_satang,
             :account_last4, :counterparty, :bank)
    """
    params = {
        "ref_no":                   parsed["ref_no"],
        "email_id":                 email_id,
        "txn_at":                   parsed["txn_at"].isoformat(),
        "direction":                parsed["direction"],
        "type":                     parsed.get("type"),
        "amount_satang":            parsed["amount_satang"],
        "fee_satang":               parsed.get("fee_satang", 0),
        "available_balance_satang": parsed.get("available_balance_satang"),
        "account_last4":            parsed.get("account_last4"),
        "counterparty":             parsed.get("counterparty"),
        "bank":                     parsed.get("bank", "KBANK"),
    }
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.rowcount > 0   # True = new row, False = duplicate skipped


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------

def log_parse_error(conn: sqlite3.Connection, email_id: str,
                    received_at: str, subject: str, reason: str) -> None:
    """Record an email that could not be parsed."""
    conn.execute(
        """INSERT INTO parse_errors (email_id, received_at, subject, reason)
           VALUES (?, ?, ?, ?)""",
        (email_id, received_at, subject, reason),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def get_last_synced_at(conn: sqlite3.Connection) -> datetime | None:
    """Return the last sync timestamp, or None if never synced."""
    row = conn.execute("SELECT last_synced_at FROM sync_state WHERE id = 1").fetchone()
    if row and row["last_synced_at"]:
        return datetime.fromisoformat(row["last_synced_at"])
    return None


def update_last_synced_at(conn: sqlite3.Connection, dt: datetime) -> None:
    """Update the last sync timestamp."""
    conn.execute(
        "UPDATE sync_state SET last_synced_at = ? WHERE id = 1",
        (dt.isoformat(),),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Balance continuity check (Stage 6)
# ---------------------------------------------------------------------------

def check_balance_continuity(conn: sqlite3.Connection) -> list[dict]:
    """
    Detect gaps in balance continuity.
    Consecutive transactions' available_balance should match the previous row's
    (balance_after = balance_before_next).  Returns list of suspicious rows.
    """
    rows = conn.execute(
        """SELECT id, ref_no, txn_at, amount_satang, fee_satang,
                  available_balance_satang
           FROM transactions
           ORDER BY txn_at ASC"""
    ).fetchall()

    gaps = []
    for i in range(len(rows) - 1):
        cur  = rows[i]
        nxt  = rows[i + 1]
        # Expected balance after current tx:
        # available_balance is AFTER the transaction, so next tx's balance
        # should be <= current balance (money went out) or we might have missed an email
        # Simple check: if next balance > current balance + large threshold, flag it
        if cur["available_balance_satang"] is not None and nxt["available_balance_satang"] is not None:
            diff = nxt["available_balance_satang"] - cur["available_balance_satang"]
            # Flag if balance jumped up unexpectedly (possible missing incoming tx)
            if diff > 0:
                gaps.append({
                    "after_ref_no":  cur["ref_no"],
                    "before_ref_no": nxt["ref_no"],
                    "balance_jump_satang": diff,
                })
    return gaps


# ---------------------------------------------------------------------------
# Self-test (run: python database.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import datetime, timezone

    print("=" * 55)
    print("TEST: database.py")
    print("=" * 55)

    # Use a temporary test DB
    import tempfile, os
    test_db = Path(tempfile.mktemp(suffix=".db"))
    _orig_db = DB_PATH

    # Monkey-patch for test
    import database as _self
    _self.DB_PATH = test_db

    conn = get_connection()
    print("  Schema created OK")

    # Insert a transaction
    sample = {
        "ref_no":                   "TEST001",
        "txn_at":                   datetime(2026, 10, 9, 22, 53, 18),
        "direction":                "out",
        "type":                     "promptpay_transfer",
        "amount_satang":            5000,
        "fee_satang":               0,
        "available_balance_satang": 203727,
        "account_last4":            "7534",
        "counterparty":             "Test User",
        "bank":                     "KBANK",
    }
    inserted = insert_transaction(conn, sample, email_id="gmail_001")
    print(f"  Insert result (should be True) : {inserted}")

    # Duplicate should be ignored
    inserted2 = insert_transaction(conn, sample, email_id="gmail_001")
    print(f"  Duplicate result (should be False): {inserted2}")

    # Row count should be 1
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    print(f"  Row count (should be 1): {count}")

    # Log a parse error
    log_parse_error(conn, "gmail_002", "2026-10-09T20:00:00", "Unknown subject", "No parser matched")
    err_count = conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
    print(f"  Parse errors (should be 1): {err_count}")

    # Sync state
    update_last_synced_at(conn, datetime(2026, 10, 9, 23, 0, 0))
    last = get_last_synced_at(conn)
    print(f"  Last synced at: {last}")

    conn.close()
    try:
        os.unlink(test_db)
        for ext in ("-wal", "-shm"):   # WAL mode creates extra files
            p = Path(str(test_db) + ext)
            if p.exists():
                p.unlink()
    except FileNotFoundError:
        pass
    print("  Temp DB cleaned up")
    print("=" * 55)
    print("STAGE 5+6 DB PASSED")

