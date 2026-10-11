# -*- coding: utf-8 -*-
"""
run_fetch.py
Wrapper around fetch_emails.py for Task Scheduler.
- Writes timestamped log to logs/fetch_YYYYMMDD.log
- Uses a lock file to prevent overlapping runs
- Safe to run even if a previous run is still going
"""

import sys
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR  = Path(__file__).parent
LOG_DIR   = BASE_DIR / "logs"
LOCK_FILE = BASE_DIR / "logs" / "fetch.lock"
TZ_THAI   = ZoneInfo("Asia/Bangkok")

LOG_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
def get_log_file() -> Path:
    today = datetime.now(TZ_THAI).strftime("%Y%m%d")
    return LOG_DIR / f"fetch_{today}.log"


def log(msg: str):
    now = datetime.now(TZ_THAI).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {msg}"
    print(line, flush=True)
    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Lock file — prevent overlapping runs
# ---------------------------------------------------------------------------
def acquire_lock() -> bool:
    """
    Try to acquire run lock.
    Returns True if acquired, False if another instance is running.
    """
    if LOCK_FILE.exists():
        # Check if the PID inside the lock is still alive
        try:
            pid = int(LOCK_FILE.read_text().strip())
            # On Windows, check if process exists
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                log(f"SKIP: Another instance is running (PID {pid})")
                return False
            else:
                log(f"Stale lock found (PID {pid} not running), removing")
                LOCK_FILE.unlink()
        except Exception:
            LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log("=" * 50)
    log("fetch_emails START")

    if not acquire_lock():
        log("fetch_emails SKIPPED (overlap protection)")
        log("=" * 50)
        return

    start = time.time()
    exit_code = 0
    try:
        # Import and run fetch_emails directly (same process = same .venv)
        import fetch_emails
        fetch_emails.main()
        elapsed = time.time() - start
        log(f"fetch_emails DONE in {elapsed:.1f}s")

    except Exception as e:
        elapsed = time.time() - start
        log(f"fetch_emails ERROR after {elapsed:.1f}s: {e}")
        log(traceback.format_exc())
        exit_code = 1

    finally:
        release_lock()

    log("=" * 50)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

