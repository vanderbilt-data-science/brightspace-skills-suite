---
name: course-video-prep
description: Convert a Zoom class recording - a local mp4 + VTT transcript, OR a Zoom cloud recording link the skill fetches for you - plus presentation materials into a best-practice asynchronous course module package: short concept-aligned video segments, each opening with an intro card branded to the target course (the CCC kit, a plain kit, custom colors, or a provided template slide), per-segment captions, interspersed low-stakes check-for-understanding quizzes (QTI for Brightspace import + KST instrument files), topic descriptions, and a manifest.json ready for the brightspace-video-module-publish skill. Use whenever the user wants to turn a recorded lecture, workshop, or technology demonstration into online course videos, or says things like "prepare the async content", "chunk this recording", "make course videos from this Zoom", "make videos from this Zoom cloud link", "prep week N videos", or mentions preparing async material for the MSAI / KST-based courses. This is Tool #2 "Video Preparation" from course-development/docs/tools-to-build.md.
---

# Course Video Prep

Turn one long recording into a complete, reviewable async module package: a sequence of short videos (each opening with an intro card), captions, quizzes placed between videos, and descriptive text — everything the `brightspace-video-module-publish` skill needs to put it in the LMS in one motion.

The pedagogical model: students watch a 6-12 minute segment focused on one concept, then immediately answer 2-4 low-stakes questions about it (retrieval practice), then move to the next segment. Segment boundaries follow concepts, not the clock.

## Data handling — FERPA / VU Level 3 (non-negotiable)

Claude is **not approved for Vanderbilt Level 3 (Restricted) data**, and
class recordings can contain it: student names in the VTT speaker labels
and student voices/questions in the audio are FERPA education records.
Until automated redaction lands (issue FERPA-2):

- Before analyzing a transcript, ask the user whether students speak in
  it. Prefer recordings of instructor-only lecture/demo segments.
- If student speech or names appear, have the user trim/redact first, or
  exclude those spans from segments and captions — never republish
  student names or voices in the packaged captions/videos.

## Workflow overview

```
Phase 0  Discovery & grounding        -> inventory confirmed with user
Phase 1  Transcript analysis          -> segment-plan.md   [USER APPROVAL GATE]
Phase 2  Video production             -> videos/ captions/ intro-cards/
Phase 3  Quiz authoring               -> quizzes/ instruments/
Phase 4  Descriptions & manifest      -> overview.html, manifest.json
Phase 5  Validation & handoff report  -> validated package
```

The only hard stop is after Phase 1: the segment plan is cheap to fix before rendering and expensive after. Phases 2-5 run without pausing once the plan is approved.

---

## Phase 0: Discovery & grounding

**If the user gives a Zoom cloud link instead of local files, fetch first:**

```bash
# API path (reliable) — needs ZOOM_ACCOUNT_ID/CLIENT_ID/CLIENT_SECRET (S2S OAuth app):
python3 <skill-path>/scripts/fetch_zoom.py --meeting <meetingId-or-UUID> --dest <dir>
# or a direct download URL you copied from the recording page (no creds):
python3 <skill-path>/scripts/fetch_zoom.py --url <mp4_url> [--url <vtt_url>] --dest <dir>
```

It downloads the MP4 and transcript VTT and prints the paths to use as
`source_video`/`source_vtt`. If no transcript comes back, transcribe
locally (whisper, see "Large / awkward inputs"). Passcode-protected
share links aren't scraped — use the API path or a direct download URL.

**Determine the course branding** for the intro cards. The intro card
should match the course's Brightspace look:
- If a `course.json` exists for the target course (from `brightspace-course`),
  read its `course.template` (`ccc` / `plain` / `none` / custom) and use
  the matching card preset.
- Else ask: CCC kit, a plain look, specific brand colors, or a **template
  slide** image to use as the card background.
- The resolved choice becomes the `branding` block in `plan.json` (Phase 2).

**Inventory the working directory** (and any paths the user names):

| Type | Look for | Role |
|------|----------|------|
| Recording | `.mp4` (Zoom names like `GMT*_Recording_1920x1080.mp4`) | Required |
| Transcript | `.transcript.vtt` preferred over `.cc.vtt` (fuller text) | Required |
| Slides | `.pdf`, `.pptx` | Optional - improves titles/boundaries |
| Outline / script | `lecture.md`, `outline*.txt/md` | Optional - best segmentation source |
| Audio-only | `.m4a` | Ignore if mp4 present |

**Locate KST grounding** if this is a course in the course-development ecosystem. Check (in order):
1. A `week-N/lecture.md` for this session — its `## Async lecture (recorded)` section (Recap / Part 1 / Part 2 / Wrap) is the intended segment structure, and its frontmatter carries `concepts:` and `objectives:`.
2. `<course-dir>/knowledge-space/domain.json` — items with `"Mastery means:"` descriptions, `bloom` levels, and `assessment_hint` fields that seed quiz questions.
3. `<course-dir>/courseNN.md` week sections and `curriculum/concepts.yaml` (program graph, kebab-case ids).

The default location for grounding data is a local course-development directory. If no grounding exists (e.g., a standalone workshop), proceed ungrounded — derive topics from the transcript and slides, and use descriptive kebab-case slugs as concept ids.

**Check tools**: `ffmpeg` and `ffprobe` must be on PATH (fail early if not). The bundled scripts auto-install their Python needs (Pillow).

**Confirm with the user** before proceeding: the inventory, the course/week identity (or "ungrounded workshop"), and the output location. Default output: `<source-dir>/async-package/` unless a course week directory is the natural home (`week-N/async-package/`).

## Phase 1: Transcript analysis -> segment plan

Parse the VTT into `{start, end, speaker, text}` entries (skip `WEBVTT` header and `NOTE` blocks; timestamps are on `-->` lines; speaker prefixes look like `Name: text`; merge consecutive same-speaker entries). Zoom sometimes misattributes speakers — cross-check against slides/outline if names matter.

**Find the segment boundaries.** Priority order of evidence:

1. **The lecture.md Parts** (if grounded): each `Part N - <concept>` is a segment. Locate where each Part begins in the recording by matching its content against the transcript.
2. **Slide transitions and explicit markers**: "next slide", "moving on", "let's talk about", "now I want to show you".
3. **Activity shifts**: lecture -> live demo -> Q&A. Never split mid-demo; a demonstration (e.g., driving Claude through a problem) must stay in one segment even if that segment runs long.
4. **Silence gaps > 3s** often mark transitions (typing, screen switching).

**Sizing rules** (accepted defaults for this program):
- Target 6-12 minutes per segment; hard cap 15. A Part that runs past 15 minutes gets split at a sub-topic seam within it.
- Segments under ~4 minutes usually mean the boundary is wrong — merge with a neighbor unless it is genuinely a self-contained concept.
- **Cut the dead air**: choose boundaries that exclude pre-class chatter, breaks, tech fumbling, and long admin stretches. Content between segment N's `end` and segment N+1's `start` is simply dropped — use that. Classroom Q&A worth keeping can become its own short segment (or be excluded if it was housekeeping).
- Sync-session recordings often contain interaction (polls, breakouts) that makes no sense async — exclude those spans, and note in the plan what was dropped and why.

**Write `segment-plan.md`** in the package directory:

```markdown
---
source_recording: GMT20260625-164513_Recording_1920x1080.mp4
source_transcript: GMT20260625-164513_Recording.transcript.vtt
course: C1            # or "ungrounded"
week: 1
generated_by: course-video-prep
status: draft
---
# Segment plan: <session title>

| # | Segment title | Start | End | Length | Concepts | Type |
|---|--------------|-------|-----|--------|----------|------|
| 1 | Tokens and embeddings | 00:03:15 | 00:12:40 | 9:25 | tokens-embeddings | lecture |
| 2 | Demo: exploring tokenization with Claude | 00:12:40 | 00:24:05 | 11:25 | tokens-embeddings | demo |

## Dropped spans
- 00:00:00-00:03:15 - pre-class setup and roll call
- 00:24:05-00:26:30 - break

## Notes
- Segment 2 runs 11:25 because the demo is a single continuous problem-solving arc.
```

**Stop here and show the user the plan.** Ask them to confirm or adjust (boundaries, titles, drops). Do not render video until they approve.

## Phase 2: Video production

Build the plan JSON and run the bundled script (it renders intro cards, cuts, normalizes loudness, concatenates, and slices captions — see `references/package-format.md` for the full plan schema):

```bash
python3 <skill-path>/scripts/segment_video.py plan.json
```

Each output video = 6s intro card (title, "Part N of M", concepts covered, length) + the content cut. Captions are sliced from the source VTT and re-offset for the intro. The script prints a per-segment report; check every segment's final duration matches plan expectations (±2s) before moving on.

**Branding the intro cards** (from the Phase 0 decision). Add a `branding`
block to `plan.json`:

```json
"branding": {
  "template": "ccc",              // ccc | plain-dark | plain-light | custom
  "bg": "#1c1c1c",               // optional overrides (custom, or tweak a preset)
  "accent": "#cfae70",
  "logo": "https://.../logo.png", // optional; local path or URL (cached)
  "template_slide": "intro.png"   // optional; used as the card BACKGROUND
}
```

- Omitting `branding` defaults to the CCC preset (which pulls the CCC logo)
  — unchanged from before.
- `template: "ccc"` uses Vanderbilt CCC colors + logo; `plain-light`/`plain-dark`
  are neutral; `custom` takes your `bg`/`accent` (text/muted auto-pick for
  contrast).
- **If `template_slide` is given, it becomes the card background** (cover-fit
  with a legibility scrim), and the title/bullets render over it — use this
  when the program has a fixed title-slide design.

Match `template` to the course's `course.json` template so the videos and
the Brightspace pages share one look.

The intro card states what the video covers — write the card bullets as "you will be able to..." phrasing when objectives are grounded, otherwise 2-3 content bullets. Keep bullets short; they render at ~44px.

Spot-check quality: extract one frame from the start of each final video (`ffmpeg -ss 2 -i out.mp4 -frames:v 1 check.png`) and view it — the intro card should be crisp and correctly titled.

## Phase 3: Quiz authoring

For each segment (or a cluster of two very short related segments), author **2-4 questions**. Read `references/quiz-authoring.md` before writing the first question — it covers question quality, the Bloom gate, the QTI JSON schema, and the KST instrument format. The essentials:

- Quizzes only evidence *remember/understand* (and light *apply*) — that is the program's assessment-blueprint rule. If a segment's grounded items are all evaluate/create-level, write comprehension questions about the demonstrated process instead, and say so in the answer key.
- Ground questions in what was actually said/shown in that segment. `assessment_hint` fields in `domain.json` are pre-approved question seeds — use them.
- Every wrong option needs a reason to exist (a real misconception), and feedback explains *why*.

Then produce three artifacts per quiz:
1. `quizzes/quiz-NN-<slug>.questions.md` — human-readable questions + answer key + rationale (the instructor review surface).
2. `quizzes/quiz-NN-<slug>.zip` — QTI 1.2 package via `python3 <skill-path>/scripts/make_qti.py questions.json out.zip` (question CRUD has no Brightspace API; QTI import is the only automatable path).
3. `instruments/quiz-NN.md` — KST instrument file with the load-bearing `items_assessed: [concept-id, ...]` frontmatter, so `kst.py status` sees coverage. Skip this only for ungrounded content.

## Phase 4: Descriptions & manifest

Write the descriptive layer (plain ASCII, define acronyms on first use — the house style):

- **`overview.html`** — the "Start here" page for the module: what this week's async portion covers, the segment list with lengths, total time commitment, and how the quizzes count. Simple semantic HTML, no external assets.
- **Per-item descriptions** — 1-2 sentences per video and quiz (these become the Brightspace topic descriptions).
- **`manifest.json`** — the machine-readable module structure the publish skill consumes: ordered items (`html` overview -> `video` -> `quiz` -> `video` -> `quiz` ...), file paths, durations, concepts, grade intent. Full schema in `references/package-format.md`. The manifest is the contract — the publish skill reads nothing else.

## Phase 5: Validation & handoff

```bash
python3 <skill-path>/scripts/validate_package.py <package-dir>
```

This verifies the manifest parses, every referenced file exists, every video has captions, durations are inside limits, QTI zips are well-formed, and instruments carry `items_assessed`. Fix anything it flags.

Finish with a report to the user: segment table (title, length, quiz question count), total watch time, what was dropped from the recording, where the package lives, and the one-liner to publish it:

> Package ready. To upload: use the **brightspace-video-module-publish** skill on `<package-dir>` (dry-run first).

## Conventions this skill must honor

- **Ground, never invent scope**: concepts/objectives come from lecture.md, domain.json, or concepts.yaml when they exist. Frontmatter on generated markdown carries `generated_by: course-video-prep` and `status: draft` — faculty promote drafts, never this skill.
- **kebab-case ids** everywhere; reuse existing concept ids rather than coining near-duplicates.
- **Plain ASCII** in all generated text (no smart quotes, em-dashes, arrows); define every acronym at first use.
- **Nothing uploads from this skill.** Its product is a package on disk. Upload is `brightspace-video-module-publish`'s job — keeping the seam clean is deliberate (the LMS access layer is still evolving).

## Large / awkward inputs

- Transcripts beyond ~50k tokens: analyze in 15-minute chunks, then reconcile boundaries across chunk seams.
- Recording is screen-share only at 720p or worse: still fine — intro cards render at source resolution so nothing is upscaled.
- No transcript at all: `whisper` is installed on this machine; offer to transcribe the m4a (`whisper audio.m4a --model small.en --output_format vtt`), but warn it takes a while on long recordings.
- Multiple recordings for one week (e.g., two async sessions): run the pipeline per recording into one shared package; number segments continuously.
