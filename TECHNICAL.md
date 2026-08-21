# Technical Guide

Everything needed to install, authenticate, and operate the Brightspace
Skills suite. The [README](README.md) is the plain-language overview for
instructors; this document is for whoever sets it up (or wants to see the
mechanics). The suite is provider-neutral Python driven by AI agents through
[Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview).

## Contents
- [What the skills are](#what-the-skills-are)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Requirements](#requirements)
- [Authentication](#authentication)
- [Installation per platform](#installation-per-platform)
- [Command reference & examples](#command-reference--examples)
- [Safety model](#safety-model)
- [What Brightspace can and cannot do](#what-brightspace-can-and-cannot-do)
- [Repository layout](#repository-layout)

---

## What the skills are

Each skill is a folder with a `SKILL.md` (the agent reads this to know when
and how to use it) plus Python scripts and reference docs.

| Skill | Job | Key scripts |
|---|---|---|
| **`brightspace-course`** | Design & build a course | `bsapi.py` (auth/client), `bscourse.py` (verbs), `qti.py` (quizzes), `rubric.py` (rubrics), `manifest.py` (the `course.json` pipeline) |
| **`course-video-prep`** | Zoom recording → segments, captions, quizzes | `segment_video.py`, `make_qti.py`, `validate_package.py` |
| **`brightspace-video-module-publish`** | Publish a prepared package as a content module | `bs_session.py`, `publish.py` |

All skills share one engine (`brightspace-course/scripts/bsapi.py`) and one
set of safety rules.

> **Held out pending privacy review:** two further skills —
> **`brightspace-manage`** (in-semester upkeep: announcements, deadlines,
> submission status) and **`brightspace-grading`** (pull submissions,
> AI-draft feedback, publish) — read student data, so they are excluded
> from `main` until a FERPA / VU data-classification review completes (see
> the FERPA-1…9 issues). They live on the
> [`student-data-skills`](../../tree/student-data-skills) branch. Do not
> deploy them against real student data until that review is done.

## How it works under the hood

Vanderbilt (like many schools) issues faculty no API credentials for
Brightspace. Instead, the scripts mint a short-lived (~1 hour) full-scope
API token from a browser session the instructor is already logged into
(the Valence `xsrf-tokens` → `oauth2/token` flow), then call the official
Valence REST API. No OAuth app registration, no admin rights, no browser
automation framework for interactive use. Everything the token can do is
exactly what the logged-in user could do in the GUI.

## Requirements

- **Python 3.9+** (present on macOS and in every agent runtime here).
- **`requests`** — auto-installed on first run (PEP-668-aware).
- Everything else is Python standard library.
- A browser the user logs into Brightspace with (for the token).
- *Optional:* the Claude-in-Chrome extension (for the few UI-only steps and
  the easiest token mint); Playwright (only for unattended/scheduled runs).

Full footprint analysis: `brightspace-course/references/install-and-auth.md`.

## Authentication

The tenant mints a ~1h JWT to any logged-in session. `bsapi.py` looks for a
token in this order: `BRIGHTSPACE_TOKEN` env var → cached token (<50 min
old) → saved `storage_state.json` cookies. Get a token by (best first):

### 1. Paste a token (universal, zero extra tooling)
In a Brightspace tab you're logged into, open DevTools → Console and run:
```js
const x = await fetch('/d2l/lp/auth/xsrf-tokens',{credentials:'same-origin'}).then(r=>r.json());
(await fetch('/d2l/lp/auth/oauth2/token',{method:'POST',credentials:'same-origin',
  headers:{'X-Csrf-Token':x.referrerToken,'Content-Type':'application/x-www-form-urlencoded'},
  body:'scope=*:*:*'}).then(r=>r.json())).access_token
```
Copy the printed token, then:
```bash
export BRIGHTSPACE_HOST=brightspace.vanderbilt.edu
printf '%s' 'PASTE_TOKEN_HERE' | python3 brightspace-course/scripts/bsapi.py save-token
python3 brightspace-course/scripts/bsapi.py whoami     # confirm
python3 brightspace-course/scripts/bsapi.py courses    # find your course id (ou)
```

### 2. Claude-in-Chrome mints it (best in Cowork)
With the extension connected and JavaScript permitted on the Brightspace
domain, the agent runs that same fetch in your tab and caches the result —
nothing to paste. Steps: `brightspace-course/references/chrome-auth.md`.

### 3. Import cookies from a browser profile
```bash
python3 brightspace-course/scripts/bsapi.py import-cookies safari|firefox|edge
```
Pure code, durable for days. **Chrome v127+ App-Bound Encryption blocks
Chrome profile reads** — use another browser you're logged into, or path 1/2.

### 4. Playwright login (headless/scheduled runs only)
```bash
pip install playwright && playwright install chromium
python3 tools/login.py
```
Saves cookies that refresh unattended for days–weeks. The only path that
needs no human and no open browser — so it's for cron/scheduled jobs and
nothing else. **Not required for interactive use.**

Non-default tenant: set `BRIGHTSPACE_HOST=<host>` before any command.
Expired-session symptoms: `401` mid-run, or an "empty referrerToken" — get a
fresh token by any path above.

## Installation per platform

Full experience (automatic skill-triggering + browser assist for UI-only
steps) is on **Claude Code** and **Claude Cowork**, which run Python locally
and can connect Claude-in-Chrome. Other platforms run the same Python with
more manual steps.

### Claude Code (CLI)
Skills live in `~/.claude/skills/` (personal) or `.claude/skills/` (project):
```bash
git clone https://github.com/vanderbilt-data-science/brightspace-skills-suite.git
cd brightspace-skills-suite
for s in brightspace-course course-video-prep brightspace-video-module-publish; do
  ln -s "$PWD/$s" "$HOME/.claude/skills/$s"
done
```
Then just ask in a session — skills trigger by description.

### Claude Cowork (Claude Desktop app, Mac/Windows)
1. Enable **Code execution** and **Skills** in **Settings → Capabilities**.
2. Zip each skill folder (`zip -r brightspace-course.zip brightspace-course`)
   and upload under **Settings → Capabilities → Skills → Upload skill**.
3. Connect the **Claude in Chrome** extension for UI-only steps.

Runs scripts locally, so it reaches your logged-in session — full experience.

### Claude web chat (claude.ai)
1. On a paid plan, enable **Code execution** and **Skills**, then upload each
   zipped skill folder.
2. The web sandbox can't see your browser — authenticate by **pasting a
   token** (path 1) so the sandbox calls the API directly.
3. No Chrome extension in the sandbox, so UI-only steps are done by you from
   the printed step-plans. All API-based work runs in the sandbox.

### OpenAI ChatGPT for Work (Team / Enterprise)
No native Agent-Skills format, but the engine is plain Python (runs in the
code interpreter):
1. Upload the relevant `scripts/` (`bsapi.py`, `bscourse.py`, `qti.py`,
   `rubric.py`, `grading.py`) and `references/` docs to the conversation or a
   Project.
2. Paste your token (`BRIGHTSPACE_TOKEN=<token>` or `save-token`).
3. Point ChatGPT at the matching `SKILL.md` / `references/*.md` as its
   operating instructions.

### OpenAI Codex
Closest non-Claude fit — it runs the scripts directly:
1. Clone the repo into Codex's workspace.
2. Provide the token via `BRIGHTSPACE_TOKEN` (or `save-token`).
3. Ask Codex to run the scripts, using `SKILL.md`/`references/*.md` as
   context.

> **Portability summary:** the *scripts* are provider-neutral Python and run
> anywhere Python does. The *skill wrapper* (auto-triggering) and *browser
> assist* (Claude in Chrome) are Claude features — best on Claude Code and
> Cowork. On OpenAI platforms, run the scripts directly and use the
> `SKILL.md` files as instructions.

## Command reference & examples

These are what the agent runs for you; you normally never type them.

**Audit a course**
```bash
python3 brightspace-course/scripts/bscourse.py map --ou 644191 -v
```

**Build from a manifest** (validate → dry-run → execute)
```bash
python3 brightspace-course/scripts/bscourse.py validate course.json
python3 brightspace-course/scripts/bscourse.py apply course.json --ou 644191
python3 brightspace-course/scripts/bscourse.py apply course.json --ou 644191 --execute
```

**Copy last year's course**
```bash
python3 brightspace-course/scripts/bscourse.py setup \
    --ou 700000 --source 644191 --offset-days 365 --execute
```

**Create an assignment**
```bash
python3 brightspace-course/scripts/bscourse.py assignment --ou 644191 \
    --title "Homework 3" --due 2026-09-05T04:59:00.000Z --out-of 100 \
    --instructions-file hw3.html --execute
```

**Author & publish a quiz** (questions + settings → QTI → import → settings)
```bash
python3 brightspace-course/scripts/qti.py --validate quiz.json
python3 brightspace-course/scripts/bscourse.py quiz-publish --ou 644191 \
    --quiz-json quiz.json --module "Module 2" --execute
```

**Rubric: preview, get UI-entry steps, verify placement**
```bash
python3 brightspace-course/scripts/rubric.py preview    rubric.json
python3 brightspace-course/scripts/rubric.py entry-plan rubric.json
python3 brightspace-course/scripts/rubric.py verify     rubric.json --ou 644191
```

**Announcement**
```bash
python3 brightspace-course/scripts/bscourse.py announce --ou 644191 \
    --title "Welcome!" --html-file welcome.html --execute
```

*(Grading commands live with the `brightspace-grading` skill on the
`student-data-skills` branch, pending privacy review.)*

The intermediate formats — `course.json`, `quiz.json`, `rubric.json` — are
documented under `brightspace-course/references/`.

## Safety model

1. **Dry-run by default.** Write commands print the plan and stop; `--execute`
   performs it.
2. **Production is guarded.** On a production host, `--execute` also requires
   `--i-mean-production`.
3. **200 ≠ landed.** Every write is verified by an independent read-back.
4. **Never PUT a partial object.** Updates read the whole object first
   (Brightspace treats missing fields as deletions).
5. **Grading is drafts-first.** Feedback is invisible until explicitly
   published.
6. **Completeness before upload.** `course.json` / `quiz.json` / `rubric.json`
   are validated first, so gaps surface as findings, not half-built courses.

## What Brightspace can and cannot do

Not every operation has an API. `brightspace-course/references/capability-map.md`
classifies every operation as **API** (scripted directly), **UI-only** (done
via browser assist or a printed step-plan, then verified by API), or **not
possible** (with a workaround). The UI-only tail includes rubric *creation*,
quiz *question* authoring beyond QTI import, and some quiz settings — most of
which can instead be pre-built in a template course and copied.

## Repository layout

```
brightspace-course/     Design & build a course (the shared engine lives here)
  SKILL.md
  scripts/              bsapi.py, bscourse.py, qti.py, rubric.py, manifest.py
  references/           install-and-auth, capability-map, course-manifest,
                        quiz-format, rubric-format, page-templates,
                        chrome-auth, api-quickref, template-setup
  assets/               plain-templates/, ccc-templates/ (optional kits)
course-video-prep/      Zoom recording → segments, captions, quizzes
brightspace-video-module-publish/    Publish a prepared package as a content module
tools/login.py          Optional Playwright login (unattended runs only)
LICENSE                 MIT
```

---

*Built and validated against a live Brightspace tenant (Vanderbilt).
Created by Jesse Spencer-Smith and Claude Opus. MIT License.*
