#!/usr/bin/env python3
"""One-time interactive Brightspace login (Playwright) — the headless path.

You usually DON'T need this. For interactive use, get a token by pasting
one or letting Claude-in-Chrome mint it (see
brightspace-course/references/install-and-auth.md). This helper exists
only for unattended/scheduled runs, where a saved cookie jar must refresh
itself with no human present.

It opens a Chromium window at your Brightspace host, waits while you
complete SSO + Duo, then saves the session to
~/.config/brightspace-skill/storage_state.json — which every skill script
reuses.

Setup (once):
    python3 -m venv .venv && source .venv/bin/activate
    pip install playwright && playwright install chromium

Run:
    BRIGHTSPACE_HOST=brightspace.vanderbilt.edu python3 tools/login.py
"""
import os
import sys
from pathlib import Path

HOST = os.environ.get("BRIGHTSPACE_HOST", "brightspace.vanderbilt.edu")
HOME_URL = f"https://{HOST}/d2l/home"
STATE_PATH = Path.home() / ".config/brightspace-skill/storage_state.json"
LOGIN_TIMEOUT_MS = 5 * 60 * 1000


def main() -> int:
    try:
        from playwright.sync_api import (TimeoutError as PWTimeout,
                                         sync_playwright)
    except ImportError:
        print("Playwright is not installed. This helper is optional; for "
              "interactive use, paste a token instead (see "
              "brightspace-course/references/install-and-auth.md). To use "
              "this helper:\n  pip install playwright && playwright install "
              "chromium", file=sys.stderr)
        return 1

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Opening {HOST}. Complete SSO + Duo in the window that appears.")
    print(f"Session will be saved to: {STATE_PATH}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(HOME_URL)
        try:
            page.wait_for_url("**/d2l/home**", timeout=LOGIN_TIMEOUT_MS)
        except PWTimeout:
            print("Timed out waiting for /d2l/home. If you were mid-login, "
                  "rerun; if you landed elsewhere, go to Home and rerun.",
                  file=sys.stderr)
            browser.close()
            return 1
        context.storage_state(path=str(STATE_PATH))
        print(f"Session saved to {STATE_PATH}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
