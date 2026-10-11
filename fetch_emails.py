# -*- coding: utf-8 -*-
"""
fetch_emails.py
Fetch KBank K PLUS transaction emails from Gmail and save to Supabase / SQLite.

Usage:
    python fetch_emails.py

Runs locally or in GitHub Actions.
Security notes:
- Uses gmail.readonly scope ONLY
- Does not print monetary amounts, recipient names, or email bodies to logs
- Filters by exact sender address to block phishing emails
- credentials and tokens loaded from environment or local files
"""

import base64
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from email import message_from_bytes
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from parse_email import parse_email, ALLOWED_SENDERS, html_to_text
from database import (
    get_connection,
    insert_transaction,
    log_parse_error,
    get_last_synced_at,
    update_last_synced_at,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR         = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE       = BASE_DIR / "token.json"

# Support loading credentials from GitHub Secrets (environment variables)
if os.getenv("GOOGLE_CREDENTIALS_JSON") and not CREDENTIALS_FILE.exists():
    CREDENTIALS_FILE.write_text(os.getenv("GOOGLE_CREDENTIALS_JSON"), encoding="utf-8")

if os.getenv("GOOGLE_TOKEN_JSON") and not TOKEN_FILE.exists():
    TOKEN_FILE.write_text(os.getenv("GOOGLE_TOKEN_JSON"), encoding="utf-8")

# gmail.readonly = read-only, cannot modify or send anything
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# How many days back to fetch on very first run (no sync state)
INITIAL_LOOKBACK_DAYS = 90

# Sender email addresses to fetch (must match ALLOWED_SENDERS in parse_email.py)
TARGET_SENDERS = list(ALLOWED_SENDERS)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_gmail_service():
    """
    Authenticate with Gmail API using OAuth2.
    - First run: opens browser for login, saves token.json
    - Subsequent runs: loads token.json, refreshes automatically if expired
    """
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("Please configure credentials.json or GOOGLE_CREDENTIALS_JSON secret.")
        sys.exit(1)

    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or re-authenticate if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing automatically...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed ({e}), re-authenticating...")
                creds = None

        if not creds or not creds.valid:
            # In headless/CI environment, we cannot launch a local browser
            if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
                print("ERROR: Cannot perform interactive login in CI/GitHub Actions.")
                print("Please update the GOOGLE_TOKEN_JSON secret with a valid token.")
                sys.exit(1)

            print("Opening browser for Google login...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print("Token refreshed and saved.")

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Email fetching
# ---------------------------------------------------------------------------

def _make_query(since_dt: datetime | None) -> str:
    """
    Build Gmail search query.
    Filters by exact sender address and date range.
    """
    sender_query = " OR ".join(f"from:{s}" for s in TARGET_SENDERS)
    if since_dt:
        ts = int(since_dt.timestamp())
        date_filter = f"after:{ts}"
    else:
        days_ago = datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)
        ts = int(days_ago.timestamp())
        date_filter = f"after:{ts}"

    return f"({sender_query}) {date_filter}"


def _get_message_ids(service, query: str) -> list[str]:
    """Return all Gmail message IDs matching the query."""
    ids = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])
        ids.extend(m["id"] for m in messages)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return ids


def _decode_payload(part) -> tuple[str, bool]:
    mime_type = part.get_content_type()
    payload = part.get_payload(decode=True)
    if payload is None:
        return "", False

    charset = part.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    return text, (mime_type == "text/html")


def _extract_body(raw_bytes: bytes) -> tuple[str, bool]:
    msg = message_from_bytes(raw_bytes)
    plain_text = None
    html_text  = None

    if msg.is_multipart():
        for part in msg.walk():
            mime = part.get_content_type()
            if mime == "text/plain" and plain_text is None:
                plain_text, _ = _decode_payload(part)
            elif mime == "text/html" and html_text is None:
                html_text, _ = _decode_payload(part)
    else:
        body, is_html = _decode_payload(msg)
        if is_html:
            html_text = body
        else:
            plain_text = body

    if plain_text:
        return plain_text, False
    if html_text:
        return html_text, True
    return "", False


def fetch_and_process(service, conn) -> dict:
    """
    Main fetch loop:
    1. Query Gmail for matching emails since last sync
    2. For each email: parse -> insert into DB or log error
    3. Update sync_state
    Returns stats dict.
    """
    last_sync = get_last_synced_at(conn)
    query = _make_query(last_sync)
    print(f"\nGmail query: {query}")

    message_ids = _get_message_ids(service, query)
    print(f"Found {len(message_ids)} email(s) to process\n")

    stats = {"processed": 0, "inserted": 0, "duplicates": 0, "errors": 0}

    for msg_id in message_ids:
        stats["processed"] += 1
        try:
            raw = service.users().messages().get(
                userId="me", id=msg_id, format="raw"
            ).execute()

            raw_bytes   = base64.urlsafe_b64decode(raw["raw"])
            msg_obj     = message_from_bytes(raw_bytes)
            subject     = msg_obj.get("Subject", "")
            sender      = msg_obj.get("From", "")
            received_at = msg_obj.get("Date", "")

            import re
            addr_match  = re.search(r"<(.+?)>", sender)
            sender_addr = addr_match.group(1) if addr_match else sender

            body, is_html = _extract_body(raw_bytes)

            parsed = parse_email(
                subject=subject,
                body=body,
                sender=sender_addr,
                is_html=is_html,
            )

            inserted = insert_transaction(conn, parsed, email_id=msg_id)
            if inserted:
                stats["inserted"] += 1
                # SECURITY: Do not print money amounts, counterparty names, or balances in logs
                print(f"  [NEW]  ref={parsed['ref_no']}  dir={parsed['direction']}")
            else:
                stats["duplicates"] += 1
                print(f"  [DUP]  ref={parsed['ref_no']}")

        except PermissionError as e:
            stats["errors"] += 1
            print(f"  [BLOCK] id={msg_id}: sender blocked")
            log_parse_error(conn, msg_id, received_at if 'received_at' in dir() else "",
                            subject if 'subject' in dir() else "", str(e))

        except (ValueError, KeyError, Exception) as e:
            stats["errors"] += 1
            subj = subject if 'subject' in dir() else "unknown"
            recv = received_at if 'received_at' in dir() else ""
            print(f"  [ERR]  id={msg_id}: parse error")
            log_parse_error(conn, msg_id, recv, subj, str(e))

    # Update sync timestamp
    now = datetime.now(timezone.utc)
    update_last_synced_at(conn, now)

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print("Finance Dashboard - Gmail Fetcher")
    print("=" * 55)

    service = get_gmail_service()
    print("Gmail authentication OK")

    conn = get_connection()
    print("Database connected")

    stats = fetch_and_process(service, conn)

    print("\n" + "=" * 55)
    print("DONE")
    print(f"  Processed : {stats['processed']}")
    print(f"  Inserted  : {stats['inserted']}  (new transactions)")
    print(f"  Duplicates: {stats['duplicates']}  (skipped)")
    print(f"  Errors    : {stats['errors']}")
    print("=" * 55)

    if hasattr(conn, "close"):
        conn.close()


if __name__ == "__main__":
    main()
