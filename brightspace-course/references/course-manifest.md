# course.json — the intermediate course model

The contract at the center of the workflow: **map source material into
this structure first, validate it for completeness, and only then touch
Brightspace.** Missing pieces surface as validator findings *before* any
upload, not as half-built courses.

```
source material (syllabus.md, schedule, recordings, QTI, ...)
        │  (Claude maps, using the CCC kit for pages)
        ▼
   course.json  ──►  bscourse.py validate <manifest>     ← gaps reported here
        │                                                   fix & re-validate
        ▼
   bscourse.py apply <manifest> --ou N            (dry-run plan)
   bscourse.py apply <manifest> --ou N --execute  (build, verified)
```

`apply` is **idempotent by title**: modules/topics/assignments/announcements
that already exist (exact title match) are skipped and reported, so
re-running after adding material only creates what's new.

## Schema (all paths relative to the manifest's directory)

```json
{
  "course": {
    "name": "AI 1010: Survey of Generative AI Tools and Applications",
    "term": "Fall 2026",
    "template": "none",          // none (default) | plain | ccc | custom:<path>
                                 //   → references/page-templates.md
    "ou": 644191,                // optional; --ou wins if both given
    "keep_inactive": true        // apply refuses to touch IsActive
  },
  "modules": [
    {
      "title": "Module 1: Orientation",
      "pages": [
        { "title": "Module 1 Overview",
          "file": "brightspace-pages/module-01-overview.html",
          "kit": "module-overview" }   // CCC kit type or "raw"
      ],
      "files":  [ { "title": "Slides Session 1", "file": "s1.pdf" } ],
      "videos": [ { "title": "3.1 Intro", "file": "v.mp4",
                    "captions": "v.vtt" } ],
      "quizzes": [ { "title": "Week 3 Quiz", "qti": "quiz3.zip",
                     "link_in_module": true } ]
    }
  ],
  "assignments": [
    { "title": "Lab 1: Prompt Refinement",
      "due": "2026-09-23T04:59:00.000Z",     // UTC ISO-8601
      "out_of": 100,
      "hidden": true,
      "instructions": "<p>inline html</p>",  // or "instructions_file"
      "grade_item": null }
  ],
  "announcements": [
    { "title": "Welcome to AI 1010!",
      "html_file": "brightspace-pages/welcome.html",  // or "text"
      "draft": true, "start": null, "pin": false }
  ]
}
```

## What `validate` checks

**Errors (block apply):** unreadable/missing referenced files; unresolved
`[placeholders]` in pages; pages declaring a CCC `kit` but missing the
shared template `<head>` assets; malformed/naive due dates; missing
required fields; duplicate titles within a scope; video files over the
simple-upload limit; QTI files that aren't zips; announcements with
neither `text` nor `html_file`.

**Warnings (report, don't block):** modules without an overview page;
assignments without instructions, due date, or points; due dates outside
the course term or on a listed no-class date (pass `no_class_dates` in
`course` to enable); quizzes never linked into a module; an empty module.

**Summary:** per-type counts and total upload size, so the plan is
legible before `apply` prints the operation list.

## Page template / validation profile

Page checks follow the course's `template` (see
`references/page-templates.md`): `none` (default — raw HTML, no house
style), `plain` (neutral kit), or `ccc` (Vanderbilt CCC kit; requires the
shared-asset `<head>` on kit pages). `validate`/`apply` read it
automatically; override with `--profile none|plain|ccc` for a one-off.
CCC is **optional** — a course that sets no `template` is never checked
against it.
