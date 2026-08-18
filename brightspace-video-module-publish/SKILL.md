---
name: brightspace-video-module-publish
description: Publish a prepared async course package (from the course-video-prep skill, or any directory with a conforming manifest.json) into a Brightspace (D2L) course as a content module - uploading videos and caption files, importing QTI quiz packages, creating description pages, and verifying every write by reading it back. Uses the instructor's saved SSO browser session (no OAuth app registration needed). Use whenever the user wants to upload course videos or quizzes to Brightspace, push a week's async module to the LMS, "publish the package", or asks to get prepared course content into brightspace.vanderbilt.edu or the D2L test tenant. Always dry-run first.
---

# Brightspace Publish

Take a package directory containing `manifest.json` (the contract produced by
`course-video-prep` — schema in that skill's `references/package-format.md`)
and make it exist in a Brightspace course: one content module holding the
overview page, the videos (with captions), and the quizzes, in manifest order.

## Safety rules (non-negotiable)

- **Dry-run is the default.** `publish.py` prints its full action plan and
  touches nothing unless `--execute` is passed.
- **Production requires explicit intent.** When the target host is
  `brightspace.vanderbilt.edu`, the script demands `--i-mean-production`.
  Confirm with the user before ever passing that flag. Prefer the test
  tenant during development.
- **200 is not success.** Brightspace sometimes returns 200 while silently
  dropping the body. Every write is verified by an independent GET
  (write-verify discipline from the brightspace lab's PLAN.md). Trust the
  read-back, not the status code.
- **Never PUT what you have not GET.** Brightspace PUT treats missing fields
  as deletions (this severed a live quiz-gradebook link once — the "q01
  incident"). The scripts only POST-create; if you extend them with updates,
  GET first, modify, PUT the whole object.

## Prerequisites

1. **A saved browser session.** This skill reuses the playwright-skill login
   at `~/.config/brightspace-skill/storage_state.json`. If it is missing or
   stale, run the login helper (interactive SSO + Duo, one time):
   ```bash
   python3 tools/login.py   # optional; see brightspace-course/references/install-and-auth.md
   ```
2. **Python `requests`** (the scripts auto-install it).
3. A validated package: run course-video-prep's `validate_package.py` first
   if there is any doubt.

## Workflow

### Step 1: Check auth and resolve the course

```bash
python3 <skill-path>/scripts/bs_session.py whoami
python3 <skill-path>/scripts/bs_session.py courses
```

`whoami` mints a short-lived (~1h) API token from the saved session cookies
and prints the logged-in user. **Known trap**: with expired cookies the XSRF
endpoint returns HTTP 200 with an *empty* token, not a 401 — the script
detects this and tells you to re-run login. `courses` lists enrollments with
their org unit ids (`ou`). Confirm the target `ou` with the user — course
names can be ambiguous across terms.

Non-default tenant: set `BRIGHTSPACE_HOST` (e.g. the test tenant hostname)
in the environment; the default is `brightspace.vanderbilt.edu`.

### Step 2: Dry run

```bash
python3 <skill-path>/scripts/publish.py <package-dir> --ou <ou>
```

Prints the numbered action plan (create module, upload N videos + captions,
import M quizzes, create overview page) with file sizes and estimated upload
time. Show this plan to the user and get their go-ahead.

### Step 3: Execute

```bash
python3 <skill-path>/scripts/publish.py <package-dir> --ou <ou> --execute
```

What it does, in order, verifying each step by read-back:
1. Creates the module (`POST .../content/root/`) titled from the manifest.
   If a module with the same title exists, it stops and asks — pass
   `--into-module <moduleId>` to add items to an existing module instead.
2. For each manifest item in order:
   - `html` -> uploads the file as an HTML topic in the module.
   - `video` -> uploads the mp4 as a file topic (multipart/mixed; files
     over ~400 MB automatically use the resumable upload protocol), then
     uploads the `.vtt` alongside it in the course content space.
   - `quiz` -> imports the QTI zip (`POST .../import/{ou}/imports/`),
     polls the job to completion, finds the created quiz by title, and adds
     a link topic pointing at it so it sits in the right module position.
3. Prints a verification table: each item, its Brightspace id, and its
   read-back status.

The run is resumable: `--skip-first N` skips already-completed items after a
partial failure (the verification table tells you N).

### Step 4: Report and the manual tail

Report the verification table to the user, plus the **known manual steps**
the API cannot do (be honest about these rather than pretending):

- **Caption attachment**: the vtt lands in the content space next to the
  video, but wiring it into the player's CC menu is UI-only in some D2L
  configurations. Verify one video in the browser; if captions are not
  offered, attach them via the topic's "Add Captions" UI (or ask this skill
  to do it with claude-in-chrome / Playwright).
- **Quiz settings**: QTI import creates questions reliably, but attempt
  limits, grade association, and availability dates usually need setting.
  The manifest's `grade` block says the intent (e.g. unlimited attempts,
  3 points, category "Quizzes"). Do these in the UI or via Playwright.
- **Module release conditions / dates** if the course uses them.

Read `references/api-notes.md` before debugging any API failure — it
distills the validated endpoint knowledge (routes, auth traps, upload
protocols, what has no API) from the brightspace research lab.

## When the API path fails

The fallback ladder, in order:
1. Re-mint the token (`bs_session.py whoami`) — 1h expiry is the most
   common failure.
2. Re-run the interactive login (session cookies expired).
3. Check `references/api-notes.md` for whether the capability is known to
   be UI-only; if so, drive the UI via claude-in-chrome or Playwright
   (the shared session helpers),
   reusing the same storage_state.
4. Worst case: the package is fully self-describing — walk the user through
   manual upload with a checklist generated from the manifest.

Never leave a half-published module silently: report exactly which items
landed and which did not.
