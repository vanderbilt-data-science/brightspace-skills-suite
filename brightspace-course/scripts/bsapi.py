#!/usr/bin/env python3
"""Brightspace auth + API client for the brightspace-course skill.

Token sources, tried in order:
  1. BRIGHTSPACE_TOKEN env var        (minted via Claude-in-Chrome — see
                                       references/chrome-auth.md)
  2. cached token file                (~/.config/brightspace-skill/
                                       token-<host>.json, written by
                                       `save-token`; expires after ~50 min)
  3. saved browser cookies            (storage_state.json from the Playwright
                                       login helper) -> mint a fresh JWT

Run directly for auth utilities:
  bsapi.py doctor          preflight: can this environment reach the
                           tenant at all, and is there usable auth?
                           Run this FIRST in any new environment.
  bsapi.py whoami          mint/load a token, print the logged-in user
  bsapi.py courses         list enrolled course offerings with ou ids
  bsapi.py token           print a bearer token (for curl)
  bsapi.py save-token      read a token from STDIN and cache it
  bsapi.py import-cookies [chrome|safari|firefox|edge|brave]
                           harvest the session cookies straight from the
                           user's own browser profile (no Playwright);
                           macOS may show a Keychain consent prompt
  bsapi.py versions        print the tenant's supported API versions

Env:
  BRIGHTSPACE_HOST   tenant host (default brightspace.vanderbilt.edu)
  BRIGHTSPACE_TOKEN  ready-made bearer token (skips cookies entirely)
  BRIGHTSPACE_STATE  path to storage_state.json (Playwright fallback)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOST = os.environ.get("BRIGHTSPACE_HOST", "brightspace.vanderbilt.edu")
BASE = f"https://{HOST}"
PRODUCTION_HOSTS = {"brightspace.vanderbilt.edu"}
CONFIG_DIR = Path.home() / ".config/brightspace-skill"
TOKEN_CACHE = CONFIG_DIR / f"token-{HOST}.json"
STATE = Path(os.environ.get("BRIGHTSPACE_STATE",
                            CONFIG_DIR / "storage_state.json"))
TOKEN_TTL = 50 * 60  # JWT lives ~1h; treat as stale after 50 min

LP = "1.57"
LE = "1.93"

LOGIN_HINT = (
    "No usable Brightspace session. Two ways to fix:\n"
    "  a) Chrome path (no Playwright): have Claude mint a token from your\n"
    "     logged-in Brightspace tab — see references/chrome-auth.md — then\n"
    "     cache it:  printf '%s' '<token>' | python3 bsapi.py save-token\n"
    "  b) Playwright path: run the interactive SSO login that saves\n"
    "     storage_state.json, then re-run this command."
)

UNREACHABLE_HINT = (
    "https://{host} is unreachable from this environment ({kind}).\n"
    "This failed at the network level, BEFORE any Brightspace login — so\n"
    "fixing tokens/cookies will not help. The tenant itself is on the\n"
    "public internet; what blocks it is the sandbox: Claude Cowork and\n"
    "claude.ai run code in a cloud VM whose outbound traffic must pass an\n"
    "egress-allowlist proxy, and the tenant is not on the allowlist.\n"
    "Fixes, best first:\n"
    "  1. Run this task in Claude Code — the terminal, or Claude Code\n"
    "     inside the Claude Desktop app. It executes on the user's own\n"
    "     machine with normal network access (verified working surface).\n"
    "  2. Org-admin fix for Cowork: Admin Console -> Organization\n"
    "     Settings -> Capabilities -> Code Execution -> Allow Network\n"
    "     Egress: add {host} to 'Additional allowed domains' AND set the\n"
    "     mode to 'All domains' (a known bug ignores the extra domains in\n"
    "     'Package managers only' mode). Applies to NEW sessions only.\n"
    "Do not retry in this session — the proxy will keep refusing.\n"
    "Confirm the diagnosis any time with: python3 bsapi.py doctor"
)

_requests = None


def pip_install(package):
    """Install a package, working around PEP 668 (Homebrew Python)."""
    for extra in ([], ["--user"], ["--user", "--break-system-packages"],
                  ["--break-system-packages"]):
        r = subprocess.run([sys.executable, "-m", "pip", "install",
                            "--quiet", *extra, package],
                           capture_output=True)
        if r.returncode == 0:
            return True
    return False


def get_requests():
    """Lazy import; auto-install around PEP 668 if missing."""
    global _requests
    if _requests is not None:
        return _requests
    try:
        import requests
    except ImportError:
        if not pip_install("requests"):
            die("could not install 'requests' (PEP 668). Install manually: "
                "python3 -m pip install --user --break-system-packages "
                "requests")
        import requests
    _requests = requests
    return _requests


def die(msg, code=1):
    sys.stdout.flush()
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def classify_net_error(e):
    """Name the network-level failure mode, or None if e isn't one."""
    requests = get_requests()
    if isinstance(e, requests.exceptions.SSLError):
        return "TLS failure — likely an intercepting proxy in the sandbox"
    if isinstance(e, requests.exceptions.ProxyError):
        return "the sandbox's proxy refused the connection"
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return "connection timed out — egress to this host is filtered"
    if isinstance(e, requests.exceptions.ReadTimeout):
        return "connected but the response timed out"
    if isinstance(e, requests.exceptions.ConnectionError):
        s = str(e)
        if ("Name or service not known" in s or "NameResolutionError" in s
                or "nodename nor servname" in s or "getaddrinfo" in s):
            return "DNS lookup blocked or failed"
        return "connection refused/reset"
    if isinstance(e, requests.exceptions.RequestException):
        return f"request failed ({type(e).__name__})"
    return None


def net_die(e):
    """Exit with the sandbox-egress explanation for a network failure."""
    kind = classify_net_error(e) or str(e)
    die(UNREACHABLE_HINT.format(host=HOST, kind=kind), code=2)


# ------------------------------------------------------------ token sources

def _token_from_env():
    return os.environ.get("BRIGHTSPACE_TOKEN") or None


def _token_from_cache():
    if not TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE.read_text())
    except (ValueError, OSError):
        return None
    if time.time() - data.get("minted_at", 0) > TOKEN_TTL:
        return None
    return data.get("token") or None


def save_token(token):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(
        {"token": token, "minted_at": time.time(), "host": HOST}))
    TOKEN_CACHE.chmod(0o600)


def _cookie_jar_from_state():
    requests = get_requests()
    if not STATE.exists():
        return None
    state = json.loads(STATE.read_text())
    jar = requests.cookies.RequestsCookieJar()
    n = 0
    for c in state.get("cookies", []):
        if HOST.split(".", 1)[-1] in c.get("domain", ""):
            jar.set(c["name"], c["value"], domain=c["domain"],
                    path=c.get("path", "/"))
            n += 1
    return jar if n else None


def _mint_from_cookies():
    """Session cookies -> XSRF token -> ~1h JWT (the vu_brightspace flow)."""
    requests = get_requests()
    jar = _cookie_jar_from_state()
    if jar is None:
        return None
    s = requests.Session()
    s.cookies = jar
    try:
        r = s.get(f"{BASE}/d2l/lp/auth/xsrf-tokens", timeout=30)
    except requests.exceptions.RequestException as e:
        net_die(e)
    if r.status_code != 200:
        return None
    xsrf = r.json().get("referrerToken", "")
    if not xsrf:
        # known trap: expired cookies => HTTP 200 with EMPTY referrerToken
        return None
    r = s.post(f"{BASE}/d2l/lp/auth/oauth2/token",
               headers={"X-Csrf-Token": xsrf},
               data={"scope": "*:*:*"}, timeout=30)
    if r.status_code != 200 or "access_token" not in r.json():
        return None
    return r.json()["access_token"]


def get_token():
    token = _token_from_env() or _token_from_cache()
    if token:
        return token
    token = _mint_from_cookies()
    if token:
        save_token(token)
        return token
    die(LOGIN_HINT)


# ------------------------------------------------------------------ client

class BS:
    """Thin Valence client with write-verify-friendly helpers."""

    def __init__(self, token=None):
        requests = get_requests()
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token or get_token()}"

    def req(self, method, path, ok=(200, 201), **kw):
        requests = get_requests()
        try:
            r = self.s.request(method, f"{BASE}{path}",
                               timeout=kw.pop("timeout", 120), **kw)
        except requests.exceptions.RequestException as e:
            net_die(e)
        if ok and r.status_code not in ok:
            if r.status_code == 401:
                die(f"401 on {path} — the token expired or is invalid.\n"
                    + LOGIN_HINT)
            die(f"{method} {path} -> {r.status_code} {r.text[:400]}")
        return r

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def jget(self, path, **kw):
        return self.get(path, **kw).json()

    def post(self, path, **kw):
        return self.req("POST", path, **kw)

    def put(self, path, **kw):
        return self.req("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.req("DELETE", path, ok=(200, 204), **kw)

    def paged_items(self, path):
        """Yield Items from a Bookmark-paginated LP endpoint."""
        bookmark = None
        while True:
            sep = "&" if "?" in path else "?"
            url = path + (f"{sep}bookmark={bookmark}" if bookmark else "")
            data = self.jget(url)
            yield from data.get("Items", [])
            if not data.get("PagingInfo", {}).get("HasMoreItems"):
                return
            bookmark = data["PagingInfo"]["Bookmark"]


def rich(html):
    """RichTextInput for write bodies (never echo back GET's RichText)."""
    return {"Content": html or "", "Type": "Html"}


def whoami(bs):
    return bs.jget(f"/d2l/api/lp/{LP}/users/whoami")


def my_courses(bs):
    path = f"/d2l/api/lp/{LP}/enrollments/myenrollments/?orgUnitTypeId=3"
    for item in bs.paged_items(path):
        org = item.get("OrgUnit", {})
        yield {"ou": org.get("Id"), "name": org.get("Name"),
               "code": org.get("Code")}


def import_browser_cookies(browser="chrome"):
    """Copy the Brightspace session cookies from the user's own browser
    profile into storage_state.json — the Playwright-free durable-auth
    path. Only cookies for the tenant's domain are read or stored; values
    are never printed. On macOS the OS may show a Keychain consent prompt
    ('access Chrome Safe Storage') — that is expected; the user approves.
    """
    try:
        import browser_cookie3
    except ImportError:
        if not pip_install("browser_cookie3"):
            die("could not install 'browser_cookie3'. Install manually or "
                "use the Playwright login / Chrome token mint instead.")
        import browser_cookie3
    loader = getattr(browser_cookie3, browser, None)
    if loader is None:
        die(f"unsupported browser {browser!r} "
            "(use chrome | safari | firefox | edge | brave)")
    domain = HOST.split(".", 1)[-1]
    try:
        jar = loader(domain_name=domain)
    except Exception as e:  # keychain refused / profile locked / etc.
        die(f"could not read {browser} cookies: {e}\n"
            "If a Keychain prompt appeared, approve it and re-run. "
            "Fallbacks: the Playwright login, or the token mint in "
            "references/chrome-auth.md.")
    cookies = [{"name": c.name, "value": c.value, "domain": c.domain,
                "path": c.path or "/"} for c in jar]
    # The session-bearing cookie must be present, or the harvest is
    # useless — refuse to overwrite a possibly-good state with junk.
    names = {c["name"] for c in cookies}
    if "d2lSessionVal" not in names:
        die(f"harvested {len(cookies)} {domain} cookies from {browser} but "
            "not 'd2lSessionVal' — you are not logged in to "
            f"https://{HOST} in {browser}, or its cookies are encrypted "
            "(Chrome v127+ App-Bound Encryption blocks profile reads). "
            "Existing session left untouched. Use a browser where you're "
            "logged in to Brightspace, or the token mint in "
            "references/chrome-auth.md.")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.replace(STATE.with_suffix(".json.bak"))
    STATE.write_text(json.dumps({"cookies": cookies}))
    STATE.chmod(0o600)
    if TOKEN_CACHE.exists():
        TOKEN_CACHE.unlink()  # force a fresh mint from the new cookies
    print(f"OK: {len(cookies)} {domain} cookies imported from {browser} "
          f"-> {STATE}")


def doctor():
    """Preflight for a new environment: reachability first, then auth.

    Exit codes: 0 = reachable + authenticated, 2 = tenant unreachable
    (sandbox egress — auth fixes won't help), 3 = reachable but no
    usable auth (fix with any token path).
    """
    requests = get_requests()
    print(f"doctor: tenant https://{HOST}")
    proxies = {k: os.environ[k] for k in os.environ
               if k.lower() in ("http_proxy", "https_proxy", "all_proxy")}
    if proxies:
        print(f"  note: proxy env set ({', '.join(sorted(proxies))}) — "
              "traffic is mediated by a sandbox/corporate proxy")

    # 1. Reachability — /d2l/api/versions/ answers anonymously, so this
    #    isolates the network layer from the auth layer.
    try:
        r = requests.get(f"{BASE}/d2l/api/versions/", timeout=15)
        if r.status_code == 200 and r.json():
            print("  PASS network: tenant reachable (anonymous "
                  "/d2l/api/versions/ -> 200)")
        else:
            print(f"  WARN network: reachable but versions endpoint "
                  f"returned {r.status_code} — a proxy may be "
                  "intercepting; treat API results with suspicion")
    except requests.exceptions.RequestException as e:
        kind = classify_net_error(e) or str(e)
        print(f"  FAIL network: {kind}")
        die(UNREACHABLE_HINT.format(host=HOST, kind=kind), code=2)

    # 2. Auth material on this machine — resolve it to a working token.
    token = _token_from_env()
    src = "BRIGHTSPACE_TOKEN env var" if token else None
    if not token:
        token = _token_from_cache()
        if token:
            src = f"cached token ({TOKEN_CACHE})"
    if not token and STATE.exists():
        token = _mint_from_cookies()
        if token:
            save_token(token)
            src = f"token minted from saved cookies ({STATE})"
        else:
            print(f"  FAIL auth: saved cookies exist ({STATE}) but are "
                  "expired — could not mint a token from them")
            die("network is fine; the session is stale. Re-auth by any "
                "path below.\n" + LOGIN_HINT, code=3)
    if not token:
        print("  FAIL auth material: no env token, no fresh cache, no "
              "saved cookies")
        die("network is fine; there is just nothing to log in with.\n"
            + LOGIN_HINT, code=3)
    print(f"  PASS auth material: {src}")

    # 3. Prove the token actually works.
    me = whoami(BS(token))
    print(f"  PASS auth: {me.get('FirstName')} {me.get('LastName')} "
          f"(UserId {me.get('Identifier')})")
    print("OK: environment ready")


# -------------------------------------------------------------------- main

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami"
    if cmd == "doctor":
        doctor()
        return
    if cmd == "import-cookies":
        browser = sys.argv[2] if len(sys.argv) > 2 else "chrome"
        import_browser_cookies(browser)
        bs = BS()
        me = whoami(bs)
        print(f"OK: authenticated to {HOST} as {me.get('FirstName')} "
              f"{me.get('LastName')} — no Playwright involved")
        return
    if cmd == "save-token":
        token = sys.stdin.read().strip()
        if not token or "." not in token:
            die("save-token expects a JWT on stdin")
        save_token(token)
        bs = BS(token)
        me = whoami(bs)
        print(f"OK: token cached for {HOST} — authenticated as "
              f"{me.get('FirstName')} {me.get('LastName')}")
        return
    bs = BS()
    if cmd == "whoami":
        me = whoami(bs)
        print(f"OK: authenticated to {HOST} as {me.get('FirstName')} "
              f"{me.get('LastName')} (UserId {me.get('Identifier')})")
    elif cmd == "courses":
        for c in my_courses(bs):
            print(f"  ou={c['ou']:<10} {c['name']}  [{c['code']}]")
    elif cmd == "token":
        print(bs.s.headers["Authorization"].split(" ", 1)[1])
    elif cmd == "versions":
        print(json.dumps(bs.jget("/d2l/api/versions/"), indent=1))
    else:
        die(f"unknown command {cmd} (use doctor | whoami | courses | "
            "token | save-token | import-cookies | versions)")


if __name__ == "__main__":
    main()
