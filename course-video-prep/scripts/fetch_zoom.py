#!/usr/bin/env python3
"""Fetch a Zoom cloud recording (video + transcript) so the pipeline can
run from a link instead of a manual download.

Two ways in:

  # A) Zoom API (Server-to-Server OAuth) — the reliable path.
  #    Needs env: ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
  python3 fetch_zoom.py --meeting <meetingId-or-UUID> --dest <dir>

  # B) Direct download URL(s) you already have (e.g. from the recording
  #    page) — no credentials needed.
  python3 fetch_zoom.py --url <download_url> [--url <vtt_url>] --dest <dir>

Downloads the largest MP4 and, if present, the transcript VTT, into
<dest>, and prints the local paths to drop into plan.json as
`source_video` / `source_vtt`. Credentials are read from the environment
and never printed.

Notes:
- A meeting UUID that contains '/' or '//' must be double-URL-encoded for
  the API; this script handles that for you when you pass the raw UUID.
- Passcode-protected share links (zoom.us/rec/share/...) are NOT scraped
  here — use the API path, or open the recording and copy the direct
  download URL for the --url path.
"""

import argparse
import base64
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

_requests = None


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_requests():
    global _requests
    if _requests is not None:
        return _requests
    try:
        import requests
    except ImportError:
        for extra in ([], ["--user"], ["--user", "--break-system-packages"],
                      ["--break-system-packages"]):
            if subprocess.run([sys.executable, "-m", "pip", "install",
                               "--quiet", *extra, "requests"],
                              capture_output=True).returncode == 0:
                break
        else:
            die("could not install 'requests'")
        import requests
    _requests = requests
    return _requests


def s2s_token():
    acct = os.environ.get("ZOOM_ACCOUNT_ID")
    cid = os.environ.get("ZOOM_CLIENT_ID")
    sec = os.environ.get("ZOOM_CLIENT_SECRET")
    if not (acct and cid and sec):
        die("the --meeting path needs ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID and "
            "ZOOM_CLIENT_SECRET in the environment (Server-to-Server OAuth "
            "app). Or use --url with a direct download link.")
    requests = get_requests()
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = requests.post("https://zoom.us/oauth/token",
                      params={"grant_type": "account_credentials",
                              "account_id": acct},
                      headers={"Authorization": f"Basic {basic}"}, timeout=30)
    if r.status_code != 200 or "access_token" not in r.json():
        die(f"Zoom OAuth failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def encode_meeting_id(mid):
    """Numeric meeting id -> as-is. A UUID with '/' or leading '=' must be
    double-URL-encoded per Zoom's API."""
    mid = str(mid)
    if mid.isdigit():
        return mid
    if mid.startswith("/") or "//" in mid:
        return urllib.parse.quote(urllib.parse.quote(mid, safe=""), safe="")
    return urllib.parse.quote(mid, safe="")


def download(url, dest, token=None):
    requests = get_requests()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with requests.get(url, headers=headers, stream=True, timeout=600) as r:
        if r.status_code != 200:
            die(f"download failed ({r.status_code}) for {url[:80]}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest


def fetch_via_api(meeting, dest):
    token = s2s_token()
    requests = get_requests()
    url = (f"https://api.zoom.us/v2/meetings/{encode_meeting_id(meeting)}"
           "/recordings")
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     timeout=60)
    if r.status_code != 200:
        die(f"could not list recordings: {r.status_code} {r.text[:200]}")
    files = r.json().get("recording_files", [])
    mp4s = [f for f in files if f.get("file_type") == "MP4"]
    vtts = [f for f in files if f.get("file_type") in ("TRANSCRIPT", "CC")
            or f.get("file_extension", "").upper() == "VTT"]
    if not mp4s:
        die("no MP4 recording found for that meeting")
    mp4 = max(mp4s, key=lambda f: f.get("file_size", 0))
    out = {}
    stem = f"zoom-{meeting}".replace("/", "_")[:60]
    out["video"] = download(mp4["download_url"], dest / f"{stem}.mp4", token)
    # prefer TRANSCRIPT over CC
    vtt = next((f for f in vtts if f.get("file_type") == "TRANSCRIPT"),
               vtts[0] if vtts else None)
    if vtt:
        out["vtt"] = download(vtt["download_url"],
                              dest / f"{stem}.transcript.vtt", token)
    else:
        print("  note: no transcript in this recording — enable audio "
              "transcript in Zoom, or transcribe locally (whisper).")
    return out


def fetch_via_urls(urls, dest, name):
    out = {}
    stem = name or "zoom-recording"
    for u in urls:
        low = u.split("?")[0].lower()
        if low.endswith(".vtt") or "transcript" in low:
            out["vtt"] = download(u, dest / f"{stem}.transcript.vtt")
        else:
            out["video"] = download(u, dest / f"{stem}.mp4")
    if "video" not in out:
        die("no video URL recognized (expected an .mp4 download link)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", help="Zoom meeting id or UUID (API path)")
    ap.add_argument("--url", action="append", default=[],
                    help="direct download URL(s); repeatable")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--name", default=None, help="basename for --url files")
    args = ap.parse_args()
    dest = Path(args.dest).expanduser()

    if args.meeting:
        out = fetch_via_api(args.meeting, dest)
    elif args.url:
        out = fetch_via_urls(args.url, dest, args.name)
    else:
        die("pass --meeting <id> (API) or --url <download_url>")

    print("\nFetched:")
    print(f"  source_video: {out['video']}")
    if out.get("vtt"):
        print(f"  source_vtt:   {out['vtt']}")
    print("\nDrop those paths into plan.json (source_video / source_vtt).")


if __name__ == "__main__":
    main()
