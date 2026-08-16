#!/usr/bin/env python3
"""rubric.json — validate, preview, plan UI entry, verify placement.

Rubric CREATION and ATTACHMENT have no Brightspace API (confirmed through
LE 1.93+): they happen in the UI, driven by Claude-in-Chrome or the user.
This tool makes that safe and checkable:

  rubric.py validate rubric.json         completeness gate (no auth)
  rubric.py preview  rubric.json         markdown table for user review
  rubric.py entry-plan rubric.json       exact UI steps (for Chrome/human)
  rubric.py verify rubric.json --ou N    API read-back: does the rubric
                                         exist and sit on its targets?

Schema: references/rubric-format.md. The write path is UI; the VERIFY
path is API (GET dropbox folder -> Assessment.Rubrics), keeping the
write-verify discipline even for browser work.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bsapi import BS, LE, die  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text())


def validate(r):
    errors, warnings = [], []
    if not r.get("name"):
        errors.append("no rubric name")
    rtype = r.get("type", "analytic")
    if rtype not in ("analytic", "holistic"):
        errors.append(f"type must be analytic|holistic (got {rtype})")
    levels = r.get("levels", [])
    if rtype == "analytic":
        if len(levels) < 2:
            errors.append("analytic rubric needs >=2 levels")
        pts = [lv.get("points") for lv in levels]
        if any(p is None for p in pts):
            errors.append("every level needs points")
        elif pts != sorted(pts, reverse=True):
            warnings.append("levels are not in descending point order "
                            "(D2L convention: best first)")
        crits = r.get("criteria", [])
        if not crits:
            errors.append("analytic rubric needs >=1 criterion")
        for c in crits:
            if not c.get("name"):
                errors.append("criterion without a name")
                continue
            descs = c.get("descriptions", [])
            if len(descs) != len(levels):
                errors.append(f"criterion '{c['name']}': {len(descs)} "
                              f"descriptions for {len(levels)} levels — "
                              "must align 1:1")
            elif any(not d for d in descs):
                warnings.append(f"criterion '{c['name']}': empty cell "
                                "description(s) — the rubric IS the "
                                "feedback, fill every cell")
    else:
        if len(r.get("overall_levels", [])) < 2:
            errors.append("holistic rubric needs >=2 overall_levels")
    for ov in r.get("overall_levels", []):
        if not ov.get("name"):
            errors.append("overall level without a name")
    for a in r.get("associate", []):
        if a.get("tool", "Dropbox") not in ("Dropbox", "Discussion",
                                            "Grades"):
            warnings.append(f"associate tool {a.get('tool')!r} — plan "
                            "supports Dropbox best; others are manual")
        if not a.get("title"):
            errors.append("associate entry without a target title")
    if not r.get("associate"):
        warnings.append("no 'associate' targets — rubric will be created "
                        "but attached to nothing")
    return errors, warnings


def preview(r):
    out = [f"# {r.get('name', '(unnamed rubric)')}  "
           f"({r.get('type', 'analytic')}, "
           f"{r.get('scoring', 'points')})", ""]
    levels = r.get("levels", [])
    if levels:
        head = "| Criterion | " + " | ".join(
            f"{lv['name']} ({lv.get('points', '?')} pts)"
            for lv in levels) + " |"
        out.append(head)
        out.append("|" + "---|" * (len(levels) + 1))
        for c in r.get("criteria", []):
            cells = [d.replace("\n", " ") for d in
                     c.get("descriptions", [])]
            out.append(f"| **{c['name']}** | " + " | ".join(cells) + " |")
        total = sum(lv.get("points", 0) for lv in levels)
        out.append("")
        out.append(f"Max per criterion: {max((lv.get('points', 0) for lv in levels), default=0)} — "
                   f"criteria: {len(r.get('criteria', []))} — "
                   f"max total: {max((lv.get('points', 0) for lv in levels), default=0) * len(r.get('criteria', []))}")
        _ = total
    for ov in r.get("overall_levels", []):
        out.append(f"- Overall '{ov['name']}'"
                   + (f" (from {ov['range_min']})" if "range_min" in ov
                      else "")
                   + (f": {ov.get('description', '')}" if ov.get("description") else ""))
    if r.get("associate"):
        out.append("")
        out.append("Attach to: " + "; ".join(
            f"{a.get('tool', 'Dropbox')} '{a['title']}'"
            for a in r["associate"]))
    return "\n".join(out)


def entry_plan(r):
    """Exact UI steps — consumed by Claude-in-Chrome or a human."""
    name = r.get("name", "")
    steps = [
        f"1. Course Admin → Rubrics → New Rubric.",
        f"2. Name: '{name}'. Type: {r.get('type', 'analytic').title()}. "
        f"Scoring: {r.get('scoring', 'points').title()}.",
    ]
    levels = r.get("levels", [])
    if levels:
        steps.append("3. Set levels (left-to-right, best first): " + ", ".join(
            f"'{lv['name']}' = {lv.get('points')} pts" for lv in levels)
            + ". Add/remove level columns to match exactly.")
        for i, c in enumerate(r.get("criteria", []), 1):
            cells = "; ".join(
                f"[{levels[j]['name']}] {d}" for j, d in
                enumerate(c.get("descriptions", [])))
            steps.append(f"4.{i} Criterion '{c['name']}' — cell text per "
                         f"level: {cells}")
    for i, ov in enumerate(r.get("overall_levels", []), 1):
        steps.append(f"5.{i} Overall Score level '{ov['name']}'"
                     + (f", start range {ov['range_min']}"
                        if "range_min" in ov else "")
                     + (f": {ov['description']}" if ov.get("description")
                        else ""))
    steps.append("6. Set rubric status to Published (draft rubrics can't "
                 "be attached).")
    for i, a in enumerate(r.get("associate", []), 1):
        steps.append(f"7.{i} Attach: {a.get('tool', 'Dropbox')} "
                     f"'{a['title']}' → edit → Evaluation & Feedback → "
                     f"Add Rubric → select '{name}'.")
    steps.append(f"8. Run: python3 rubric.py verify <rubric.json> --ou <ou> "
                 "to confirm by API read-back.")
    return "\n".join(steps)


def verify(r, ou):
    bs = BS()
    name = r.get("name")
    problems = []
    folders = bs.jget(f"/d2l/api/le/{LE}/{ou}/dropbox/folders/")
    by_title = {f.get("Name"): f for f in folders}
    for a in r.get("associate", []):
        if a.get("tool", "Dropbox") != "Dropbox":
            print(f"  ?  {a.get('tool')} '{a['title']}': verify not "
                  "supported — check in UI")
            continue
        f = by_title.get(a["title"])
        if not f:
            problems.append(f"no dropbox folder titled '{a['title']}'")
            continue
        rubrics = (f.get("Assessment") or {}).get("Rubrics") or []
        names = [rb.get("Name") for rb in rubrics]
        if name in names:
            print(f"  OK '{name}' attached to '{a['title']}' "
                  f"(folder {f.get('Id')})")
        else:
            problems.append(f"'{a['title']}' (folder {f.get('Id')}) has "
                            f"rubrics {names or 'none'} — '{name}' missing")
    if problems:
        for p in problems:
            print(f"  MISSING {p}")
        sys.exit(1)
    if not r.get("associate"):
        print("  (no associate targets declared — nothing to verify "
              "against; check Course Admin → Rubrics in the UI)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["validate", "preview", "entry-plan",
                                    "verify"])
    ap.add_argument("rubric_json")
    ap.add_argument("--ou", default=None)
    args = ap.parse_args()
    r = load(args.rubric_json)
    errors, warnings = validate(r)
    if args.cmd == "validate":
        for e in errors:
            print(f"  ERROR   {e}")
        for w in warnings:
            print(f"  warning {w}")
        print("valid" if not errors else f"{len(errors)} error(s)")
        sys.exit(1 if errors else 0)
    if errors:
        for e in errors:
            print(f"  ERROR   {e}")
        die("rubric spec incomplete — fix before proceeding")
    if args.cmd == "preview":
        print(preview(r))
    elif args.cmd == "entry-plan":
        print(entry_plan(r))
    elif args.cmd == "verify":
        if not args.ou:
            die("verify needs --ou")
        verify(r, args.ou)


if __name__ == "__main__":
    main()
