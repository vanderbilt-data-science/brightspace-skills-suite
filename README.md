# Brightspace Skills

**Run your Brightspace (D2L) course by asking an AI agent — design it,
manage it, and grade it in plain language, instead of clicking through the
GUI.** These are agent skills, used from **Claude Cowork, Claude Code,
ChatGPT for Work, or OpenAI Codex** — not a command-line tool you operate
yourself.

Created by **Jesse Spencer-Smith** (Vanderbilt Data Science Institute) and
**Claude Opus**.

Each skill is an [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview):
packaged know-how (a `SKILL.md` plus Python helpers) that an AI agent loads
on its own when it's relevant. **You don't run commands** — you ask ("set up
my course from this folder", "who hasn't submitted Lab 2", "draft feedback
for these essays") and the agent picks the right skill and does the work,
showing you what it will change before it changes anything. Under the hood
the agent talks to Brightspace over its official Valence API using **your own
logged-in session** — no OAuth app registration and no admin rights.

> **Why this exists:** Vanderbilt (like many schools) gives faculty no API
> credentials for Brightspace. These skills let an agent mint a short-lived
> API token from a session you're already logged into, so everything an
> instructor does — content, assignments, quizzes, announcements, grading —
> can be done conversationally, verified, and repeated, instead of clicked.

---

## The three skills

| Skill | Job | What it does |
|---|---|---|
| **`brightspace-course`** | **Design & build** | Stand up a course — brand new, copied from a previous offering, or from a template. A `course.json` manifest is validated for completeness *before* anything is uploaded, then applied idempotently. Includes a full quiz pipeline (author → QTI → import → settings, all via API) and a rubric pipeline (author → preview → guided UI entry → API verification). Page templates are pluggable (none / plain / a branded kit / your own). |
| **`brightspace-manage`** | **Run it, in-semester** | Day-to-day upkeep of a live course: post announcements, publish this week's notes/slides/videos, adjust due dates, audit the course structure, check who has submitted. Enforces visibility rules so nothing goes student-facing by accident. |
| **`brightspace-grading`** | **Assess student work** | Pull submissions, draft scores and written feedback with AI against the assignment's rubric or criteria, show you a review table, push feedback as **invisible drafts**, and publish only after you approve. Every push is verified by reading it back. |

Two companion skills round out the async-content path:
**`course-video-prep`** (turn a Zoom recording into segmented videos,
captions, and quizzes) and **`brightspace-publish`** (bulk-publish a
prepared package as a content module).

### How they fit together

```
        brightspace-course  ─────►  build the course (content, quizzes, rubrics)
                 │
        brightspace-manage  ─────►  keep it current through the term
                 │
        brightspace-grading ─────►  pull, grade with AI, publish feedback

   course-video-prep ──► brightspace-publish   (async video modules, optional)
```

All five share one engine (`brightspace-course/scripts/bsapi.py`) and one
set of safety rules.

---

## Safety model (the same rules everywhere)

1. **Dry-run by default.** Every write command prints exactly what it would
   do and stops. You add `--execute` to actually do it.
2. **Production is guarded.** On a production host, `--execute` *also*
   requires `--i-mean-production`. Development belongs on a test tenant or a
   sandbox course.
3. **200 ≠ landed.** Brightspace sometimes returns success while silently
   dropping data. Every write is verified by an independent read-back — the
   scripts trust the read, not the status code.
4. **Never PUT a partial object.** Brightspace treats missing fields as
   deletions, so updates always read the whole object first.
5. **Grading is drafts-first.** Feedback is invisible to students until you
   explicitly approve publishing.
6. **Completeness before upload.** `course.json`, `quiz.json`, and
   `rubric.json` are validated first, so gaps surface as findings — not as a
   half-built course.

---

## Quick start

```bash
git clone https://github.com/vanderbilt-data-science/brightspace-skills-suite.git
cd brightspace-skills-suite

# 1. Get an API token from a Brightspace tab you're logged into.
#    In that tab's DevTools console (⌥⌘I → Console), run:
#      const x = await fetch('/d2l/lp/auth/xsrf-tokens',{credentials:'same-origin'}).then(r=>r.json());
#      (await fetch('/d2l/lp/auth/oauth2/token',{method:'POST',credentials:'same-origin',
#        headers:{'X-Csrf-Token':x.referrerToken,'Content-Type':'application/x-www-form-urlencoded'},
#        body:'scope=*:*:*'}).then(r=>r.json())).access_token
#    Copy the printed token, then:
export BRIGHTSPACE_HOST=brightspace.vanderbilt.edu   # your tenant
printf '%s' 'PASTE_TOKEN_HERE' | python3 brightspace-course/scripts/bsapi.py save-token

# 2. Confirm it works and find your course id:
python3 brightspace-course/scripts/bsapi.py whoami
python3 brightspace-course/scripts/bsapi.py courses
```

Only **Python 3 and the `requests` package** are required — and `requests`
auto-installs on first run. Full auth options (paste a token,
Claude-in-Chrome mint, browser-profile import, or the optional Playwright
login for unattended jobs) are in
[`brightspace-course/references/install-and-auth.md`](brightspace-course/references/install-and-auth.md).

---

## Examples

**Audit a course:**
```bash
python3 brightspace-course/scripts/bscourse.py map --ou 644191 -v
```

**Build a course from a manifest** (dry-run, then execute):
```bash
python3 brightspace-course/scripts/bscourse.py validate course.json
python3 brightspace-course/scripts/bscourse.py apply course.json --ou 644191
python3 brightspace-course/scripts/bscourse.py apply course.json --ou 644191 --execute
```

**Copy last year's course into a new offering:**
```bash
python3 brightspace-course/scripts/bscourse.py setup \
    --ou 700000 --source 644191 --offset-days 365 --execute
```

**Create an assignment:**
```bash
python3 brightspace-course/scripts/bscourse.py assignment --ou 644191 \
    --title "Homework 3" --due 2026-09-05T04:59:00.000Z --out-of 100 \
    --instructions-file hw3.html --execute
```

**Author and publish a quiz** (questions + settings in one file → API):
```bash
python3 brightspace-course/scripts/qti.py --validate quiz.json
python3 brightspace-course/scripts/bscourse.py quiz-publish --ou 644191 \
    --quiz-json quiz.json --module "Module 2" --execute
```

**Draft a rubric, preview it, get the UI-entry steps, verify placement:**
```bash
python3 brightspace-course/scripts/rubric.py preview   rubric.json
python3 brightspace-course/scripts/rubric.py entry-plan rubric.json
python3 brightspace-course/scripts/rubric.py verify     rubric.json --ou 644191
```

**Post an announcement:**
```bash
python3 brightspace-course/scripts/bscourse.py announce --ou 644191 \
    --title "Welcome!" --html-file welcome.html --execute
```

**Grade an assignment with AI:**
```bash
python3 brightspace-grading/scripts/grading.py folders --ou 644191
python3 brightspace-grading/scripts/grading.py pull --ou 644191 --folder 399527
#  ... AI reads the submissions, drafts scores + feedback, you review ...
python3 brightspace-grading/scripts/grading.py feedback --ou 644191 \
    --folder 399527 --user 12345 --score 87 --html feedback/12345.html --execute
#  ... you spot-check the drafts, then re-run with --publish ...
```

In practice you rarely type these — you ask the assistant ("grade Lab 1
against the rubric", "make my course match last year's") and it runs them,
showing you each dry-run plan first.

---

## Installation

Each skill is a self-contained folder (`SKILL.md` + `scripts/` +
`references/`). How you install depends on the platform. **Full experience
(automatic skill-triggering + browser assist for the few UI-only steps) is
on Claude Code and Claude Desktop**, because they run Python locally and can
connect the Claude-in-Chrome extension. Other platforms run the same Python,
just with more manual steps.

### Claude Code (CLI) — recommended

Skills live in `~/.claude/skills/` (personal) or `.claude/skills/` (project).
Clone the repo and link the skill folders:

```bash
git clone https://github.com/vanderbilt-data-science/brightspace-skills-suite.git
cd brightspace-skills-suite
for s in brightspace-course brightspace-manage brightspace-grading \
         course-video-prep brightspace-publish; do
  ln -s "$PWD/$s" "$HOME/.claude/skills/$s"
done
```

Start a session and just ask — the skills trigger by description. The
Claude-in-Chrome extension (if installed) handles the UI-only tail (rubric
creation, quiz pools).

### Claude Cowork (Claude Desktop app, Mac/Windows)

1. Enable **Code execution** and **Skills** in **Settings → Capabilities**.
2. For each skill, zip its folder (e.g. `zip -r brightspace-course.zip
   brightspace-course`) and upload it under **Settings → Capabilities →
   Skills → Upload skill**.
3. Connect the **Claude in Chrome** extension for the UI-only steps.

The desktop app runs the scripts locally, so it can reach your logged-in
Brightspace session — the same full experience as Claude Code.

### Claude web chat (claude.ai)

1. On a paid plan, enable **Code execution** and **Skills** in **Settings →
   Capabilities**, then upload each skill folder (zipped), as above.
2. Because the web sandbox can't see your browser, authenticate by **pasting
   a token** (the Quick-start console snippet) so the sandbox can call the
   API directly.
3. There's no Chrome extension in the browser sandbox, so the handful of
   UI-only operations (rubric *creation*, quiz question pools) are done by
   you from the printed step-plans. Everything API-based — content,
   assignments, quizzes, grading — runs in the sandbox.

### OpenAI ChatGPT for Work (Team / Enterprise)

ChatGPT has no native Agent-Skills format, but the engine is plain Python,
so it runs in ChatGPT's code-interpreter (Advanced Data Analysis):

1. Upload the relevant `scripts/` (`bsapi.py`, `bscourse.py`, `qti.py`,
   `rubric.py`, `grading.py`) and the `references/` docs to the
   conversation or a Project.
2. Paste your token and set it: the assistant runs
   `BRIGHTSPACE_TOKEN=<token>` in the environment (or calls `save-token`).
3. Point ChatGPT at the matching `SKILL.md` / `references/*.md` as
   instructions so it knows the workflow and safety rules.

You lose automatic triggering and the Chrome assist, but all API operations
work. Treat the `SKILL.md` files as the operating manual.

### OpenAI Codex

Codex (the coding agent) runs the scripts directly — it's the closest
non-Claude fit, since everything here is ordinary Python:

1. Clone the repo into Codex's workspace.
2. Provide the token via `BRIGHTSPACE_TOKEN` (or `save-token`).
3. Ask Codex to run the scripts (`bscourse.py`, `grading.py`, …). Feed it
   the `SKILL.md` and `references/*.md` as context for the workflow.

No skill auto-triggering and no browser assist (so UI-only steps are manual),
but the full API surface is available.

> **Portability summary:** the *scripts* are provider-neutral Python and run
> anywhere Python does. The *skill wrapper* (auto-triggering by description)
> and the *browser assist* (Claude in Chrome for UI-only steps) are Claude
> features — best on Claude Code and Claude Desktop. On OpenAI platforms,
> run the scripts directly and use the `SKILL.md` files as instructions.

---

## What Brightspace can and can't do (and the workarounds)

Not every operation has an API. The skills are honest about this: the
capability map
([`brightspace-course/references/capability-map.md`](brightspace-course/references/capability-map.md))
lists every operation as **API** (scripted directly), **UI-only** (done via
browser assist or a printed step-plan, then verified by API), or **not
possible** (with the workaround). Highlights of the UI-only tail: rubric
*creation*, quiz *question* authoring beyond QTI import, and some quiz
settings — most of which you can instead pre-build in a template course and
copy.

---

## Repository layout

```
brightspace-course/     Design & build a course (the engine lives here)
  SKILL.md
  scripts/              bsapi.py, bscourse.py, qti.py, rubric.py, manifest.py
  references/           install-and-auth, capability-map, course-manifest,
                        quiz-format, rubric-format, page-templates, api-quickref
  assets/               plain-templates/, ccc-templates/ (optional kits)
brightspace-manage/     In-semester upkeep of a running course
brightspace-grading/    Pull submissions, AI-draft feedback, publish
course-video-prep/      Zoom recording → segments, captions, quizzes
brightspace-publish/    Publish a prepared package as a content module
tools/login.py          Optional Playwright login (unattended/scheduled runs)
LICENSE                 MIT
```

---

## Provenance & status

Built and validated against a live Brightspace tenant (Vanderbilt). The
skills default to test tenants and sandbox courses; production writes require
an explicit confirmation flag. This is an actively developing project —
issues and pull requests welcome.

**Created by Jesse Spencer-Smith and Claude Opus.** Licensed under the MIT
License (see [`LICENSE`](LICENSE)).
