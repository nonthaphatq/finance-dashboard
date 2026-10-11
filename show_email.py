# -*- coding: utf-8 -*-
"""
show_email.py
Fetch the raw body of a specific Gmail message and print it.
Used to inspect email format before writing a parser.

SECURITY: This prints email content to terminal only.
Do NOT share output that contains real names or account numbers.
"""

import base64
import sys
from email import message_from_bytes
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

BASE_DIR   = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)

def show_email(msg_id: str):
    service = get_service()
    raw = service.users().messages().get(
        userId="me", id=msg_id, format="raw"
    ).execute()
    raw_bytes = base64.urlsafe_b64decode(raw["raw"])
    msg = message_from_bytes(raw_bytes)

    print("=" * 60)
    print(f"Subject : {msg.get('Subject', '')}")
    print(f"From    : {msg.get('From', '')}")
    print(f"Date    : {msg.get('Date', '')}")
    print("=" * 60)
    print("BODY:")
    print("-" * 60)

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                text = payload.decode(charset, errors="replace")
                print(f"[{ctype}]")
                print(text[:3000])   # first 3000 chars only
                print()
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        text = payload.decode(charset, errors="replace")
        print(text[:3000])

    print("=" * 60)
    print()
    print("*** Before sharing this output: ***")
    print("*** Remove real names, account numbers, phone numbers ***")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_email.py <gmail_message_id>")
        print("Example: python show_email.py 1a12482c63693a8c")
        sys.exit(1)
    show_email(sys.argv[1])

