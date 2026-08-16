#!/usr/bin/env python3
"""Publish an async-package (manifest.json) into a Brightspace course module.

Usage:
  publish.py <package-dir> --ou <orgUnitId>                    # DRY RUN (default)
  publish.py <package-dir> --ou <orgUnitId> --execute          # do it
  publish.py <pkg> --ou <ou> --execute --into-module <id>      # reuse module
  publish.py <pkg> --ou <ou> --execute --skip-first <N>        # resume

Safety:
  - dry-run by default; prints the numbered action plan and exits
  - production host (brightspace.vanderbilt.edu) additionally requires
    --i-mean-production
  - every write is verified by an independent GET read-back (200 != landed)
  - POST-create only; this script never PUTs partial objects

See ../references/api-notes.md for endpoint details and known traps.
"""

import argparse
import json
import mimetypes
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bs_session import BASE, HOST, LE, die, mint_token  # noqa: E402

SIMPLE_UPLOAD_LIMIT = 400 * 1024 * 1024  # stay under D2L's ~488MB cap
PRODUCTION_HOSTS = {"brightspace.vanderbilt.edu"}


# ------------------------------------------------------------ plan building

def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n / 1:.1f}{unit}"
        n /= 1024


def build_plan(pkg, manifest):
    module = manifest["module"]
    plan = [{"action": "create-module", "title": module["title"],
             "description": module.get("description", "")}]
    for item in module["items"]:
        t = item["type"]
        if t == "html":
            f = pkg / item["file"]
            plan.append({"action": "upload-html", "title": item["title"],
                         "file": f, "size": f.stat().st_size if f.exists() else 0,
                         "description": item.get("description", "")})
        elif t == "video":
            f = pkg / item["file"]
            step = {"action": "upload-video", "title": item["title"],
                    "file": f, "size": f.stat().st_size if f.exists() else 0,
                    "description": item.get("description", "")}
            if item.get("captions"):
                step["captions"] = pkg / item["captions"]
            plan.append(step)
        elif t == "quiz":
            f = pkg / item["qti"]
            plan.append({"action": "import-quiz", "title": item["title"],
                         "file": f, "size": f.stat().st_size if f.exists() else 0,
                         "grade": item.get("grade", {}),
                         "description": item.get("description", "")})
        else:
            die(f"unknown item type in manifest: {t}")
    return plan


def print_plan(plan, ou):
    total = sum(s.get("size", 0) for s in plan)
    print(f"\nAction plan for ou={ou} on {HOST} "
          f"({len(plan)} steps, {human_size(total)} to upload):\n")
    for i, s in enumerate(plan):
        size = f"  [{human_size(s['size'])}]" if s.get("size") else ""
        cap = "  +captions" if s.get("captions") else ""
        print(f"  {i:2d}. {s['action']:<14} {s['title']}{size}{cap}")
    print()


# ------------------------------------------------------------ api operations

def api(s, method, path, **kw):
    r = s.request(method, f"{BASE}{path}", timeout=kw.pop("timeout", 120), **kw)
    return r


def get_org_code(s, ou):
    r = api(s, "GET", f"/d2l/api/lp/1.57/courses/{ou}")
    if r.status_code == 200:
        return r.json().get("Code") or str(ou)
    return str(ou)


def create_module(s, ou, title, description):
    body = {"Title": title, "ShortTitle": title[:50], "Type": 0,
            "ModuleStartDate": None, "ModuleEndDate": None,
            "ModuleDueDate": None, "IsHidden": False, "IsLocked": False,
            "Description": {"Html": description or "", "Text": ""}}
    r = api(s, "POST", f"/d2l/api/le/{LE}/{ou}/content/root/", json=body)
    if r.status_code not in (200, 201):
        die(f"create-module failed: {r.status_code} {r.text[:400]}")
    mod_id = r.json().get("Id")
    # read-back verify
    r2 = api(s, "GET", f"/d2l/api/le/{LE}/{ou}/content/modules/{mod_id}")
    if r2.status_code != 200 or r2.json().get("Title") != title:
        die(f"create-module verify failed for id {mod_id}")
    return mod_id


def find_module_by_title(s, ou, title):
    r = api(s, "GET", f"/d2l/api/le/{LE}/{ou}/content/root/")
    if r.status_code != 200:
        return None
    for m in r.json():
        if m.get("Type") == 0 and m.get("Title") == title:
            return m.get("Id")
    return None


def multipart_mixed_topic(s, ou, module_id, topic_json, file_path, content_type):
    """POST a topic + file in one multipart/mixed request."""
    boundary = f"d2lpub{uuid.uuid4().hex}"
    fname = Path(file_path).name
    head = (f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            f"{json.dumps(topic_json)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {content_type}\r\n"
            f'Content-Disposition: attachment; filename="{fname}"\r\n\r\n'
            ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    body = head + Path(file_path).read_bytes() + tail
    r = api(s, "POST",
            f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}/structure/",
            data=body,
            headers={"Content-Type": f"multipart/mixed; boundary={boundary}"},
            timeout=1800)
    return r


def upload_file_topic(s, ou, module_id, org_code, title, file_path,
                      description=""):
    size = Path(file_path).stat().st_size
    if size > SIMPLE_UPLOAD_LIMIT:
        die(f"{Path(file_path).name} is {human_size(size)} - above the simple "
            "upload limit. Use the resumable upload protocol "
            "(references/api-notes.md) or split/compress the video. "
            "Course videos this long should be rare; check the segment plan.")
    ct = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    topic = {"Title": title, "ShortTitle": title[:50], "Type": 1,
             "TopicType": 1,
             "Url": f"/content/enforced/{ou}-{org_code}/{Path(file_path).name}",
             "StartDate": None, "EndDate": None, "DueDate": None,
             "IsHidden": False, "IsLocked": False, "IsExempt": False,
             "Description": {"Html": description or "", "Text": ""}}
    r = multipart_mixed_topic(s, ou, module_id, topic, file_path, ct)
    if r.status_code not in (200, 201):
        die(f"upload of {Path(file_path).name} failed: "
            f"{r.status_code} {r.text[:400]}")
    return r.json().get("Id")


def create_link_topic(s, ou, module_id, title, url, description=""):
    topic = {"Title": title, "ShortTitle": title[:50], "Type": 1,
             "TopicType": 3, "Url": url,
             "StartDate": None, "EndDate": None, "DueDate": None,
             "IsHidden": False, "IsLocked": False, "IsExempt": False,
             "Description": {"Html": description or "", "Text": ""}}
    r = api(s, "POST",
            f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}/structure/",
            json=topic)
    if r.status_code not in (200, 201):
        die(f"link topic '{title}' failed: {r.status_code} {r.text[:400]}")
    return r.json().get("Id")


def import_qti(s, ou, zip_path):
    with open(zip_path, "rb") as fh:
        r = api(s, "POST", f"/d2l/api/le/{LE}/import/{ou}/imports/",
                files={"file": (Path(zip_path).name, fh, "application/zip")},
                timeout=600)
    if r.status_code not in (200, 201, 202):
        die(f"QTI import POST failed: {r.status_code} {r.text[:400]}")
    job = r.json().get("JobToken") or r.json().get("JobId")
    if not job:
        die(f"QTI import returned no job token: {r.text[:400]}")
    for _ in range(120):
        time.sleep(5)
        r = api(s, "GET", f"/d2l/api/le/{LE}/import/{ou}/imports/{job}")
        status = (r.json().get("Status") or "").upper() if r.status_code == 200 else ""
        if "FAIL" in status:
            die(f"QTI import job failed: {r.text[:400]}")
        if status in ("COMPLETED", "COMPLETE", "IMPORTED", "SUCCESS"):
            return job
    die("QTI import job did not finish within 10 minutes")


def find_quiz_by_name(s, ou, name):
    url = f"/d2l/api/le/{LE}/{ou}/quizzes/"
    while url:
        r = api(s, "GET", url)
        if r.status_code != 200:
            return None
        data = r.json()
        for q in data.get("Objects", data if isinstance(data, list) else []):
            if q.get("Name") == name:
                return q.get("QuizId") or q.get("Id")
        nxt = data.get("Next") if isinstance(data, dict) else None
        url = nxt.replace(BASE, "") if nxt else None
    return None


def verify_module_contents(s, ou, module_id):
    r = api(s, "GET",
            f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}/structure/")
    if r.status_code != 200:
        return []
    return [(t.get("Id"), t.get("Title")) for t in r.json()]


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--ou", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--into-module", type=int, default=None)
    ap.add_argument("--skip-first", type=int, default=0)
    ap.add_argument("--i-mean-production", action="store_true")
    args = ap.parse_args()

    pkg = Path(args.package)
    manifest_path = pkg / "manifest.json"
    if not manifest_path.exists():
        die(f"no manifest.json in {pkg}")
    manifest = json.loads(manifest_path.read_text())

    missing = []
    plan = build_plan(pkg, manifest)
    for step in plan:
        for key in ("file", "captions"):
            if step.get(key) and not Path(step[key]).exists():
                missing.append(str(step[key]))
    if missing:
        die("files referenced by manifest are missing (run "
            "validate_package.py):\n  " + "\n  ".join(missing))

    print_plan(plan, args.ou)

    if not args.execute:
        print("DRY RUN - nothing was uploaded. Re-run with --execute to "
              "publish (and confirm the ou with the user first).")
        return

    if HOST in PRODUCTION_HOSTS and not args.i_mean_production:
        die(f"{HOST} is PRODUCTION. Re-run with --i-mean-production after "
            "confirming with the user, or set BRIGHTSPACE_HOST to the test "
            "tenant.")

    s = mint_token()
    org_code = get_org_code(s, args.ou)
    results = []

    # step 0: module
    module_step, item_steps = plan[0], plan[1:]
    if args.into_module:
        module_id = args.into_module
        print(f" 0. using existing module {module_id}")
    else:
        existing = find_module_by_title(s, args.ou, module_step["title"])
        if existing:
            die(f"a module titled '{module_step['title']}' already exists "
                f"(id {existing}). Pass --into-module {existing} to add to "
                "it, or retitle in the manifest.")
        module_id = create_module(s, args.ou, module_step["title"],
                                  module_step["description"])
        print(f" 0. create-module OK -> id {module_id}")

    for i, step in enumerate(item_steps, 1):
        if i <= args.skip_first:
            print(f"{i:2d}. SKIPPED (--skip-first)")
            continue
        t0 = time.time()
        if step["action"] in ("upload-html", "upload-video"):
            tid = upload_file_topic(s, args.ou, module_id, org_code,
                                    step["title"], step["file"],
                                    step["description"])
            results.append((step["title"], f"topic {tid}"))
            if step.get("captions"):
                cid = upload_file_topic(
                    s, args.ou, module_id, org_code,
                    f"{step['title']} - captions (vtt)", step["captions"],
                    "Caption file. Attach to the video player via topic "
                    "settings if not picked up automatically.")
                results.append((f"{step['title']} [captions]", f"topic {cid}"))
        elif step["action"] == "import-quiz":
            import_qti(s, args.ou, step["file"])
            quiz_id = find_quiz_by_name(s, args.ou, step["title"])
            if quiz_id:
                url = (f"/d2l/lms/quizzing/user/quiz_summary.d2l"
                       f"?qi={quiz_id}&ou={args.ou}")
                tid = create_link_topic(s, args.ou, module_id, step["title"],
                                        url, step["description"])
                results.append((step["title"],
                                f"quiz {quiz_id}, link topic {tid}"))
            else:
                results.append((step["title"],
                                "IMPORTED but quiz not found by title - "
                                "check Question Library / quiz list in UI"))
        print(f"{i:2d}. {step['action']} OK ({time.time() - t0:.0f}s) - "
              f"{step['title']}")

    print("\nRead-back verification of module contents:")
    contents = verify_module_contents(s, args.ou, module_id)
    landed_titles = [t for _, t in contents]
    for title, note in results:
        mark = "OK " if any(title.split(" [")[0] in lt for lt in landed_titles) \
            else "?? "
        print(f"  {mark} {title}  ({note})")
    print(f"\nModule {module_id} now contains {len(contents)} topics. "
          "Verify one video plays with captions in the browser, then set "
          "quiz attempts/grading per the manifest grade blocks (UI or "
          "Playwright - see SKILL.md 'manual tail').")


if __name__ == "__main__":
    main()
