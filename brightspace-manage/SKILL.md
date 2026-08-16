---
name: brightspace-manage
description: Day-to-day management of a running Brightspace (D2L) course - post announcements, publish this week's notes/slides/videos, adjust due dates and availability, check who has submitted, view the roster, audit course structure, and keep content current through the semester. Use whenever the user wants to "tell the class", "post this week's materials", "move the deadline", "who hasn't submitted", "what's in my course", or any in-semester course upkeep on brightspace.vanderbilt.edu / D2L. For building a NEW course or authoring quizzes/rubrics/pages use brightspace-course (design); for grading submissions use brightspace-grading. Writes are dry-run by default.
---

# Brightspace Course Management (in-semester)

The running-course companion to `brightspace-course` (design/creation)
and `brightspace-grading` (assessment). Uses the same engine — all
commands live in `../brightspace-course/scripts/` (shared auth via
`bsapi.py`; same `BRIGHTSPACE_HOST`, dry-run, and production-flag
rules; capability limits in `../brightspace-course/references/
capability-map.md`).

```bash
BC=../brightspace-course/scripts   # relative to this skill directory
python3 $BC/bsapi.py whoami        # session check
python3 $BC/bsapi.py courses       # find the ou
```

## Everyday verbs

**What's in the course / audit:**
`python3 $BC/bscourse.py map --ou N -v`
Full module tree + quizzes, assignments (with due dates), announcements.

**Post this week's materials:**
`upload` (files/slides/notes), `page` (HTML pages — follow the CCC kit
via the design skill for new page types), `video` (+ `--captions`).
Modules are matched by exact title — check `map` first.

**Announcements:** `announce --ou N --title ... --html-file ...`
(`--start` schedules, `--draft` holds, `--pin` pins).
⚠ Current tenant bug: the news-create API 500s (probed 2026-08-16) — the
verb fails with guidance; fall back to posting via the UI or
Claude-in-Chrome, and re-try the verb after the next LMS monthly update.

**New assignment mid-semester:** `assignment --ou N --title ... --due ...
--out-of ... [--hidden]` (UTC dates — 11:59 p.m. Central = 04:59Z next
day in CDT, 05:59Z in CST).

**Who's in the class:** `bsapi.py` + classlist routes
(`/d2l/api/le/{v}/{ou}/classlist/`) — extend on demand.

**Who has submitted:** that's grading territory —
`python3 ../brightspace-grading/scripts/grading.py submissions --ou N
--folder F` (read-only, fine to use from here).

## Changing existing items (due dates, visibility, renames)

There are no update verbs yet — and Brightspace **PUT deletes omitted
fields**, so never hand-craft a partial PUT. The safe pattern (extend
`bscourse.py` with it when first needed):
1. GET the full object (folder, topic, module, quiz shell).
2. Change only the intended field on the full body (convert RichText →
   RichTextInput fields, strip read-only fields — see
   `../brightspace-course/references/api-quickref.md`).
3. PUT the whole object; GET again; compare the changed field.

Quiz setting changes: the design skill's `quiz-publish` transform shows
the exact GET→PUT conversion — reuse it.

## Visibility rules (in a live course)

- Course activation (`IsActive`) is never changed as a side effect.
- New content into a live course: create `--hidden` (or into a hidden
  module), let the instructor flip visibility in the UI or ask
  explicitly for it visible.
- Anything student-visible (announcement, unhiding, due-date change on a
  live assignment) → confirm with the instructor first, then verify by
  read-back and report what students now see.
