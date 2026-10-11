# -*- coding: utf-8 -*-
"""
database.py
Database interface supporting both Supabase (Cloud PostgreSQL) and SQLite (Local fallback).

Cloud Tables:
  transactions  - parsed bank transactions (no duplicates via ref_no UNIQUE)
  parse_errors  - emails that could not be parsed
  sync_state    - tracks last successful Gmail sync timestamp
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Supabase Configuration
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_supabase_client = None

def get_supabase_client():
    """Returns authenticated Supabase client for backend ingestion using service_role."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        return _supabase_client
    return None

def is_supabase_enabled() -> bool:
    """Returns True if Supabase environment variables are configured."""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

# ---------------------------------------------------------------------------
# Local SQLite fallback
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "finance.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_no                  TEXT    NOT NULL UNIQUE,
    email_id                TEXT,
    txn_at                  TEXT    NOT NULL,
    direction               TEXT    NOT NULL,
    type                    TEXT,
    amount_satang           INTEGER NOT NULL,
    fee_satang              INTEGER NOT NULL DEFAULT 0,
    available_balance_satang INTEGER,
    account_last4           TEXT,
    counterparty            TEXT,
    bank                    TEXT    NOT NULL DEFAULT 'KBANK',
    created_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS parse_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id    TEXT,
    received_at TEXT,
    subject     TEXT,
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS sync_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_synced_at  TEXT
);

INSERT OR IGNORE INTO sync_state (id, last_synced_at) VALUES (1, NULL);
"""

def get_connection():
    """
    Returns connection. If Supabase is configured, returns Supabase client;
    otherwise opens/returns local SQLite connection.
    """
    sb = get_supabase_client()
    if sb is not None:
        return sb
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn

# ---------------------------------------------------------------------------
# Transactions (Insert & Duplicate prevention via ref_no)
# ---------------------------------------------------------------------------

def insert_transaction(conn, parsed: dict, email_id: str = "") -> bool:
    """
    Insert one parsed transaction.
    Returns True if inserted, False if ref_no already exists (duplicate).
    Works with both Supabase client and SQLite connection.
    """
    # 1. Supabase Mode
    if hasattr(conn, "table"):
        ref_no = parsed["ref_no"]
        
        # Check if ref_no already exists in database
        existing = conn.table("transactions").select("id").eq("ref_no", ref_no).execute()
        if existing.data and len(existing.data) > 0:
            return False  # Duplicate skipped
        
        txn_at_val = parsed["txn_at"]
        if hasattr(txn_at_val, "isoformat"):
            txn_at_str = txn_at_val.isoformat()
        else:
            txn_at_str = str(txn_at_val)

        payload = {
            "ref_no":                   ref_no,
            "email_id":                 email_id,
            "txn_at":                   txn_at_str,
            "direction":                parsed["direction"],
            "type":                     parsed.get("type"),
            "amount_satang":            parsed["amount_satang"],
            "fee_satang":               parsed.get("fee_satang", 0),
            "available_balance_satang": parsed.get("available_balance_satang"),
            "account_last4":            parsed.get("account_last4"),
            "counterparty":             parsed.get("counterparty"),
            "bank":                     parsed.get("bank", "KBANK"),
        }
        
        try:
            conn.table("transactions").insert(payload).execute()
            return True
        except Exception as e:
            # Check if it was unique constraint violation race
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                return False
            raise e

    # 2. SQLite Mode
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
    txn_at_val = parsed["txn_at"]
    txn_at_str = txn_at_val.isoformat() if hasattr(txn_at_val, "isoformat") else str(txn_at_val)

    params = {
        "ref_no":                   parsed["ref_no"],
        "email_id":                 email_id,
        "txn_at":                   txn_at_str,
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
    return cursor.rowcount > 0

# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------

def log_parse_error(conn, email_id: str, received_at: str, subject: str, reason: str) -> None:
    """Record an email that could not be parsed."""
    if hasattr(conn, "table"):
        conn.table("parse_errors").insert({
            "email_id": email_id,
            "received_at": received_at,
            "subject": subject,
            "reason": reason,
        }).execute()
        return

    conn.execute(
        """INSERT INTO parse_errors (email_id, received_at, subject, reason)
           VALUES (?, ?, ?, ?)""",
        (email_id, received_at, subject, reason),
    )
    conn.commit()

# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def get_last_synced_at(conn) -> datetime | None:
    """Return the last sync timestamp, or None if never synced."""
    if hasattr(conn, "table"):
        res = conn.table("sync_state").select("last_synced_at").eq("id", 1).execute()
        if res.data and len(res.data) > 0 and res.data[0].get("last_synced_at"):
            return datetime.fromisoformat(res.data[0]["last_synced_at"])
        return None

    row = conn.execute("SELECT last_synced_at FROM sync_state WHERE id = 1").fetchone()
    if row and row["last_synced_at"]:
        return datetime.fromisoformat(row["last_synced_at"])
    return None

def update_last_synced_at(conn, dt: datetime) -> None:
    """Update the last sync timestamp."""
    iso_val = dt.isoformat()
    if hasattr(conn, "table"):
        conn.table("sync_state").upsert({"id": 1, "last_synced_at": iso_val}).execute()
        return

    conn.execute(
        "UPDATE sync_state SET last_synced_at = ? WHERE id = 1",
        (iso_val,),
    )
    conn.commit()
