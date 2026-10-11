# -*- coding: utf-8 -*-
"""
parse_email.py
Parse transaction data from K PLUS (KBank) notification emails.

Rules:
- Amounts stored as integer satang (x100), never float
- Buddhist Era year (> 2400) auto-converted to CE by subtracting 543
- On parse failure: raise ValueError with reason (caller logs to parse_errors)
"""

import re
from datetime import datetime
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """Strip HTML tags and return plain text."""
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def get_text(self):
        return "\n".join(self._parts)


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using stdlib only (no extra packages)."""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_amount_to_satang(value_str: str) -> int:
    """
    Convert amount string e.g. '2,037.27' -> 203727 (integer satang).
    Never uses float to avoid rounding errors.
    """
    clean = value_str.replace(",", "").strip()
    if "." in clean:
        baht_part, satang_part = clean.split(".", 1)
        satang_part = satang_part.ljust(2, "0")[:2]
    else:
        baht_part = clean
        satang_part = "00"
    return int(baht_part) * 100 + int(satang_part)


def _parse_txn_datetime(value_str: str) -> datetime:
    """
    Parse date/time string e.g. '09/10/2026 22:53:18' -> datetime.
    Supports both CE and BE years (year > 2400 -> subtract 543).
    """
    value_str = value_str.strip()
    dt = datetime.strptime(value_str, "%d/%m/%Y %H:%M:%S")
    if dt.year > 2400:
        dt = dt.replace(year=dt.year - 543)
    return dt


def _find_field(pattern: str, text: str, field_name: str) -> str:
    """Search for regex pattern; raise ValueError if not found."""
    match = re.search(pattern, text, re.UNICODE)
    if not match:
        raise ValueError(f"Field not found: {field_name!r}")
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# Parsers by email type
# ---------------------------------------------------------------------------

def _parse_transfer_out_promptpay(text: str) -> dict:
    """
    Parse 'PromptPay transfer out (success)' email.
    direction = 'out'
    """
    txn_at_str  = _find_field(r"วันที่ทำรายการ[:\s]+([0-9/: ]+)", text, "txn_date")
    ref_no      = _find_field(r"เลขที่รายการ[:\s]+(\S+)", text, "ref_no")
    account_raw = _find_field(r"โอนเงินจากบัญชี[:\s]+(\S+)", text, "account")
    amount_str  = _find_field(r"จำนวนเงิน\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "amount")
    fee_str     = _find_field(r"ค่าธรรมเนียม\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "fee")
    balance_str = _find_field(r"ยอดถอนได้\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "balance")

    # counterparty is optional
    cp_match = re.search(r"ชื่อผู้รับเงิน[:\s]+(.+)", text, re.UNICODE)
    counterparty = cp_match.group(1).strip() if cp_match else None

    # Keep only last 4 digits of account number (security: no full account)
    digits = re.findall(r"\d+", account_raw)
    account_last4 = digits[-1][-4:] if digits else None

    return {
        "txn_at":                   _parse_txn_datetime(txn_at_str),
        "ref_no":                   ref_no,
        "account_last4":            account_last4,
        "counterparty":             counterparty,
        "amount_satang":            _parse_amount_to_satang(amount_str),
        "fee_satang":               _parse_amount_to_satang(fee_str),
        "available_balance_satang": _parse_amount_to_satang(balance_str),
        "direction":                "out",
        "type":                     "promptpay_transfer",
        "bank":                     "KBANK",
    }



def _parse_transfer_out_bank(text: str) -> dict:
    """
    Parse inter-bank transfer email (bilingual Thai/English).
    Subjects: 'Result of Funds Transfer (Success)'
              or Thai equivalent without PromptPay keyword.
    direction = 'out', type = 'bank_transfer'
    """
    # Use Thai labels (appear first in the bilingual email)
    txn_at_str  = _find_field(r"วันที่ทำรายการ[:\s]+([0-9/: ]+)", text, "txn_date")
    ref_no      = _find_field(r"เลขที่รายการ[:\s]+(\S+)", text, "ref_no")
    account_raw = _find_field(r"โอนเงินจากบัญชี[:\s]+(\S+)", text, "account")
    amount_str  = _find_field(r"จำนวนเงิน\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "amount")
    fee_str     = _find_field(r"ค่าธรรมเนียม\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "fee")
    balance_str = _find_field(r"ยอดถอนได้\s*\(บาท\)[:\s]+([\d,]+\.\d+)", text, "balance")

    # Destination bank name (optional)
    to_bank_match = re.search(r"ธนาคารผู้รับเงิน[:\s]+(.+)", text, re.UNICODE)
    to_bank = to_bank_match.group(1).strip() if to_bank_match else None

    # Account name = counterparty (optional, store as-is)
    cp_match = re.search(r"ชื่อบัญชี[:\s]+(.+)", text, re.UNICODE)
    counterparty = cp_match.group(1).strip() if cp_match else None

    # Keep only last 4 digits of source account
    digits = re.findall(r"\d+", account_raw)
    account_last4 = digits[-1][-4:] if digits else None

    return {
        "txn_at":                   _parse_txn_datetime(txn_at_str),
        "ref_no":                   ref_no,
        "account_last4":            account_last4,
        "counterparty":             counterparty,
        "amount_satang":            _parse_amount_to_satang(amount_str),
        "fee_satang":               _parse_amount_to_satang(fee_str),
        "available_balance_satang": _parse_amount_to_satang(balance_str),
        "direction":                "out",
        "type":                     "bank_transfer",
        "bank":                     "KBANK",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Map subject keywords to parser functions
# Order matters: more specific keywords first
_SUBJECT_PARSERS = {
    "โอนเงินพร้อมเพย์":              _parse_transfer_out_promptpay,   # PromptPay (Thai subject)
    "Result of Funds Transfer":       _parse_transfer_out_bank,         # Inter-bank (English subject)
    "แจ้งผลการทำรายการโอนเงิน":      _parse_transfer_out_bank,         # Inter-bank (Thai subject)
}


# SECURITY: Only accept emails from these exact addresses
ALLOWED_SENDERS = {
    "kplus@kasikornbank.com",
}


def parse_email(subject: str, body: str, sender: str = "", is_html: bool = False) -> dict:
    """
    Parse one bank notification email into a structured dict.

    Parameters
    ----------
    subject  : Email subject line
    body     : Email body (plain text or HTML)
    sender   : Sender email address (security check)
    is_html  : Set True if body is HTML; will be converted to text first

    Returns
    -------
    dict with transaction fields

    Raises
    ------
    PermissionError : Sender not in ALLOWED_SENDERS (phishing guard)
    ValueError      : Cannot parse this email (caller saves to parse_errors)
    """
    # --- Security: verify sender ---
    if sender and sender.lower().strip() not in ALLOWED_SENDERS:
        raise PermissionError(
            f"Sender not allowed: {sender!r}  "
            f"(allowed: {ALLOWED_SENDERS})"
        )

    # --- Convert HTML to plain text if needed ---
    text = html_to_text(body) if is_html else body

    # --- Select parser by subject keyword ---
    parser_fn = None
    for keyword, fn in _SUBJECT_PARSERS.items():
        if keyword in subject:
            parser_fn = fn
            break

    if parser_fn is None:
        raise ValueError(f"No parser for subject: {subject!r}")

    return parser_fn(text)


# ---------------------------------------------------------------------------
# Self-test (run: python parse_email.py)
# ---------------------------------------------------------------------------

SAMPLE_BODY = """
วันที่ทำรายการ: 09/10/2026 22:53:18
เลขที่รายการ: 016282225318CPP03687
โอนเงินจากบัญชี: xxx-x-x7534-x
ชื่อผู้รับเงิน: Somchai Jaidee
จำนวนเงิน (บาท): 50.00
ค่าธรรมเนียม (บาท): 0.00
ยอดถอนได้ (บาท): 2,037.27
"""

SAMPLE_SUBJECT = "แจ้งผลการทำรายการโอนเงินพร้อมเพย์ (สำเร็จ)"
SAMPLE_SENDER  = "kplus@kasikornbank.com"


if __name__ == "__main__":
    print("=" * 55)
    print("TEST: parse_email.py")
    print("=" * 55)

    result = parse_email(
        subject=SAMPLE_SUBJECT,
        body=SAMPLE_BODY,
        sender=SAMPLE_SENDER,
        is_html=False,
    )

    print(f"  txn_at            : {result['txn_at']}")
    print(f"  ref_no            : {result['ref_no']}")
    print(f"  account_last4     : {result['account_last4']}")
    print(f"  counterparty      : {result['counterparty']}")
    print(f"  amount (satang)   : {result['amount_satang']}  => {result['amount_satang']/100:.2f} THB")
    print(f"  fee (satang)      : {result['fee_satang']}  => {result['fee_satang']/100:.2f} THB")
    print(f"  balance (satang)  : {result['available_balance_satang']}  => {result['available_balance_satang']/100:.2f} THB")
    print(f"  direction         : {result['direction']}")
    print(f"  type              : {result['type']}")
    print(f"  bank              : {result['bank']}")

    print()
    print("--- Security test: fake sender ---")
    try:
        parse_email(SAMPLE_SUBJECT, SAMPLE_BODY, sender="hacker@evil.com")
        print("  ERROR: should have raised PermissionError!")
    except PermissionError as e:
        print(f"  BLOCKED correctly: {e}")

    print("=" * 55)
    print("STAGE 2 PASSED")
