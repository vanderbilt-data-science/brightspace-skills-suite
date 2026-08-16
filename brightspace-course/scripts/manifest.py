#!/usr/bin/env python3
"""course.json loading, completeness validation, and operation planning.

The manifest-first contract (references/course-manifest.md): map source
material into course.json, `validate` it for completeness, and only then
`apply` it to Brightspace. Used by bscourse.py; importable on its own.
"""

import json
import re
from datetime import datetime
from pathlib import Path

SIMPLE_UPLOAD_LIMIT = 400 * 1024 * 1024
CCC_HEAD_MARK = "/shared/D2L/Courseware_HTML_Templates"
PLACEHOLDER_RE = re.compile(r"\[([^\]\[]{3,80})\]")
IGNORED_PLACEHOLDERS = re.compile(r"^\s*(\d+|[A-Za-z])\s*$")  # [1], [a] etc.

# Page template a course uses. Optional — default is "none" (raw HTML,
# no house style enforced). CCC is one option among several.
KNOWN_TEMPLATES = ("none", "plain", "ccc")


def course_template(manifest):
    """The page template for this course: manifest course.template, or the
    --profile-mapped value, defaulting to 'none' (no house style)."""
    t = (manifest.get("course", {}) or {}).get("template", "none")
    return t if t in KNOWN_TEMPLATES else "custom"


def load_manifest(path):
    p = Path(path)
    manifest = json.loads(p.read_text())
    return manifest, p.parent


def _iso_utc(s):
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.tzinfo is not None
    except (ValueError, AttributeError):
        return False


def _page_placeholders(text):
    stripped = re.sub(r"<[^>]+>", " ", text)
    return [m for m in PLACEHOLDER_RE.findall(stripped)
            if not IGNORED_PLACEHOLDERS.match(m)]


def validate(manifest, base, profile="auto"):
    """Return (errors, warnings, stats). Errors block apply.

    `profile` selects how strictly pages are checked:
      auto  - derive from the manifest's course.template (default)
      none  - raw HTML: only placeholder + file checks
      plain - the neutral kit
      ccc   - the Vanderbilt CCC page kit (checks shared-asset <head>)
    An explicit profile overrides the manifest.
    """
    errors, warnings = [], []
    if profile == "auto":
        profile = course_template(manifest)
    stats = {"modules": 0, "pages": 0, "files": 0, "videos": 0,
             "quizzes": 0, "assignments": 0, "announcements": 0,
             "upload_bytes": 0}

    def resolve(rel, ctx):
        f = base / rel
        if not f.exists():
            errors.append(f"{ctx}: file not found: {rel}")
            return None
        stats["upload_bytes"] += f.stat().st_size
        return f

    def need(obj, key, ctx):
        if not obj.get(key):
            errors.append(f"{ctx}: missing required field '{key}'")
            return False
        return True

    course = manifest.get("course", {})
    if not course.get("name"):
        warnings.append("course: no 'name' set")
    no_class = set(course.get("no_class_dates", []))
    term_start, term_end = course.get("term_start"), course.get("term_end")

    seen_modules = set()
    for m in manifest.get("modules", []):
        if not need(m, "title", "module"):
            continue
        title = m["title"]
        ctx = f"module '{title}'"
        if title in seen_modules:
            errors.append(f"{ctx}: duplicate module title")
        seen_modules.add(title)
        stats["modules"] += 1
        content_count = 0
        seen_titles = set()

        for pg in m.get("pages", []):
            if not (need(pg, "title", ctx) and need(pg, "file", ctx)):
                continue
            content_count += 1
            stats["pages"] += 1
            if pg["title"] in seen_titles:
                errors.append(f"{ctx}: duplicate item title '{pg['title']}'")
            seen_titles.add(pg["title"])
            f = resolve(pg["file"], f"{ctx} page '{pg['title']}'")
            if not f:
                continue
            text = f.read_text(errors="replace")
            left = _page_placeholders(text)
            if left:
                errors.append(
                    f"{ctx} page '{pg['title']}': unresolved placeholders: "
                    + "; ".join(f"[{p}]" for p in left[:5]))
            kit = pg.get("kit", "raw")
            if profile == "ccc" and kit != "raw" \
                    and CCC_HEAD_MARK not in text:
                errors.append(
                    f"{ctx} page '{pg['title']}': course template is 'ccc' "
                    f"and this page declares kit '{kit}', but it lacks the "
                    "CCC shared-template <head> assets (copy from "
                    "assets/ccc-templates/, or set course.template to "
                    "'plain'/'none')")

        for fl in m.get("files", []):
            if need(fl, "title", ctx) and need(fl, "file", ctx):
                content_count += 1
                stats["files"] += 1
                resolve(fl["file"], f"{ctx} file '{fl['title']}'")

        for v in m.get("videos", []):
            if not (need(v, "title", ctx) and need(v, "file", ctx)):
                continue
            content_count += 1
            stats["videos"] += 1
            f = resolve(v["file"], f"{ctx} video '{v['title']}'")
            if f and f.stat().st_size > SIMPLE_UPLOAD_LIMIT:
                errors.append(f"{ctx} video '{v['title']}': over the "
                              "~400MB simple-upload limit — segment it")
            if v.get("captions"):
                resolve(v["captions"], f"{ctx} captions for '{v['title']}'")
            else:
                warnings.append(f"{ctx} video '{v['title']}': no captions")

        for q in m.get("quizzes", []):
            if not (need(q, "title", ctx) and need(q, "qti", ctx)):
                continue
            stats["quizzes"] += 1
            f = resolve(q["qti"], f"{ctx} quiz '{q['title']}'")
            if f and f.read_bytes()[:2] != b"PK":
                errors.append(f"{ctx} quiz '{q['title']}': {q['qti']} is "
                              "not a zip package")
            if not q.get("link_in_module", True):
                warnings.append(f"{ctx} quiz '{q['title']}': never linked "
                                "into a module")

        if profile in ("ccc", "plain") and not any(
                pg.get("kit") == "module-overview"
                for pg in m.get("pages", [])) \
                and title.lower().startswith("module"):
            warnings.append(f"{ctx}: no module-overview page "
                            "(good practice; set course.template to 'none' "
                            "to silence)")
        if content_count == 0 and not m.get("quizzes"):
            warnings.append(f"{ctx}: empty module (scaffold only)")

    seen_assign = set()
    for a in manifest.get("assignments", []):
        if not need(a, "title", "assignment"):
            continue
        ctx = f"assignment '{a['title']}'"
        stats["assignments"] += 1
        if a["title"] in seen_assign:
            errors.append(f"{ctx}: duplicate assignment title")
        seen_assign.add(a["title"])
        due = a.get("due")
        if due:
            if not _iso_utc(due):
                errors.append(f"{ctx}: due date '{due}' is not "
                              "timezone-aware ISO-8601 (use ...Z)")
            else:
                if due[:10] in no_class:
                    warnings.append(f"{ctx}: due on a no-class date {due[:10]}")
                if term_start and due < term_start:
                    warnings.append(f"{ctx}: due before term start")
                if term_end and due > term_end:
                    warnings.append(f"{ctx}: due after term end")
        else:
            warnings.append(f"{ctx}: no due date")
        if not a.get("out_of"):
            warnings.append(f"{ctx}: no points (out_of)")
        if a.get("instructions_file"):
            resolve(a["instructions_file"], ctx)
        elif not a.get("instructions"):
            warnings.append(f"{ctx}: no instructions")

    for n in manifest.get("announcements", []):
        if not need(n, "title", "announcement"):
            continue
        ctx = f"announcement '{n['title']}'"
        stats["announcements"] += 1
        if n.get("html_file"):
            resolve(n["html_file"], ctx)
        elif not n.get("text"):
            errors.append(f"{ctx}: needs 'text' or 'html_file'")
        if n.get("start") and not _iso_utc(n["start"]):
            errors.append(f"{ctx}: start '{n['start']}' is not "
                          "timezone-aware ISO-8601")

    return errors, warnings, stats


def build_ops(manifest, base):
    """Ordered operations for apply: modules, then their content, then
    assignments, then announcements."""
    ops = []
    for m in manifest.get("modules", []):
        ops.append({"op": "module", "title": m["title"]})
        for pg in m.get("pages", []):
            ops.append({"op": "page", "module": m["title"],
                        "title": pg["title"], "file": base / pg["file"]})
        for fl in m.get("files", []):
            ops.append({"op": "file", "module": m["title"],
                        "title": fl["title"], "file": base / fl["file"]})
        for v in m.get("videos", []):
            ops.append({"op": "video", "module": m["title"],
                        "title": v["title"], "file": base / v["file"],
                        "captions": (base / v["captions"])
                        if v.get("captions") else None})
        for q in m.get("quizzes", []):
            ops.append({"op": "quiz", "module": m["title"]
                        if q.get("link_in_module", True) else None,
                        "title": q["title"], "qti": base / q["qti"]})
    for a in manifest.get("assignments", []):
        instructions = a.get("instructions", "")
        if a.get("instructions_file"):
            instructions = (base / a["instructions_file"]).read_text()
        ops.append({"op": "assignment", "title": a["title"],
                    "due": a.get("due"), "out_of": a.get("out_of"),
                    "hidden": a.get("hidden", False),
                    "instructions": instructions,
                    "grade_item": a.get("grade_item")})
    for n in manifest.get("announcements", []):
        if n.get("skip"):
            ops.append({"op": "manual", "title": n["title"],
                        "note": n.get("skip_reason", "marked skip")})
            continue
        html = n.get("text", "")
        if n.get("html_file"):
            html = (base / n["html_file"]).read_text()
        ops.append({"op": "announce", "title": n["title"], "html": html,
                    "draft": n.get("draft", False),
                    "start": n.get("start"), "pin": n.get("pin", False)})
    return ops


def print_report(errors, warnings, stats):
    print(f"Manifest: {stats['modules']} modules, {stats['pages']} pages, "
          f"{stats['files']} files, {stats['videos']} videos, "
          f"{stats['quizzes']} quizzes, {stats['assignments']} assignments, "
          f"{stats['announcements']} announcements; "
          f"{stats['upload_bytes'] / 1e6:.1f}MB to upload")
    for e in errors:
        print(f"  ERROR   {e}")
    for w in warnings:
        print(f"  warning {w}")
    if errors:
        print(f"\n{len(errors)} error(s) — fix these before apply.")
    elif warnings:
        print(f"\nValid with {len(warnings)} warning(s).")
    else:
        print("\nValid — complete for this profile.")
    return not errors
