#!/usr/bin/env python3
"""Validate an async-package directory before handoff to brightspace-video-module-publish.

Usage: python3 validate_package.py <package-dir> [--max-minutes 15]

Checks:
  - manifest.json parses and has required fields
  - every file referenced by the manifest exists
  - every video has a captions entry and the vtt is non-trivial
  - video durations are within limits (warn > max, fail > max+5)
  - quiz zips contain imsmanifest.xml + quiz.xml
  - instruments carry the load-bearing items_assessed frontmatter
  - module items alternate sensibly (a quiz never precedes its first video)

Exit code 0 = pass (warnings allowed), 1 = failures found.
"""

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

failures, warnings = [], []


def fail(msg):
    failures.append(msg)


def warn(msg):
    warnings.append(msg)


def probe_duration(path):
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        print("usage: validate_package.py <package-dir> [--max-minutes 15]")
        sys.exit(1)
    pkg = Path(sys.argv[1])
    max_s = 15 * 60
    if "--max-minutes" in sys.argv:
        max_s = float(sys.argv[sys.argv.index("--max-minutes") + 1]) * 60

    mpath = pkg / "manifest.json"
    if not mpath.exists():
        print(f"FAIL: no manifest.json in {pkg}")
        sys.exit(1)
    try:
        manifest = json.loads(mpath.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: manifest.json does not parse: {e}")
        sys.exit(1)

    for field in ("package_version", "module"):
        if field not in manifest:
            fail(f"manifest missing required field: {field}")
    items = manifest.get("module", {}).get("items", [])
    if not items:
        fail("manifest module.items is empty")
    if not manifest.get("module", {}).get("title"):
        fail("manifest module.title is missing")

    seen_video = False
    n_videos = n_quizzes = 0
    total_watch = 0.0

    for i, item in enumerate(items):
        label = f"item {i} ({item.get('title', '?')})"
        t = item.get("type")
        if t not in ("html", "video", "quiz"):
            fail(f"{label}: unknown type {t!r}")
            continue
        if not item.get("title"):
            fail(f"{label}: missing title")

        if t == "html":
            f = pkg / item.get("file", "")
            if not item.get("file") or not f.exists():
                fail(f"{label}: html file missing: {item.get('file')}")

        elif t == "video":
            seen_video = True
            n_videos += 1
            f = pkg / item.get("file", "")
            if not item.get("file") or not f.exists():
                fail(f"{label}: video file missing: {item.get('file')}")
                continue
            dur = probe_duration(f)
            if dur:
                total_watch += dur
                claimed = item.get("duration_seconds")
                if claimed and abs(dur - claimed) > 3:
                    warn(f"{label}: manifest says {claimed}s, file is {dur:.0f}s")
                if dur > max_s + 300:
                    fail(f"{label}: {dur / 60:.1f} min far exceeds the "
                         f"{max_s / 60:.0f} min cap")
                elif dur > max_s:
                    warn(f"{label}: {dur / 60:.1f} min exceeds the "
                         f"{max_s / 60:.0f} min cap")
                if dur < 120:
                    warn(f"{label}: only {dur / 60:.1f} min - merge candidate?")
            cap = item.get("captions")
            if not cap:
                warn(f"{label}: no captions (accessibility expectation for "
                     "async course video)")
            elif not (pkg / cap).exists():
                fail(f"{label}: captions file missing: {cap}")
            elif (pkg / cap).stat().st_size < 100:
                warn(f"{label}: captions file nearly empty: {cap}")

        elif t == "quiz":
            n_quizzes += 1
            if not seen_video:
                fail(f"{label}: quiz appears before any video")
            z = pkg / item.get("qti", "")
            if not item.get("qti") or not z.exists():
                fail(f"{label}: QTI zip missing: {item.get('qti')}")
            else:
                try:
                    names = zipfile.ZipFile(z).namelist()
                    for req in ("imsmanifest.xml", "quiz.xml"):
                        if req not in names:
                            fail(f"{label}: {z.name} lacks {req}")
                except zipfile.BadZipFile:
                    fail(f"{label}: {z.name} is not a valid zip")
            ak = item.get("answer_key")
            if ak and not (pkg / ak).exists():
                fail(f"{label}: answer key missing: {ak}")
            inst = item.get("instrument")
            if inst:
                ip = pkg / inst
                if not ip.exists():
                    fail(f"{label}: instrument missing: {inst}")
                elif not re.search(r"^items_assessed:\s*\[.+\]",
                                   ip.read_text(), re.M):
                    fail(f"{label}: {inst} lacks items_assessed frontmatter "
                         "(load-bearing for KST coverage)")

    if n_videos and not n_quizzes:
        warn("no quizzes in package - interspersed checks are the point of "
             "this pipeline; confirm this is intentional")

    print(f"Package: {pkg}")
    print(f"Items: {len(items)} ({n_videos} videos, {n_quizzes} quizzes)  "
          f"total watch time: {total_watch / 60:.0f} min")
    for w in warnings:
        print(f"  WARN: {w}")
    for f_ in failures:
        print(f"  FAIL: {f_}")
    if failures:
        print(f"\nRESULT: {len(failures)} failure(s), {len(warnings)} warning(s)")
        sys.exit(1)
    print(f"\nRESULT: PASS ({len(warnings)} warning(s))")


if __name__ == "__main__":
    main()
