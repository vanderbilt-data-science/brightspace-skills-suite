---
name: brightspace-grading
description: Pull student assignment submissions from Brightspace (D2L), grade them with AI against the assignment's rubric or criteria, and push scores + written feedback back - drafts first, published only after instructor review. Use whenever the user wants to grade submissions, "pull what students turned in", "draft feedback for Lab 2", "how many are still ungraded", batch-grade an assignment, or fill scored rubrics. Requires the brightspace-course skill installed alongside (shared auth/client). Never publishes feedback without explicit instructor approval.
---

# Brightspace Grading Workbench

Grade with AI, publish with judgment. The loop:

```
pull  ──►  AI drafts per-student feedback + scores  ──►  instructor
                    (against rubric/criteria)            reviews table
                                                             │ approves
push as DRAFTS (invisible to students) ──► spot-check ──► publish
```

Scripts in `scripts/grading.py`; auth comes from the sibling
`brightspace-course` skill (same token sources, same `BRIGHTSPACE_HOST`
handling).

## Non-negotiables

1. **The instructor approves before anything is student-visible.**
   Draft feedback (`IsGraded: false`) is the default and is invisible to
   students; `--publish` is a separate, explicitly-approved step.
2. **Show the whole grading table before pushing anything** — user, score,
   one-line feedback summary. The instructor may adjust any row.
3. **200 ≠ landed.** Dropbox feedback is a documented silent-drop trap:
   every push is read back and the *text* compared (the script retries
   the alternate rich-text shape automatically and refuses to continue
   if neither lands).
4. **FERPA posture:** submissions are student records. Keep pulled files
   in the working directory, don't commit them, don't quote one
   student's work in another's feedback.

## Workflow

### 1. Locate and pull

```bash
python3 scripts/grading.py folders --ou 644191
python3 scripts/grading.py pull --ou 644191 --folder 399527
```

`pull` downloads every submitter's files into
`submissions-ou<ou>-f<folder>/<name>-<uid>/` plus `submissions.json`
(who, what, when, out-of).

### 2. Grade with AI

Read the assignment's instructions and rubric first:
- Rubric attached in Brightspace? `GET` it via the folder
  (`Assessment.Rubrics`) or ask for the `rubric.json` used to create it
  (see brightspace-course's `references/rubric-format.md`).
- No rubric? Derive criteria from the assignment instructions and
  **confirm them with the instructor before grading**.

For each submission: read the files, score per criterion, and write
student-facing feedback — specific to their work, naming what was strong
and what to fix, in the instructor's voice (ask for a sample or their
preferences the first time). Produce a review table:

| Student | Score | Feedback summary |
|---|---|---|

and per-student feedback HTML files in the working directory.

### 3. Review gate

Present the table. The instructor edits/approves. **Do not proceed on
silence.**

### 4. Push drafts, then publish

```bash
python3 scripts/grading.py feedback --ou 644191 --folder 399527 \
    --user 12345 --score 87 --html feedback/12345.html --execute
# after instructor spot-checks drafts in the UI:
#   same command + --publish   (re-approval required)
python3 scripts/grading.py status --ou 644191 --folder 399527
```

Scored rubrics: the feedback POST carries `RubricAssessments[]`; rubric
assessment PUT also works per-user (`/assessment?objectType=Dropbox...`).
Extend the script when the course uses attached rubrics — GET the rubric
structure first to map criterion/level ids.

## Boundaries

- Quiz attempts: auto-graded by Brightspace; this skill reads attempts
  (`.../quizzes/{id}/attempts/`) but per-question responses are not in
  the API — quiz-answer review stays in the UI.
- No bulk-grade API exists: pushes loop per-student (that's fine — the
  read-back verify makes it slow-but-sure).
- Discussions grading: extend on demand (routes exist).
