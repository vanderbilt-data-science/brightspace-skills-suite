---
name: brightspace-course
description: Design and build a Brightspace (D2L) course - brand new, copied from a previous course, or from a template (e.g. the CCC Online Programs page kit) - with guidance on structure and best practices. Covers the course.json manifest pipeline (map -> validate -> apply), CCC-styled pages (syllabus, module overviews, lessons), assignment creation, the quiz pipeline (quiz.json -> QTI -> import -> settings), and the rubric pipeline (rubric.json -> preview -> UI entry -> API verify). Use for "set up my course", "build the Brightspace course for X", "copy last year's course", "make it follow the CCC template", "create the quizzes", "make a rubric", or any course DESIGN work. Always opens by asking for the course URL, opening that tenant in the browser for the user to log in, and confirming whose account it landed on - then asks whether the course should follow a template or be modeled on a previous course. Day-to-day upkeep of a running course is brightspace-manage; grading submissions is brightspace-grading. Writes are dry-run by default.
---

# Brightspace Course Design & Creation

Part of the Brightspace suite: **this skill designs and builds courses**;
`brightspace-manage` runs them day-to-day; `brightspace-grading` pulls
and grades submissions. All three share this skill's engine
(`scripts/bsapi.py`) and capability map.

One skill for the whole course lifecycle: **setup from template → syllabus →
assignments → assessments → videos → notes → announcements**, with every
write dry-run first, verified by read-back, and guarded on production.

Scripts live in `scripts/` (`bsapi.py` = auth + client, `bscourse.py` = the
verbs). They need only Python 3 + `requests` (auto-installed).

## Data handling — FERPA / VU Level 3 (non-negotiable)

Claude is **not approved for Vanderbilt Level 3 (Restricted) data**, which
includes FERPA student education records: any student identity coupled
with grades, scores, submissions, or enrollment. Course *design* needs
none of that — keep it that way:

- Never call classlist, enrollment-of-others, grades-of-students, or
  submission endpoints, and never read Classlist/Grades/submission pages
  via browser tools, even when convenient for a side question.
- If a task drifts toward student data ("who submitted", "grade this"),
  stop and route it to the reviewed workflow — don't improvise it here.
- Credentials are secrets: never print a token, never inline one in a
  shell command (see `references/chrome-auth.md` for the safe forms).

## Safety rules (non-negotiable)

1. **Dry-run is the default.** Every write command prints its plan and exits
   unless `--execute` is passed. Show the plan to the user before executing.
2. **Production needs explicit intent.** On `brightspace.vanderbilt.edu`,
   `--execute` also requires `--i-mean-production`. Never pass it without
   the user confirming in this conversation. Prefer the test tenant
   (`BRIGHTSPACE_HOST=<test-host>`).
3. **200 ≠ landed.** Every write is verified by an independent GET
   read-back. Trust the read-back the scripts print, not the status code.
4. **Never PUT what you haven't GET.** Brightspace PUT treats missing
   fields as deletions. The scripts only POST-create; if you extend them
   with updates: GET → modify → PUT the whole object.
5. **Tag test artifacts.** When testing, pass `--tag bstest-<runid>` so
   everything created is findable and removable.

## Step 0 — the opening move (before any design talk)

When the user asks for anything course-building — *"help me build out a
course in Brightspace"*, *"set up my fall course"*, *"copy last year's"* —
**open with the URL question and get them logged in first.** The URL alone
resolves the tenant *and* the course with no auth and no API call, and
everything downstream (`doctor`, `courses`, every verb) needs a live token
anyway.

1. **Ask for the course URL.** "Open the course in Brightspace and paste
   the URL from your address bar." If the shell doesn't exist yet, ask for
   the tenant host instead and find the ou later with `bsapi.py courses`.

2. **Parse host + ou from it.** The ou is the numeric id:

   | URL shape | ou |
   |---|---|
   | `https://<host>/d2l/home/12345` | `12345` |
   | `https://<host>/d2l/le/content/12345/home` | `12345` |
   | `https://<host>/d2l/lms/…?ou=12345` | `12345` (query param) |
   | `https://<host>/d2l/home` | none — tenant only |

   In practice: the first run of digits after `/d2l/home/` or
   `/d2l/le/content/`, else an `ou=` query param. **Echo back what you
   parsed** ("tenant `<host>`, course ou `12345`") so they can correct it.
   Non-default tenant → `export BRIGHTSPACE_HOST=<host>` before any command.

3. **Check whether you even need a login** — `bsapi.py doctor`. Exit 0
   means a cached token is still live: **skip to step 6**, no browser and
   no SSO needed. Exit 3 = auth stale or absent, continue to step 4. Exit
   2 = tenant unreachable, which no amount of logging in will fix (see
   the sandbox note below). Don't drag the user through Duo for a session
   you already have.

4. **Open that tenant in the Browser pane and let the user log in.**
   `preview_start` on `https://<host>/d2l/home`, then **wait for them to
   complete SSO + Duo themselves** — never type credentials, never touch
   the password fields. Poll until the tab settles on `/d2l/home`. It may
   land instantly with no prompt (an existing SSO session is silently
   re-admitted) — that's fine; a live session is all you need.

5. **Mint and cache the token** per `references/chrome-auth.md`, then
   `bsapi.py whoami`. **Read the name back to the user** — it's the
   cheapest guard against building into the wrong person's course.

6. **Name the course back to them.** `bsapi.py courses`, match the ou from
   step 2, and confirm: *"building into Intro to Data Science, Fall 2026 —
   right?"* Production rules apply on `brightspace.vanderbilt.edu`.

Then move to **First questions** below. Sketching structure before you have
a token is fine — but don't run a command that touches the tenant until
`whoami` has printed a name.

## Install & auth — minimal, no Playwright required

**Install footprint: Python 3 + `requests` (auto-installed). Nothing
else for the normal path** — no OAuth app, no admin, no browser driver.
Full breakdown and the "do we need Playwright?" / "does it run in Cowork?"
analysis: `references/install-and-auth.md`.

The tenant mints a ~1h full-scope JWT to any logged-in browser session.
`bsapi.py` looks for, in order: `BRIGHTSPACE_TOKEN` env → cached token
(<50 min) → `storage_state.json` cookies. Get a token by (best first):

1. **Desktop Browser pane mints it (smoothest; verified 2026-08-21):** in
   Claude Code on Desktop, open the tenant in the built-in Browser pane,
   let the user do SSO + Duo there, run the mint JS in that page, cache
   via a temp file into `save-token` (never inline the token in a shell
   command) — full steps in `references/chrome-auth.md`.
2. **Paste one (universal, zero tooling):** user runs the two-line fetch
   in their Brightspace tab's DevTools console (in
   `references/chrome-auth.md`), Claude saves it via stdin-from-file.
   (The Claude-in-Chrome *extension* currently redacts JWT results, so on
   that surface use this paste path or the Desktop pane.)
3. **Import from a browser profile:** `python3 scripts/bsapi.py
   import-cookies safari|firefox|edge` — pure code, durable for days.
   (Chrome v127+ App-Bound Encryption blocks this; use another browser
   you're logged in to, or path 1/2.)
4. **Playwright login — only for headless/scheduled runs** (no human
   present): `approaches/playwright-skill/scripts/login.py` saves cookies
   that refresh unattended for days–weeks. Skip it entirely for
   interactive use.

**The preflight (Step 0 · step 3) — the first command that touches the
tenant, in any new environment:**

```bash
python3 scripts/bsapi.py doctor      # network first, then auth
python3 scripts/bsapi.py courses     # find the target ou id
```

`doctor` separates the two failure classes so you never chase the wrong
one: exit 2 = **tenant unreachable** (a sandbox blocks egress — no token
work will help; see below), exit 3 = network fine but **auth stale/absent**
(fix with any token path above), exit 0 = ready.

**If doctor reports the tenant unreachable (exit 2):** you are in a
sandboxed runtime — Claude Cowork and claude.ai execute code in a cloud VM
behind an egress-allowlist proxy that does not include the tenant. Do NOT
retry or fiddle with tokens; tell the user plainly: run this task in
**Claude Code** (terminal, or Claude Code inside the Claude Desktop app),
which executes on their own machine and reaches the tenant; or an org
admin can allowlist the tenant host under Admin Console → Organization
Settings → Capabilities → Code Execution → Allow Network Egress (mode
must be "All domains" — a known bug ignores extra domains in "Package
managers only" mode; takes effect in new sessions only).

Expired-session symptoms: `401` mid-run, or "empty referrerToken" (the
XSRF endpoint returns HTTP 200 with an empty token when cookies expired).
Fix by re-obtaining a token (any path above).

Non-default tenant: `export BRIGHTSPACE_HOST=<host>` before any command.

## First questions — ask before designing anything

Before proposing structure or writing a single manifest line, ask the
user explicitly (don't assume, even if the request seems clear):

1. **"Is there a template or an existing course this should be modeled
   after?"** The three common answers:
   - **A program template / page kit** (e.g. the CCC Online Programs
     kit): use `setup` from the template course and/or the kit under
     `assets/`, per `references/template-setup.md`.
   - **A previous course of theirs** (last year's offering, a colleague's
     master): confirm which one (`bsapi.py courses` to find the ou), then
     `setup --source <ou> --offset-days <n>`. Ask what should carry over
     (structure only? quizzes? rubrics?) and what gets new content.
   - **Neither — building fresh** (often adapting in-person materials):
     go manifest-first, and ask whether they want the `plain` page kit,
     `ccc`, or unstyled pages.
2. **"Which course shell are we building into?"** — normally already
   answered by the URL from Step 0. Confirm the ou *by name* (from
   `bsapi.py courses`, not just the number) and that it's not the live
   student-facing course (production rules apply).

Copying structure from a previous course is the *safe* reuse path —
Course Copy moves content and settings, never student records. If they
answer "model it on last year's" with new content, the usual shape is:
`setup` copy → strip/replace per-week content via the manifest → roll
dates forward.

## The workflow: map → validate → apply

For anything bigger than a one-off, **don't upload piecemeal**. Map the
source material into a `course.json` (schema:
`references/course-manifest.md`), then:

```bash
python3 scripts/bscourse.py validate course.json     # completeness BEFORE upload
python3 scripts/bscourse.py apply course.json --ou N            # dry-run plan
python3 scripts/bscourse.py apply course.json --ou N --execute  # build, verified
```

`validate` needs no auth and reports what's missing (files, placeholders,
due dates, CCC-kit conformance, module-overview coverage) while it's still
cheap to fix. `apply` is idempotent by title — re-running after adding
material only creates what's new. Consult
`references/capability-map.md` for what Brightspace can/can't do and the
workaround when a capability is UI-only or broken (it also carries
live-probed tenant bugs, e.g. announcements create currently 500s).

## The verbs

Single operations, used directly or by `apply`. Always confirm the target
`--ou` with the user (`bsapi.py courses`), run the dry-run, show the
plan, then `--execute`.

### See what a course looks like

```bash
python3 scripts/bscourse.py map --ou 12345 -v
```

Full module/topic tree plus quiz, assignment, and announcement counts.
Use this to document a template course and to verify results after writes.

### Set up a course from a template

```bash
python3 scripts/bscourse.py setup --ou <DEST> --source <TEMPLATE_OU> \
    [--components Content,Quizzes,Dropbox,News] [--offset-days 365] --execute
```

Runs a Course Copy job (async; polled to completion) and prints the
destination tree afterward. Omit `--components` to copy everything —
including things the REST API cannot create directly (rubrics, quiz
questions, navbars), which is why template-copy is the backbone of course
setup. `--offset-days` shifts all dates (new semester = usually 365).

Note: `setup` copies from an *existing course* (last year's offering, a
master, or a template course). It's independent of the page-template
choice above — copy a prior course whatever its style, or start empty and
author pages from `plain`/`ccc`/none. For CCC programs specifically, the
kit is a **page-design kit** (`assets/ccc-templates/`) with a per-module
rhythm — see `references/template-setup.md`.

**Copy rules (the classic Brightspace copy mishaps, prevented):**

- **Copy into a shell ONCE.** Course Copy is not idempotent — re-running
  it duplicates every module, topic, and grade item, and cleanup is
  manual. If something's missing after a copy, add it via the manifest
  or verbs; never re-run `setup` into the same shell. Before any copy,
  `map` the destination — if it isn't empty, stop and confirm with the
  user.
- **Leave old announcements behind.** Copying `News` brings last term's
  announcements, which can post immediately and confuse students. Omit
  `News` from `--components` unless the user explicitly wants them.
- **Then audit.** After the copy job completes, run the post-copy audit
  below before calling it done.

**Post-copy / post-build audit (always):**

1. `map --ou <dest> -v` — the tree now marks `HIDDEN`/locked items and
   start/end/due dates, and flags the hidden-item count. Check: did all
   dates roll (offset applied, nothing left in last year)? Anything
   unexpectedly hidden that students will need? Stale announcements
   (count shows in the summary)?
2. Items with **no** dates don't get offset (nothing to shift) — scan
   for assignments/quizzes that *should* have due dates but don't.
3. Have the user spot-check in **View as Student** (Brightspace's
   preview) — it won't show date-restricted items, so pair it with the
   map flags rather than trusting it alone.

### Syllabus, notes, pages, any file

```bash
python3 scripts/bscourse.py syllabus --ou 12345 --file syllabus.pdf --execute
python3 scripts/bscourse.py upload   --ou 12345 --file week3-notes.pdf \
    --module "Week 3" --execute
python3 scripts/bscourse.py page     --ou 12345 --file overview.html \
    --module "Week 3" --title "Week 3 Overview" --execute
```

Modules are created if missing (matched by exact title anywhere in the
tree). `syllabus` defaults to a module named "Syllabus" — override
`--module` to match the template's section (check `map` first).

**Authoring pages — pick a template (or none):** a course chooses a page
look once via `course.template` — `none` (default; raw clean HTML),
`plain` (neutral unbranded kit, `assets/plain-templates/`), `ccc` (the
Vanderbilt CCC Online Programs kit, `assets/ccc-templates/`), or a custom
kit path. Copy the matching template file, fill every `[placeholder]`,
publish with `page`. **CCC is optional** — only for CCC programs. Full
comparison and authoring steps: `references/page-templates.md`; the CCC
kit specifics: `references/template-setup.md`.

### Videos (+ captions)

```bash
python3 scripts/bscourse.py video --ou 12345 --module "Week 3" \
    --file seg1.mp4 --captions seg1.vtt --title "3.1 Intro to X" --execute
```

Simple upload holds to ~400MB/file; segment longer recordings (the
`course-video-prep` skill produces conforming segments+captions, and the
`brightspace-video-module-publish` skill bulk-publishes a whole prepared package —
prefer it for full weekly packages; use `video` for one-offs).

### Assignments

```bash
python3 scripts/bscourse.py assignment --ou 12345 --title "Homework 3" \
    --due 2026-09-05T04:59:00.000Z --out-of 100 \
    --instructions-file hw3.html --execute
```

Creates an individual file-submission dropbox folder, verified by
read-back including the due date. Due dates are **UTC** ISO-8601 — convert
from the course timezone (Central: add 5h in CDT / 6h in CST; 11:59pm CT ≈
04:59/05:59Z next day). Grade-item linking: create the grade item first,
then extend with `GradeItemId` (see `references/api-quickref.md`).

### Assessments / quizzes — the full pipeline

```bash
python3 scripts/qti.py --validate quiz.json          # completeness gate
python3 scripts/bscourse.py quiz-publish --ou 12345 \
    --quiz-json quiz.json --module "Module 2" --execute
```

Author questions + settings as `quiz.json`
(`references/quiz-format.md`), show the drafted questions to the user,
then one command does: QTI generation → import job (questions cannot be
created via REST — 405 everywhere; import is the only path) → settings
via the quiz-shell PUT (dates, attempts, time limit, shuffle, grade
linkage, active flag — all API) → link topic in the module → verify
question count + settings. `rm-quiz` cleans up. Raw packages from other
tools still import via `quiz-import`. Only pools/sections and per-question
edits need the UI.

### Rubrics — intermediate format, UI entry, API verify

```bash
python3 scripts/rubric.py validate rubric.json
python3 scripts/rubric.py preview rubric.json     # show the user, get OK
python3 scripts/rubric.py entry-plan rubric.json  # exact UI steps
python3 scripts/rubric.py verify rubric.json --ou 12345
```

Rubric creation/attachment has **no API**: author `rubric.json`
(`references/rubric-format.md`, with authoring guidance and what to ask
the user), validate, preview for approval, then drive the UI from the
entry plan via Claude-in-Chrome (or hand it to the user), and finally
**verify by API read-back** that the rubric sits on its target
assignments. Alternative: keep rubrics in a master course and copy them
with `setup --components Rubrics,Dropbox`.

### Announcements

```bash
python3 scripts/bscourse.py announce --ou 12345 --title "Welcome!" \
    --html-file welcome.html --execute
# schedule for later: --start 2026-08-24T13:00:00.000Z
```

### Cleanup (test runs)

```bash
python3 scripts/bscourse.py rm-module --ou 12345 --id 67890 --execute
```

## Browser fallback (the UI-only tail)

A few operations have **no API**: rubric creation, quiz question editing /
settings beyond the shell, Intelligent Agents, some grade-scheme setup.
Order of preference:

1. **Get it from the template** — `setup` copies rubrics, quizzes,
   navbars, etc. wholesale. Design templates so the UI-only artifacts
   already exist in them.
2. **Claude-in-Chrome** — drive the real UI in the user's own logged-in
   Chrome tab for the remaining one-offs (needs site permission for the
   Brightspace domain in the extension).
3. Tell the user exactly what to click if neither is available.

## Companion skills

- `course-video-prep` — turn a Zoom recording into segments + captions +
  QTI quizzes + manifest.
- `brightspace-video-module-publish` — bulk-publish such a package as a content module
  (same auth, same safety rules).
