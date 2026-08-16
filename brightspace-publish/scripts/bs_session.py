#!/usr/bin/env python3
"""Brightspace session helper: mint an API token from saved browser cookies.

Usage:
  python3 bs_session.py whoami            # mint token, print logged-in user
  python3 bs_session.py courses           # list enrolled courses with ou ids
  python3 bs_session.py token             # print a bearer token (for curl)

Auth pattern (see references/api-notes.md): load cookies saved by the
playwright-skill login (~/.config/brightspace-skill/storage_state.json),
GET an XSRF token, POST it back to mint a ~1h JWT bearer.

Env:
  BRIGHTSPACE_HOST   tenant host (default brightspace.vanderbilt.edu)
  BRIGHTSPACE_STATE  path to storage_state.json (default ~/.config/...)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_requests = None


def get_requests():
    """Lazy import so callers (e.g. publish.py dry-run) work without it."""
    global _requests
    if _requests is not None:
        return _requests
    try:
        import requests
    except ImportError:
        # PEP 668 (externally-managed Homebrew Python) blocks plain pip
        for extra in ([], ["--user"], ["--user", "--break-system-packages"],
                      ["--break-system-packages"]):
            r = subprocess.run([sys.executable, "-m", "pip", "install",
                                "--quiet", *extra, "requests"],
                               capture_output=True)
            if r.returncode == 0:
                break
        else:
            die("could not install the 'requests' package (pip is blocked "
                "by PEP 668). Install it manually, e.g.: python3 -m pip "
                "install --user --break-system-packages requests")
        import requests
    _requests = requests
    return _requests

HOST = os.environ.get("BRIGHTSPACE_HOST", "brightspace.vanderbilt.edu")
BASE = f"https://{HOST}"
STATE = Path(os.environ.get(
    "BRIGHTSPACE_STATE",
    Path.home() / ".config/brightspace-skill/storage_state.json"))
LOGIN_HINT = ("No Brightspace session. Get a token (paste one or let\n"
              "  Claude-in-Chrome mint it) per brightspace-course/references/\n"
              "  install-and-auth.md, or run the optional Playwright login:\n"
              "  python3 tools/login.py")

LP = "1.57"
LE = "1.93"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_cookies():
    requests = get_requests()
    if not STATE.exists():
        die(f"no saved session at {STATE}\n{LOGIN_HINT}")
    state = json.loads(STATE.read_text())
    jar = requests.cookies.RequestsCookieJar()
    n = 0
    for c in state.get("cookies", []):
        if HOST.split(".", 1)[-1] in c.get("domain", ""):
            jar.set(c["name"], c["value"], domain=c["domain"],
                    path=c.get("path", "/"))
            n += 1
    if n == 0:
        die(f"no cookies for {HOST} in {STATE}\n{LOGIN_HINT}")
    return jar


def mint_token(session=None):
    """Return (requests.Session with Bearer set). ~1h validity."""
    requests = get_requests()
    s = session or requests.Session()
    s.cookies = load_cookies()
    r = s.get(f"{BASE}/d2l/lp/auth/xsrf-tokens", timeout=30)
    if r.status_code != 200:
        die(f"xsrf-tokens returned {r.status_code}\n{LOGIN_HINT}")
    xsrf = r.json().get("referrerToken", "")
    if not xsrf:
        # documented trap: 200 + empty token == expired session cookies
        die(f"session cookies are expired (empty referrerToken).\n{LOGIN_HINT}")
    r = s.post(f"{BASE}/d2l/lp/auth/oauth2/token",
               headers={"X-Csrf-Token": xsrf},
               data={"scope": "*:*:*"}, timeout=30)
    if r.status_code != 200 or "access_token" not in r.json():
        die(f"token mint failed: {r.status_code} {r.text[:300]}\n{LOGIN_HINT}")
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def whoami(s):
    r = s.get(f"{BASE}/d2l/api/lp/{LP}/users/whoami", timeout=30)
    if r.status_code != 200:
        die(f"whoami failed: {r.status_code} {r.text[:300]}")
    return r.json()


def courses(s):
    out, bookmark = [], None
    while True:
        url = (f"{BASE}/d2l/api/lp/{LP}/enrollments/myenrollments/"
               f"?orgUnitTypeId=3")
        if bookmark:
            url += f"&bookmark={bookmark}"
        r = s.get(url, timeout=30)
        if r.status_code != 200:
            die(f"enrollments failed: {r.status_code} {r.text[:300]}")
        data = r.json()
        for item in data.get("Items", []):
            ou_info = item.get("OrgUnit", {})
            out.append({"ou": ou_info.get("Id"), "name": ou_info.get("Name"),
                        "code": ou_info.get("Code")})
        if not data.get("PagingInfo", {}).get("HasMoreItems"):
            break
        bookmark = data["PagingInfo"]["Bookmark"]
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami"
    s = mint_token()
    if cmd == "whoami":
        me = whoami(s)
        print(f"OK: authenticated to {HOST} as "
              f"{me.get('FirstName')} {me.get('LastName')} "
              f"(UserId {me.get('Identifier')})")
    elif cmd == "courses":
        for c in courses(s):
            print(f"  ou={c['ou']:<10} {c['name']}  [{c['code']}]")
    elif cmd == "token":
        print(s.headers["Authorization"].split(" ", 1)[1])
    else:
        die(f"unknown command {cmd} (use whoami | courses | token)")


if __name__ == "__main__":
    main()
