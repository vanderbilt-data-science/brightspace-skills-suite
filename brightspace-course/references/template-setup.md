# The CCC Online Programs template (optional)

> **Optional kit.** CCC is one page-template choice among several — see
> `references/page-templates.md`. This file applies only when a course
> sets `course.template: "ccc"`. For a neutral look use `plain`; for no
> house style use the default `none`.

Source of truth: the course **"CCC Online Programs Template Sandbox"**
(export saved 2026-08; the extracted page kit is versioned in this
skill's `assets/ccc-templates/`). The sandbox course's content-styler URL
embeds **ou 6606** — likely its org unit id on production (verify with
`bsapi.py courses` before relying on it).

## What the template is

Not a fixed module layout — a **page-design kit** built on D2L's
Courseware HTML Templates **V5** with the **Vanderbilt-2025** theme and
CCC branding. Every page shares:

- `<head>` loading, in order:
  `/shared/D2L/Courseware_HTML_Templates/V5/latest/_assets/js/global.min.js`
  (module), `.../js/Vanderbilt-2025.js`, `.../css/global.min.css`,
  `.../css/Vanderbilt-2025.min.css`,
  `/shared/HTML-Template-Library/HTML-Templates-V5/css/custom.css`, and
  the course's `/d2l/le/contentstyler/{ou}/files/View` stylesheet. These
  are tenant-relative paths that resolve inside the D2L content viewer —
  keep them exactly as-is.
- A **hero band**: full-width table row, `background-color: #1c1c1c`,
  CCC hero image (Cloudinary
  `CCC_hero_background_xr3cov.png`), `border-top: 4px solid #cfae70`
  (gold), inside a 960px-max table. The syllabus variant adds the white
  CCC logo (`V_Centered_CCC_White_1_wir9ei.png`).
- Body wrapped in
  `<div class="courseware-container-fluid courseware-themes">` +
  `<div class="courseware-layouts-content-wrapper">`.
- Interactive widgets (accordions, callouts) as
  `d2l-element mceNonEditable` blocks with `data-type`
  (`unnumbered`/`attention`/`noicon`/`left`/`vertical`/`horizontal`) —
  copy whole blocks verbatim; their JS comes from the shared assets.
- Placeholders in square brackets: `[Title of Lesson]`,
  `[Note for Instructor: …]`. **Every bracket must be resolved or the
  section removed before publishing.**

## Page types (files in `assets/ccc-templates/`)

| File | Use for | Skeleton |
|---|---|---|
| `course-overview.html` | Course "start here" page | h1 Overview; h2 Technology Requirements / Prior Knowledge Requirement / Navigation (references `navigation-arrow.png` — upload it alongside) |
| `module-overview.html` | First page of each module | Objectives ("Knowledge and Skills You Will Gain"), h2 Overview of Activities (assignments/discussions/quizzes lists with due dates) |
| `lesson.html` | Mixed video+reading lesson | h1 "Lesson: […]"; h2 Video / Reading (+Citation) / Practice Question / Knowledge and Skills (Module Level, Course Level) |
| `lecture.html` | Video lecture page | h1 "Lecture: […]"; h2 Video (iframe embed + transcript + slides links) / Knowledge and Skills |
| `reading-activity.html` | Reading assignment | h1 "Reading: […]"; h2 Instructions (+Citation) / Practice Question / Knowledge and Skills |
| `assignment-description.html` | Assignment page (pairs with a dropbox folder) | h1 "Assignment Description: […]"; h2 Overview / Instructions and Key Components (action steps) / Assignment Details |
| `next-steps.html` | Module closer | Recap of Activities (due-date reminders), preview of next module |
| `blank.html` | Anything else | h1 "[Content Type: Title]"; generic sections + Knowledge and Skills |
| `syllabus.html` | The syllabus | h1 Syllabus; h2 [Course Name] (Instructor Information/Availability + photo), Course Information, Course Outcomes, Program Outcomes, Course Schedule, Course Materials, Course Policies and Expectations, Grading Policies, Grading Scale, Additional Policies/Resources/Support |

Convention: every content page ends with **"Knowledge and Skills You Will
Gain"** mapping the page to Module-Level and Course-Level outcomes — keep
that section filled, it's the program's QA hook (AdvancED/accreditation
lineage).

## Authoring workflow (what Claude does)

1. Copy the right template from `assets/ccc-templates/`.
2. Fill every `[placeholder]` from the user's material; delete sections
   that don't apply (e.g. no Practice Question) rather than leaving
   brackets.
3. For videos hosted in-course, replace the YouTube iframe with the
   uploaded topic's player or keep an iframe/link per the user's hosting
   choice.
4. Publish with
   `bscourse.py page --ou <ou> --module "<module>" --file <page>.html`
   (upload `navigation-arrow.png` via `upload` first if the page uses
   it), then spot-check rendering in the browser — the shared-asset CSS
   only resolves inside D2L.

## Standing up a full course

The kit implies the course rhythm: per module —
**Module Overview → Lessons/Lectures/Readings → Assignment Description
(+ dropbox via `assignment`) → quiz (via `quiz-import`) → Next Steps** —
plus course-level **Overview** and **Syllabus** pages up front. If a
fully-built master course exists for the program, prefer `setup`
(Course Copy) to clone it, then regenerate pages that need new content;
otherwise generate pages from this kit module-by-module.
