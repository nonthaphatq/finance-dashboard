# -*- coding: utf-8 -*-
"""
process_one.py
Fetch and process a single Gmail email by its message ID.
Useful for re-processing emails that previously failed to parse.

Usage:
    python process_one.py <gmail_message_id>

Example:
    python process_one.py 1a12482c63693a8c
"""

import base64
import sys
import re
from email import message_from_bytes
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from parse_email import parse_email, html_to_text
from database import get_connection, insert_transaction, log_parse_error

BASE_DIR   = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _extract_body(raw_bytes: bytes) -> tuple[str, bool]:
    msg = message_from_bytes(raw_bytes)
    plain_text = None
    html_text  = None
    if msg.is_multipart():
        for part in msg.walk():
            mime = part.get_content_type()
            if mime == "text/plain" and plain_text is None:
                charset = part.get_content_charset() or "utf-8"
                plain_text = part.get_payload(decode=True).decode(charset, errors="replace")
            elif mime == "text/html" and html_text is None:
                charset = part.get_content_charset() or "utf-8"
                html_text = part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        body = msg.get_payload(decode=True).decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            html_text = body
        else:
            plain_text = body
    if plain_text:
        return plain_text, False
    if html_text:
        return html_text, True
    return "", False


def process_one(msg_id: str):
    print("=" * 55)
    print(f"Processing email: {msg_id}")
    print("=" * 55)

    service = get_service()
    conn    = get_connection()

    # Fetch raw email
    raw = service.users().messages().get(
        userId="me", id=msg_id, format="raw"
    ).execute()
    raw_bytes   = base64.urlsafe_b64decode(raw["raw"])
    msg_obj     = message_from_bytes(raw_bytes)
    subject     = msg_obj.get("Subject", "")
    sender      = msg_obj.get("From", "")
    received_at = msg_obj.get("Date", "")

    # Extract sender address only (strip display name)
    addr_match  = re.search(r"<(.+?)>", sender)
    sender_addr = addr_match.group(1) if addr_match else sender

    body, is_html = _extract_body(raw_bytes)

    print(f"  Subject : {subject}")
    print(f"  From    : {sender_addr}")
    print(f"  Date    : {received_at}")
    print()

    try:
        parsed = parse_email(
            subject=subject,
            body=body,
            sender=sender_addr,
            is_html=is_html,
        )

        inserted = insert_transaction(conn, parsed, email_id=msg_id)

        if inserted:
            print("  Result  : [NEW] Inserted successfully")
            print(f"  ref_no  : {parsed['ref_no']}")
            print(f"  amount  : {parsed['amount_satang']/100:.2f} THB")
            print(f"  balance : {parsed['available_balance_satang']/100:.2f} THB")
            print(f"  type    : {parsed['type']}")
        else:
            print(f"  Result  : [DUP] ref_no={parsed['ref_no']} already in DB")

    except PermissionError as e:
        print(f"  Result  : [BLOCKED] {e}")
        log_parse_error(conn, msg_id, received_at, subject, str(e))

    except ValueError as e:
        print(f"  Result  : [PARSE ERROR] {e}")
        log_parse_error(conn, msg_id, received_at, subject, str(e))

    print("=" * 55)
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_one.py <gmail_message_id>")
        sys.exit(1)
    process_one(sys.argv[1])

