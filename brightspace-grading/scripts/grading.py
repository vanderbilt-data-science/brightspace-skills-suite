#!/usr/bin/env python3
"""Brightspace grading workbench: pull submissions, push draft feedback.

Shares the brightspace-course auth/client (installed as a sibling skill).

  grading.py folders --ou N                     assignment folders + counts
  grading.py submissions --ou N --folder F      who submitted what, when
  grading.py pull --ou N --folder F [--dest D]  download files + metadata
  grading.py feedback --ou N --folder F --user U --score S
             (--html f | --text "...") [--publish]
  grading.py status --ou N --folder F           feedback coverage report

Safety model:
  - feedback lands as DRAFT (IsGraded=false, invisible to students)
    unless --publish is passed; never pass --publish without the user
    having reviewed and approved the batch.
  - every push is verified by GET read-back; the RichText-shape
    silent-drop trap is detected (text compared, not status codes).
"""

import argparse
import json
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here.parent.parent / "brightspace-course/scripts"))
from bsapi import BS, LE, die  # noqa: E402


def get_folder(bs, ou, folder_id):
    return bs.jget(f"/d2l/api/le/{LE}/{ou}/dropbox/folders/{folder_id}")


def list_submissions(bs, ou, folder_id):
    return bs.jget(f"/d2l/api/le/{LE}/{ou}/dropbox/folders/{folder_id}"
                   "/submissions/?activeOnly=true")


def cmd_folders(bs, args):
    for f in bs.jget(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/"):
        counts = (f" — {f.get('TotalUsersWithSubmissions', '?')}/"
                  f"{f.get('TotalUsers', '?')} submitted, "
                  f"{f.get('TotalUsersWithFeedback', '?')} have feedback"
                  if f.get("TotalUsers", -1) != -1 else "")
        print(f"  folder={f.get('Id'):<8} {f.get('Name')}"
              f" (due {f.get('DueDate')}){counts}")


def _entities(data):
    return data if isinstance(data, list) else data.get("Objects", [])


def cmd_submissions(bs, args):
    for e in _entities(list_submissions(bs, args.ou, args.folder)):
        ent = e.get("Entity", {})
        uid = ent.get("EntityId") or ent.get("Id")
        name = ent.get("DisplayName") or ent.get("Name")
        status = e.get("Status")
        fb = "feedback:yes" if e.get("Feedback") else "feedback:no"
        subs = e.get("Submissions", [])
        files = sum(len(s.get("Files", [])) for s in subs)
        latest = max((s.get("SubmissionDate") or "" for s in subs),
                     default="")
        print(f"  user={uid:<10} {name:<28} status={status} "
              f"files={files} latest={latest[:16]} {fb}")


def cmd_pull(bs, args):
    dest = Path(args.dest or f"submissions-ou{args.ou}-f{args.folder}")
    dest.mkdir(parents=True, exist_ok=True)
    meta = {"ou": args.ou, "folder": args.folder, "entities": []}
    folder = get_folder(bs, args.ou, args.folder)
    meta["folder_name"] = folder.get("Name")
    meta["out_of"] = (folder.get("Assessment") or {}).get(
        "ScoreDenominator")
    n_files = 0
    for e in _entities(list_submissions(bs, args.ou, args.folder)):
        ent = e.get("Entity", {})
        uid = ent.get("EntityId") or ent.get("Id")
        name = (ent.get("DisplayName") or ent.get("Name")
                or str(uid)).replace("/", "_")
        erec = {"user_id": uid, "name": name, "files": [],
                "status": e.get("Status"),
                "has_feedback": bool(e.get("Feedback"))}
        udir = dest / f"{name}-{uid}"
        for s in e.get("Submissions", []):
            sid = s.get("Id")
            for f in s.get("Files", []):
                fid, fname = f.get("FileId"), f.get("FileName")
                udir.mkdir(parents=True, exist_ok=True)
                r = bs.get(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/"
                           f"{args.folder}/submissions/{sid}/files/{fid}")
                out = udir / fname
                out.write_bytes(r.content)
                erec["files"].append(str(out.relative_to(dest)))
                n_files += 1
        meta["entities"].append(erec)
    (dest / "submissions.json").write_text(json.dumps(meta, indent=1))
    submitted = sum(1 for e in meta["entities"] if e["files"])
    print(f"OK: {submitted} submitters, {n_files} files -> {dest}/ "
          "(submissions.json holds the metadata)")


def cmd_feedback(bs, args):
    if args.html:
        html = Path(args.html).read_text()
    elif args.text:
        html = f"<p>{args.text}</p>"
    else:
        die("provide --html <file> or --text")
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    folder = get_folder(bs, args.ou, args.folder)
    out_of = (folder.get("Assessment") or {}).get("ScoreDenominator")
    if args.score is not None and out_of and args.score > out_of:
        die(f"score {args.score} exceeds folder out-of {out_of}")
    state = "PUBLISHED (student-visible)" if args.publish else \
        "DRAFT (invisible to student)"
    print(f"Plan: {state} feedback for user {args.user} on "
          f"'{folder.get('Name')}' (folder {args.folder}), "
          f"score {args.score}/{out_of}")
    if not args.execute:
        print("\nDRY RUN — nothing was sent. Re-run with --execute "
              "(feedback pushes require prior user approval of the "
              "batch; --publish additionally requires it explicitly).")
        return
    path = (f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/{args.folder}"
            f"/feedback/user/{args.user}")
    # docs declare RichText {Text, Html} here (anomalous); silent-drop
    # trap documented — verify by read-back and fall back if empty.
    body = {"Score": args.score, "Feedback": {"Text": text, "Html": html},
            "RubricAssessments": [], "IsGraded": bool(args.publish),
            "GradedSymbol": None}
    bs.post(path, json=body)
    got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/"
                  f"{args.folder}/feedback/user/{args.user}")
    landed = ((got.get("Feedback") or {}).get("Text") or "").strip()
    if not landed:
        print("  read-back EMPTY with RichText shape — retrying with "
              "RichTextInput …")
        body["Feedback"] = {"Content": html, "Type": "Html"}
        bs.post(path, json=body)
        got = bs.jget(f"/d2l/api/le/{LE}/{args.ou}/dropbox/folders/"
                      f"{args.folder}/feedback/user/{args.user}")
        landed = ((got.get("Feedback") or {}).get("Text") or "").strip()
    if not landed:
        die("feedback did not land (both rich-text shapes read back "
            "empty) — do not trust the 200s; investigate before batch "
            "grading")
    if args.score is not None and got.get("Score") != args.score:
        die(f"score read-back {got.get('Score')} != {args.score}")
    print(f"OK: feedback verified for user {args.user} "
          f"(score {got.get('Score')}, {state.split()[0]})")


def cmd_status(bs, args):
    total = with_fb = published = 0
    for e in _entities(list_submissions(bs, args.ou, args.folder)):
        if not e.get("Submissions"):
            continue
        total += 1
        fb = e.get("Feedback")
        if fb:
            with_fb += 1
            if fb.get("IsGraded"):
                published += 1
    print(f"folder {args.folder}: {total} submitters, {with_fb} with "
          f"feedback ({published} published, {with_fb - published} draft), "
          f"{total - with_fb} ungraded")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--ou", required=True)

    p = sub.add_parser("folders")
    common(p)
    p.set_defaults(fn=cmd_folders)
    for name, fn in (("submissions", cmd_submissions),
                     ("status", cmd_status)):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--folder", required=True, type=int)
        p.set_defaults(fn=fn)
    p = sub.add_parser("pull")
    common(p)
    p.add_argument("--folder", required=True, type=int)
    p.add_argument("--dest", default=None)
    p.set_defaults(fn=cmd_pull)
    p = sub.add_parser("feedback")
    common(p)
    p.add_argument("--folder", required=True, type=int)
    p.add_argument("--user", required=True, type=int)
    p.add_argument("--score", type=float, default=None)
    p.add_argument("--html", default=None)
    p.add_argument("--text", default=None)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.set_defaults(fn=cmd_feedback)

    args = ap.parse_args()
    args.fn(BS(), args)


if __name__ == "__main__":
    main()
