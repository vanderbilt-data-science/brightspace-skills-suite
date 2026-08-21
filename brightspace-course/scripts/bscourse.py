#!/usr/bin/env python3
"""bscourse — manage a Brightspace course from the command line.

Every write is DRY-RUN by default: the command prints exactly what it would
do and exits. Add --execute to do it. On the production host
(brightspace.vanderbilt.edu) --execute additionally requires
--i-mean-production.

Subcommands:
  map          show a course's full content structure (+ quizzes, dropbox,
               announcements) — also how we document a template course
  setup        copy components from a template course into this one
               (Course Copy API job) and verify
  syllabus     upload/replace the syllabus file in its module
  upload       upload any file (notes, slides, handouts) as a content topic
  page         create an HTML page topic from an .html file
  video        upload a video (+ optional .vtt captions) as a content topic
  assignment   create an assignment (dropbox folder) with due date/points
  quiz-import  import a QTI package (quiz questions cannot be created via
               REST — import is the only path) and link it into a module
  announce     post an announcement (supports future StartDate scheduling)
  rm-module    delete a module by id (cleanup of test artifacts)

Common flags: --ou (course), --execute, --tag (suffix titles, e.g. a bstest
run id), --i-mean-production.  Auth/host handling lives in bsapi.py.
"""

import argparse
import json
import mimetypes
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bsapi import (BASE, HOST, LE, LP, PRODUCTION_HOSTS, BS, die,  # noqa: E402
                   rich)

SIMPLE_UPLOAD_LIMIT = 400 * 1024 * 1024


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def tagged(title, args):
    return f"{title} [{args.tag}]" if getattr(args, "tag", None) else title


def guard_execute(args):
    """Dry-run gate + production gate. Returns True when writes may proceed."""
    if not args.execute:
        print("\nDRY RUN — nothing was changed. Re-run with --execute "
              "(after confirming the plan and the ou with the user).")
        return False
    if HOST in PRODUCTION_HOSTS and not args.i_mean_production:
        die(f"{HOST} is PRODUCTION. Re-run with --i-mean-production after "
            "explicit user confirmation, or set BRIGHTSPACE_HOST to the "
            "test tenant.")
    return True


# ---------------------------------------------------------------- content

def get_org_code(bs, ou):
    r = bs.get(f"/d2l/api/lp/{LP}/courses/{ou}", ok=None)
    if r.status_code == 200:
        return r.json().get("Code") or str(ou)
    return str(ou)


def root_modules(bs, ou):
    return bs.jget(f"/d2l/api/le/{LE}/{ou}/content/root/")


def module_structure(bs, ou, module_id):
    return bs.jget(f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}"
                   "/structure/")


def _content_flags(e):
    """Visibility/date markers for a content entry (module or topic) —
    the switches behind "why can't students see X"."""
    flags = []
    if e.get("IsHidden"):
        flags.append("HIDDEN")
    if e.get("IsLocked"):
        flags.append("locked")
    for keys, label in ((("StartDate", "ModuleStartDate"), "from"),
                        (("EndDate", "ModuleEndDate"), "until"),
                        (("DueDate", "ModuleDueDate"), "due")):
        v = next((e[k] for k in keys if e.get(k)), None)
        if v:
            flags.append(f"{label} {v[:10]}")
    return flags


def walk_content(bs, ou):
    """Yield (depth, kind, id, title, extra) over the whole content tree.
    extra carries type/url plus HIDDEN/locked/date flags."""
    def rec(entries, depth):
        for e in entries:
            flags = _content_flags(e)
            if e.get("Type") == 0:
                yield (depth, "module", e.get("Id"), e.get("Title"),
                       ", ".join(flags))
                yield from rec(module_structure(bs, ou, e["Id"]), depth + 1)
            else:
                tt = {1: "file", 2: "link", 3: "link", 5: "scorm"}.get(
                    e.get("TopicType"), f"tt{e.get('TopicType')}")
                base = f"{tt} {e.get('Url') or ''}".strip()
                yield (depth, "topic", e.get("Id"), e.get("Title"),
                       ", ".join([base] + flags) if flags else base)
    yield from rec(root_modules(bs, ou), 0)


def find_module(bs, ou, title):
    """Find a module id by exact title anywhere in the tree."""
    for depth, kind, mid, mtitle, _ in walk_content(bs, ou):
        if kind == "module" and mtitle == title:
            return mid
    return None


def ensure_module(bs, ou, title, description=""):
    mid = find_module(bs, ou, title)
    if mid:
        return mid, False
    body = {"Title": title, "ShortTitle": title[:50], "Type": 0,
            "ModuleStartDate": None, "ModuleEndDate": None,
            "ModuleDueDate": None, "IsHidden": False, "IsLocked": False,
            "Description": {"Html": description, "Text": ""}}
    r = bs.post(f"/d2l/api/le/{LE}/{ou}/content/root/", json=body)
    mid = r.json().get("Id")
    got = bs.jget(f"/d2l/api/le/{LE}/{ou}/content/modules/{mid}")
    if got.get("Title") != title:
        die(f"module create verify failed for id {mid}")
    return mid, True


def upload_file_topic(bs, ou, module_id, org_code, title, file_path,
                      description=""):
    """Topic + file bytes in one multipart/mixed POST (live-validated)."""
    file_path = Path(file_path)
    size = file_path.stat().st_size
    if size > SIMPLE_UPLOAD_LIMIT:
        die(f"{file_path.name} is {human_size(size)} — above the simple "
            "upload limit (~488MB). Split/compress it, or extend this "
            "script with the resumable protocol "
            "(references/api-quickref.md).")
    ct = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    topic = {"Title": title, "ShortTitle": title[:50], "Type": 1,
             "TopicType": 1,
             "Url": f"/content/enforced/{ou}-{org_code}/{file_path.name}",
             "StartDate": None, "EndDate": None, "DueDate": None,
             "IsHidden": False, "IsLocked": False, "IsExempt": False,
             "Description": {"Html": description, "Text": ""}}
    boundary = f"bsc{uuid.uuid4().hex}"
    head = (f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            f"{json.dumps(topic)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {ct}\r\n"
            f'Content-Disposition: attachment; filename="{file_path.name}"'
            "\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    r = bs.post(f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}"
                "/structure/",
                data=head + file_path.read_bytes() + tail,
                headers={"Content-Type":
                         f"multipart/mixed; boundary={boundary}"},
                timeout=1800)
    tid = r.json().get("Id")
    # read-back verify
    titles = [t.get("Title") for t in module_structure(bs, ou, module_id)]
    if title not in titles:
        die(f"upload of {file_path.name} returned {r.status_code} but the "
            "topic did not appear in the module (200 != landed)")
    return tid


def create_link_topic(bs, ou, module_id, title, url, description=""):
    topic = {"Title": title, "ShortTitle": title[:50], "Type": 1,
             "TopicType": 3, "Url": url,
             "StartDate": None, "EndDate": None, "DueDate": None,
             "IsHidden": False, "IsLocked": False, "IsExempt": False,
             "Description": {"Html": description, "Text": ""}}
    r = bs.post(f"/d2l/api/le/{LE}/{ou}/content/modules/{module_id}"
                "/structure/", json=topic)
    return r.json().get("Id")


# ------------------------------------------------------------ subcommands

def cmd_map(bs, args):
    print(f"Content tree for ou={args.ou} on {HOST}:")
    n_mod = n_top = n_hidden = 0
    for depth, kind, oid, title, extra in walk_content(bs, args.ou):
        n_mod += kind == "module"
        n_top += kind == "topic"
        hidden = "HIDDEN" in (extra or "")
        n_hidden += hidden
        pad = "  " * depth
        note = f"  ({extra})" if extra and (args.verbose or hidden) else ""
        mark = "▸" if kind == "module" else "·"
        print(f"  {pad}{mark} {title}  [{kind} {oid}]{note}")
    quizzes = []
    r = bs.get(f"/d2l/api/le/{LE}/{args.ou}/quizzes/", ok=None)
    if r.status_code == 200:
        data = r.json()
        quizzes = data.get("Objects", data if isinstance(data, list) else [])
    dropbox = bs.get(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/",
                     ok=None)
    folders = dropbox.json() if dropbox.status_code == 200 else []
    news = bs.get(f"/d2l/api/le/{LE}/{args.ou}/news/", ok=None)
    news_items = news.json() if news.status_code == 200 else []
    print(f"\n  {n_mod} modules, {n_top} topics, {len(quizzes)} quizzes, "
          f"{len(folders)} assignments, {len(news_items)} announcements")
    if n_hidden:
        print(f"  ! {n_hidden} HIDDEN content item(s) — invisible to "
              "students (as is everything inside a hidden module)")
    if args.verbose:
        for q in quizzes:
            due = q.get("DueDate")
            print(f"    quiz {q.get('QuizId') or q.get('Id')}: "
                  f"{q.get('Name')}" + (f" (due {due})" if due else ""))
        for f in folders:
            print(f"    assignment {f.get('Id')}: {f.get('Name')} "
                  f"(due {f.get('DueDate')})")


def cmd_setup(bs, args):
    components = ([c.strip() for c in args.components.split(",")]
                  if args.components else None)
    print(f"Template copy plan: ou={args.source} -> ou={args.ou} on {HOST}")
    print(f"  components: {components or 'ALL (Brightspace default)'}")
    if args.offset_days:
        print(f"  dates offset by {args.offset_days} days")
    print("\nSource (template) structure:")
    for depth, kind, oid, title, _ in walk_content(bs, args.source):
        print(f"  {'  ' * depth}{'▸' if kind == 'module' else '·'} {title}")
    if not guard_execute(args):
        return
    body = {"SourceOrgUnitId": int(args.source)}
    if components:
        body["Components"] = components
    if args.offset_days:
        body["DaysToOffsetDates"] = args.offset_days
    r = bs.post(f"/d2l/api/le/{LE}/import/{args.ou}/copy/", json=body,
                ok=(200, 201, 202))
    job = r.json().get("JobToken")
    if not job:
        die(f"copy job returned no JobToken: {r.text[:300]}")
    print(f"copy job queued: {job}")
    for _ in range(180):
        time.sleep(5)
        r = bs.get(f"/d2l/api/le/{LE}/import/{args.ou}/copy/{job}", ok=None)
        status = (r.json().get("Status") or "").upper() \
            if r.status_code == 200 else f"http {r.status_code}"
        print(f"  … {status}")
        if status in ("COMPLETE", "COMPLETED"):
            break
        if status in ("FAILED", "CANCELLED"):
            die(f"copy job ended {status}")
    else:
        die("copy job did not finish within 15 minutes")
    print("\nRead-back — destination structure now:")
    cmd_map(bs, argparse.Namespace(ou=args.ou, verbose=False))


def cmd_syllabus(bs, args):
    _upload_into_module(bs, args, default_title="Syllabus")


def cmd_upload(bs, args):
    _upload_into_module(bs, args, default_title=Path(args.file).stem)


def cmd_page(bs, args):
    if not args.file.endswith((".html", ".htm")):
        die("page expects an .html file (use `upload` for other files)")
    _upload_into_module(bs, args, default_title=Path(args.file).stem)


def _upload_into_module(bs, args, default_title):
    f = Path(args.file)
    if not f.exists():
        die(f"no such file: {f}")
    title = tagged(args.title or default_title, args)
    print(f"Plan: upload {f.name} ({human_size(f.stat().st_size)}) as "
          f"topic '{title}' into module '{args.module}' of ou={args.ou} "
          f"on {HOST}")
    if not guard_execute(args):
        return
    mid, created = ensure_module(bs, args.ou, args.module)
    if created:
        print(f"  created module '{args.module}' (id {mid})")
    org_code = get_org_code(bs, args.ou)
    tid = upload_file_topic(bs, args.ou, mid, org_code, title, f,
                            args.description or "")
    print(f"OK: topic {tid} verified in module {mid}")


def cmd_video(bs, args):
    f = Path(args.file)
    if not f.exists():
        die(f"no such file: {f}")
    title = tagged(args.title or f.stem, args)
    cap = Path(args.captions) if args.captions else None
    if cap and not cap.exists():
        die(f"no such captions file: {cap}")
    print(f"Plan: upload video {f.name} ({human_size(f.stat().st_size)})"
          + (f" + captions {cap.name}" if cap else "")
          + f" as '{title}' into module '{args.module}' of ou={args.ou} "
            f"on {HOST}")
    if not guard_execute(args):
        return
    mid, created = ensure_module(bs, args.ou, args.module)
    if created:
        print(f"  created module '{args.module}' (id {mid})")
    org_code = get_org_code(bs, args.ou)
    tid = upload_file_topic(bs, args.ou, mid, org_code, title, f,
                            args.description or "")
    print(f"OK: video topic {tid} verified")
    if cap:
        cid = upload_file_topic(
            bs, args.ou, mid, org_code, f"{title} — captions (vtt)", cap,
            "Caption file. Attach via the video player settings if not "
            "picked up automatically.")
        print(f"OK: captions topic {cid} verified")


def cmd_assignment(bs, args):
    instructions = ""
    if args.instructions_file:
        instructions = Path(args.instructions_file).read_text()
    elif args.instructions:
        instructions = args.instructions
    name = tagged(args.title, args)
    body = {
        "CategoryId": None,
        "Name": name,
        "CustomInstructions": rich(instructions),
        "Availability": None,
        "GroupTypeId": None,
        "DueDate": args.due,
        "DisplayInCalendar": bool(args.due),
        "NotificationEmail": None,
        "IsHidden": args.hidden,
        "IsAnonymous": False,
        "DropboxType": 2,        # individual
        "SubmissionType": 0,     # file
        "CompletionType": 0,     # on submission
        "GradeItemId": None,
        "AllowOnlyUsersWithSpecialAccess": False,
    }
    if args.out_of:
        body["Assessment"] = {"ScoreDenominator": args.out_of}
    print(f"Plan: create assignment '{name}' in ou={args.ou} on {HOST}")
    print(json.dumps(body, indent=2)[:800])
    if not guard_execute(args):
        return
    r = bs.post(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/", json=body)
    fid = r.json().get("Id")
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/{fid}")
    if got.get("Name") != name:
        die(f"assignment verify failed for id {fid}")
    if args.due and (got.get("DueDate") or "")[:16] != args.due[:16]:
        die(f"assignment {fid} landed but DueDate read-back is "
            f"{got.get('DueDate')} (expected {args.due}) — fix via UI/PUT")
    print(f"OK: assignment {fid} verified (due {got.get('DueDate')})")


def cmd_quiz_import(bs, args):
    z = Path(args.qti)
    if not z.exists():
        die(f"no such package: {z}")
    print(f"Plan: import QTI package {z.name} "
          f"({human_size(z.stat().st_size)}) into ou={args.ou} on {HOST}"
          + (f", then link quiz '{args.title}' into module "
             f"'{args.module}'" if args.module else ""))
    if not guard_execute(args):
        return
    with open(z, "rb") as fh:
        r = bs.post(f"/d2l/api/le/{LE}/import/{args.ou}/imports/",
                    files={"file": (z.name, fh, "application/zip")},
                    ok=(200, 201, 202), timeout=600)
    job = r.json().get("JobToken") or r.json().get("JobId")
    if not job:
        die(f"import returned no job token: {r.text[:300]}")
    print(f"import job queued: {job}")
    for _ in range(120):
        time.sleep(5)
        r = bs.get(f"/d2l/api/le/{LE}/import/{args.ou}/imports/{job}",
                   ok=None)
        status = (r.json().get("Status") or "").upper() \
            if r.status_code == 200 else ""
        if "FAIL" in status:
            die(f"import job failed: {r.text[:300]}")
        if status in ("COMPLETED", "COMPLETE", "IMPORTED", "SUCCESS"):
            break
    else:
        die("import job did not finish within 10 minutes")
    print("import complete")
    if args.title:
        quiz_id = None
        data = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/quizzes/")
        for q in data.get("Objects",
                          data if isinstance(data, list) else []):
            if q.get("Name") == args.title:
                quiz_id = q.get("QuizId") or q.get("Id")
        if not quiz_id:
            print(f"?? quiz named '{args.title}' not found after import — "
                  "check the Question Library in the UI")
            return
        print(f"OK: quiz {quiz_id} present")
        if args.module:
            mid, _ = ensure_module(bs, args.ou, args.module)
            url = (f"/d2l/lms/quizzing/user/quiz_summary.d2l"
                   f"?qi={quiz_id}&ou={args.ou}")
            tid = create_link_topic(bs, args.ou, mid,
                                    tagged(args.title, args), url)
            print(f"OK: link topic {tid} in module {mid}")


def _find_quiz(bs, ou, name):
    data = bs.jget(f"/d2l/api/le/{LE}/{ou}/quizzes/")
    for q in data.get("Objects", data if isinstance(data, list) else []):
        if q.get("Name") == name:
            return q.get("QuizId") or q.get("Id")
    return None


def _rtin(block):
    """QuizReadData rich block -> QuizData shape (RichText->RichTextInput)."""
    t = (block or {}).get("Text", {})
    return {"Text": {"Content": t.get("Html") or t.get("Text") or "",
                     "Type": "Html" if t.get("Html") else "Text"},
            "IsDisplayed": (block or {}).get("IsDisplayed", False)}


def cmd_quiz_publish(bs, args):
    """quiz.json -> QTI zip -> import -> settings PUT -> link -> verify."""
    import tempfile
    import qti
    errs, warns = qti.validate_spec(args.quiz_json)
    for w in warns:
        print(f"  warning {w}")
    if errs:
        for e in errs:
            print(f"  ERROR   {e}")
        die("quiz spec incomplete — fix before publishing")
    name, settings, questions = qti.load_spec(args.quiz_json)
    name = tagged(name, args)
    print(f"Plan: publish quiz '{name}' ({len(questions)} questions) to "
          f"ou={args.ou} on {HOST}")
    to_set = {k: settings[k] for k in
              ("due", "start", "end", "attempts", "time_limit_minutes",
               "shuffle", "grade_item_id", "description", "is_active")
              if k in settings}
    if to_set:
        print(f"  settings via shell PUT: {to_set}")
    if args.module:
        print(f"  then link into module '{args.module}'")
    if not guard_execute(args):
        return

    # imports land under the UNTAGGED spec name; check both
    raw_name = qti.load_spec(args.quiz_json)[0]
    for existing in {name, raw_name}:
        if _find_quiz(bs, args.ou, existing):
            die(f"a quiz named '{existing}' already exists in ou={args.ou}"
                " — rename in quiz.json or rm-quiz the old one first")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
    qti.build(args.quiz_json, zip_path)
    qargs = argparse.Namespace(ou=args.ou, qti=zip_path, title=None,
                               module=None, execute=True, tag=None,
                               i_mean_production=args.i_mean_production)
    cmd_quiz_import(bs, qargs)
    quiz_id = _find_quiz(bs, args.ou, name if not args.tag else name) \
        or _find_quiz(bs, args.ou, qti.load_spec(args.quiz_json)[0])
    if not quiz_id:
        die("import completed but the quiz was not found by name — check "
            "the Question Library in the UI")
    print(f"quiz {quiz_id} imported")

    # settings: GET shell -> transform to QuizData -> merge -> PUT -> verify
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{quiz_id}")
    body = {k: v for k, v in got.items()
            if k not in ("QuizId", "ActivityId", "AttemptsAllowed")}
    body["NumberOfAttemptsAllowed"] = (
        None if got.get("AttemptsAllowed", {}).get("IsUnlimited")
        else got.get("AttemptsAllowed", {}).get("NumberOfAttemptsAllowed"))
    for blk in ("Instructions", "Description", "Header", "Footer"):
        body[blk] = _rtin(got.get(blk))
    body["Name"] = name
    if "due" in settings:
        body["DueDate"] = settings["due"]
    if "start" in settings:
        body["StartDate"] = settings["start"]
    if "end" in settings:
        body["EndDate"] = settings["end"]
    # live-validated: quiz calendar association REQUIRES start or end —
    # DueDate alone 400s ("Cannot have schedule association without...")
    body["DisplayInCalendar"] = bool(settings.get("start")
                                     or settings.get("end"))
    if "attempts" in settings:
        body["NumberOfAttemptsAllowed"] = settings["attempts"]
    if "time_limit_minutes" in settings:
        body["SubmissionTimeLimit"] = {"IsEnforced": True, "ShowClock": True,
                                       "TimeLimitValue":
                                       settings["time_limit_minutes"]}
    if "shuffle" in settings:
        body["Shuffle"] = bool(settings["shuffle"])
    if "grade_item_id" in settings:
        body["GradeItemId"] = settings["grade_item_id"]
        body["AutoExportToGrades"] = True
        body["IsAutoSetGraded"] = True
    if "description" in settings:
        body["Description"] = {"Text": {"Content": settings["description"],
                                        "Type": "Html"}, "IsDisplayed": True}
    body["IsActive"] = bool(settings.get("is_active", False))
    bs.put(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{quiz_id}", json=body)
    check = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{quiz_id}")
    problems = []
    if "due" in settings and (check.get("DueDate") or "")[:16] \
            != settings["due"][:16]:
        problems.append(f"DueDate={check.get('DueDate')}")
    if "attempts" in settings and not check.get(
            "AttemptsAllowed", {}).get("IsUnlimited") and check.get(
            "AttemptsAllowed", {}).get("NumberOfAttemptsAllowed") \
            != settings["attempts"]:
        problems.append(f"Attempts={check.get('AttemptsAllowed')}")
    if problems:
        die(f"settings PUT landed 200 but read-back mismatches: {problems}")
    nq = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{quiz_id}/questions/")
    n_landed = len(nq.get("Objects", nq if isinstance(nq, list) else []))
    print(f"OK: quiz {quiz_id} verified — {n_landed} questions, settings "
          "applied" + ("" if n_landed == len(questions) else
                       f" (SPEC HAD {len(questions)} — INVESTIGATE)"))
    if args.module:
        mid, _ = ensure_module(bs, args.ou, args.module)
        url = (f"/d2l/lms/quizzing/user/quiz_summary.d2l"
               f"?qi={quiz_id}&ou={args.ou}")
        tid = create_link_topic(bs, args.ou, mid, name, url)
        print(f"OK: link topic {tid} in module '{args.module}'")


def cmd_rm_quiz(bs, args):
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{args.id}")
    print(f"Plan: DELETE quiz {args.id} '{got.get('Name')}' from "
          f"ou={args.ou} on {HOST}")
    if not guard_execute(args):
        return
    bs.delete(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{args.id}")
    r = bs.get(f"/d2l/api/le/{LE}/{args.ou}/quizzes/{args.id}", ok=None)
    if r.status_code == 200:
        die(f"quiz {args.id} still present after delete")
    print(f"OK: quiz {args.id} deleted")


def cmd_announce(bs, args):
    html = Path(args.html_file).read_text() if args.html_file else args.text
    if not html:
        die("provide --html-file or --text")
    title = tagged(args.title, args)
    # live-validated 2026-08-16: StartDate is REQUIRED, and Body takes the
    # RichText shape {Text, Html} (like dropbox feedback), NOT RichTextInput.
    start = args.start or (time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                                         time.gmtime()))
    text = re.sub(r"<[^>]+>", " ", html).strip()
    body = {"Title": title, "Body": {"Text": text, "Html": html},
            "StartDate": start, "EndDate": None,
            "IsGlobal": False, "IsPublished": not args.draft,
            "ShowOnlyInCourseOfferings": True,
            "IsAuthorInfoShown": False, "IsPinned": args.pin,
            "IsStartDateShown": bool(args.start), "SortOrder": None}
    print(f"Plan: post announcement '{title}' to ou={args.ou} on {HOST}"
          + (f" scheduled for {args.start}" if args.start else "")
          + (" as DRAFT" if args.draft else ""))
    if not guard_execute(args):
        return
    # docs require multipart/mixed (part 1 = NewsItemData)
    boundary = f"bsc{uuid.uuid4().hex}"
    raw = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n"
           f"{json.dumps(body)}\r\n--{boundary}--\r\n").encode()
    r = bs.post(f"/d2l/api/le/{LE}/{args.ou}/news/", data=raw,
                headers={"Content-Type":
                         f"multipart/mixed; boundary={boundary}"},
                ok=None)
    if r.status_code == 500:
        die("announce hit the tenant's known news-create 500 (see "
            "references/capability-map.md, probed 2026-08-16): the Valence "
            "create endpoint is broken on this LMS build. Fallback: post "
            "the announcement via the UI or Claude-in-Chrome; reads and "
            "deletes still work.")
    if r.status_code not in (200, 201):
        die(f"announce failed: {r.status_code} {r.text[:300]}")
    nid = r.json().get("Id")
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/news/{nid}")
    if got.get("Title") != title:
        die(f"announcement verify failed for id {nid}")
    print(f"OK: announcement {nid} verified")


def cmd_validate(bs, args):
    import manifest as mf
    man, base = mf.load_manifest(args.manifest)
    errors, warnings, stats = mf.validate(man, base, args.profile)
    ok = mf.print_report(errors, warnings, stats)
    sys.exit(0 if ok else 1)


def cmd_apply(bs, args):
    import manifest as mf
    man, base = mf.load_manifest(args.manifest)
    errors, warnings, stats = mf.validate(man, base, args.profile)
    if not mf.print_report(errors, warnings, stats):
        die("manifest failed validation — nothing was attempted")
    ou = args.ou or str(man.get("course", {}).get("ou") or "")
    if not ou:
        die("no target: pass --ou or set course.ou in the manifest")
    ops = mf.build_ops(man, base)

    # existing state, for idempotency-by-title
    existing_topics = {}   # module title -> set of child titles
    module_ids = {}
    for depth, kind, oid, title, _ in walk_content(bs, ou):
        if kind == "module":
            module_ids[title] = oid
            existing_topics.setdefault(title, set())
    for mtitle, mid in module_ids.items():
        existing_topics[mtitle] = {
            t.get("Title") for t in module_structure(bs, ou, mid)}
    r = bs.get(f"/d2l/api/le/{LE}/{ou}/dropbox/folders/", ok=None)
    existing_assign = {f.get("Name") for f in r.json()} \
        if r.status_code == 200 else set()
    r = bs.get(f"/d2l/api/le/{LE}/{ou}/news/", ok=None)
    existing_news = {n.get("Title") for n in r.json()} \
        if r.status_code == 200 else set()

    def exists(op):
        if op["op"] == "manual":
            return None  # neither create nor skip — a flagged manual step
        if op["op"] == "module":
            return op["title"] in module_ids
        if op["op"] in ("page", "file", "video"):
            return op["title"] in existing_topics.get(op["module"], set())
        if op["op"] == "assignment":
            return op["title"] in existing_assign
        if op["op"] == "announce":
            return op["title"] in existing_news
        return False  # quiz imports always run (job-based)

    todo = []
    print(f"\nApply plan for ou={ou} on {HOST}:")
    for op in ops:
        if op["op"] == "manual":
            print(f"  MANUAL announce   {op['title']} ({op['note']})")
            continue
        skip = exists(op)
        mark = "SKIP  " if skip else "CREATE"
        where = f" -> {op.get('module')}" if op.get("module") else ""
        print(f"  {mark} {op['op']:<10} {op['title']}{where}")
        if not skip:
            todo.append(op)
    if not todo:
        print("\nNothing to do — course already matches the manifest.")
        return
    if not guard_execute(args):
        return

    org_code = get_org_code(bs, ou)
    for op in todo:
        kind = op["op"]
        if kind == "module":
            mid, _ = ensure_module(bs, ou, op["title"])
            module_ids[op["title"]] = mid
            print(f"  OK module '{op['title']}' (id {mid})")
        elif kind in ("page", "file", "video"):
            mid, _ = ensure_module(bs, ou, op["module"])
            tid = upload_file_topic(bs, ou, mid, org_code, op["title"],
                                    op["file"])
            print(f"  OK {kind} '{op['title']}' (topic {tid})")
            if kind == "video" and op.get("captions"):
                cid = upload_file_topic(
                    bs, ou, mid, org_code,
                    f"{op['title']} — captions (vtt)", op["captions"])
                print(f"  OK captions (topic {cid})")
        elif kind == "quiz":
            qargs = argparse.Namespace(
                ou=ou, qti=str(op["qti"]), title=op["title"],
                module=op["module"], execute=True, tag=None,
                i_mean_production=args.i_mean_production)
            cmd_quiz_import(bs, qargs)
        elif kind == "assignment":
            aargs = argparse.Namespace(
                ou=ou, title=op["title"], due=op["due"],
                out_of=op["out_of"], instructions=op["instructions"],
                instructions_file=None, hidden=op["hidden"],
                execute=True, tag=None,
                i_mean_production=args.i_mean_production)
            cmd_assignment(bs, aargs)
        elif kind == "announce":
            nargs = argparse.Namespace(
                ou=ou, title=op["title"], text=op["html"], html_file=None,
                start=op["start"], draft=op["draft"], pin=op["pin"],
                execute=True, tag=None,
                i_mean_production=args.i_mean_production)
            cmd_announce(bs, nargs)
    print("\nApply complete. Re-run `map` to see the resulting structure.")


def cmd_module(bs, args):
    titles = [tagged(t, args) for t in args.title]
    print(f"Plan: ensure {len(titles)} module(s) exist in ou={args.ou} "
          f"on {HOST}:")
    for t in titles:
        print(f"  ▸ {t}")
    if not guard_execute(args):
        return
    for t in titles:
        mid, created = ensure_module(bs, args.ou, t)
        print(f"  {'created' if created else 'exists '} {t} (id {mid})")


def cmd_rm_module(bs, args):
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/content/modules/{args.id}")
    print(f"Plan: DELETE module {args.id} '{got.get('Title')}' "
          f"from ou={args.ou} on {HOST}")
    if not guard_execute(args):
        return
    bs.delete(f"/d2l/api/le/{LE}/{args.ou}/content/modules/{args.id}")
    r = bs.get(f"/d2l/api/le/{LE}/{args.ou}/content/modules/{args.id}",
               ok=None)
    if r.status_code == 200:
        die(f"module {args.id} still present after delete")
    print(f"OK: module {args.id} deleted")


# -------------------------------------------------------------------- cli

def build_parser():
    ap = argparse.ArgumentParser(prog="bscourse", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, write=True):
        p.add_argument("--ou", required=True, help="course org unit id")
        if write:
            p.add_argument("--execute", action="store_true")
            p.add_argument("--i-mean-production", action="store_true")
            p.add_argument("--tag", default=None,
                           help="suffix created titles with [tag] "
                                "(test runs: bstest-<id>)")

    p = sub.add_parser("map", help="show course structure")
    common(p, write=False)
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(fn=cmd_map, verbose=False)

    p = sub.add_parser("setup", help="copy components from a template course")
    common(p)
    p.add_argument("--source", required=True,
                   help="template course ou to copy FROM")
    p.add_argument("--components", default=None,
                   help="comma list (Content,Quizzes,Dropbox,Grades,"
                        "Rubrics,News,…); omit = everything")
    p.add_argument("--offset-days", type=int, default=None)
    p.set_defaults(fn=cmd_setup)

    for name, fn, extra in (("syllabus", cmd_syllabus, "Syllabus"),
                            ("upload", cmd_upload, None),
                            ("page", cmd_page, None)):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--file", required=True)
        p.add_argument("--module", default=extra or "Course Materials")
        p.add_argument("--title", default=None)
        p.add_argument("--description", default=None)
        p.set_defaults(fn=fn)

    p = sub.add_parser("video", help="upload video + captions")
    common(p)
    p.add_argument("--file", required=True)
    p.add_argument("--captions", default=None, help=".vtt file")
    p.add_argument("--module", required=True)
    p.add_argument("--title", default=None)
    p.add_argument("--description", default=None)
    p.set_defaults(fn=cmd_video)

    p = sub.add_parser("assignment", help="create a dropbox assignment")
    common(p)
    p.add_argument("--title", required=True)
    p.add_argument("--due", default=None,
                   help="UTC ISO-8601, e.g. 2026-09-05T04:59:00.000Z")
    p.add_argument("--out-of", type=float, default=None)
    p.add_argument("--instructions", default=None)
    p.add_argument("--instructions-file", default=None)
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(fn=cmd_assignment)

    p = sub.add_parser("quiz-import", help="import QTI quiz package")
    common(p)
    p.add_argument("--qti", required=True, help="QTI/D2L package .zip")
    p.add_argument("--title", default=None,
                   help="expected quiz name (for verify + linking)")
    p.add_argument("--module", default=None,
                   help="module to place a quiz link topic in")
    p.set_defaults(fn=cmd_quiz_import)

    p = sub.add_parser("quiz-publish",
                       help="quiz.json -> QTI -> import -> settings -> link")
    common(p)
    p.add_argument("--quiz-json", required=True,
                   help="quiz spec (references/quiz-format.md)")
    p.add_argument("--module", default=None,
                   help="module to place the quiz link topic in")
    p.set_defaults(fn=cmd_quiz_publish)

    p = sub.add_parser("rm-quiz", help="delete a quiz (cleanup)")
    common(p)
    p.add_argument("--id", required=True, type=int)
    p.set_defaults(fn=cmd_rm_quiz)

    p = sub.add_parser("announce", help="post an announcement")
    common(p)
    p.add_argument("--title", required=True)
    p.add_argument("--text", default=None, help="HTML body inline")
    p.add_argument("--html-file", default=None)
    p.add_argument("--start", default=None,
                   help="future UTC ISO-8601 => scheduled")
    p.add_argument("--draft", action="store_true")
    p.add_argument("--pin", action="store_true")
    p.set_defaults(fn=cmd_announce)

    p = sub.add_parser("validate",
                       help="check a course.json for completeness (no auth)")
    p.add_argument("manifest")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "none", "plain", "ccc"],
                   help="page-check strictness; 'auto' reads "
                        "course.template (default none)")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("apply",
                       help="validate a course.json then build it")
    p.add_argument("manifest")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "none", "plain", "ccc"],
                   help="page-check strictness; 'auto' reads "
                        "course.template (default none)")
    p.add_argument("--ou", default=None,
                   help="target course (overrides manifest course.ou)")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--i-mean-production", action="store_true")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("module", help="create module(s) if missing")
    common(p)
    p.add_argument("--title", required=True, nargs="+",
                   help="one or more module titles")
    p.set_defaults(fn=cmd_module)

    p = sub.add_parser("rm-module", help="delete a module (test cleanup)")
    common(p)
    p.add_argument("--id", required=True, type=int)
    p.set_defaults(fn=cmd_rm_module)

    return ap


class LazyBS:
    """Defer auth until the first real API call, so dry-run plans for
    file-based verbs print without needing a live session."""

    def __init__(self):
        self._bs = None

    def __getattr__(self, name):
        if self._bs is None:
            self._bs = BS()
        return getattr(self._bs, name)


def main():
    args = build_parser().parse_args()
    args.fn(LazyBS(), args)


if __name__ == "__main__":
    main()
