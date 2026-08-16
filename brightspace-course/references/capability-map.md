# Brightspace capability map — what works, what doesn't, and what to do instead

The decision table for this skill. Three tiers:
**API** (this skill does it directly) · **UI-only** (Brightspace can, but
only through the browser — use the template copy or Claude-in-Chrome) ·
**Cannot** (Brightspace has no such feature — offer the workaround).

Documentation coverage behind this map: the lab's `reference/api/`
(11 docs: auth, courses/org, content, assignments, rubrics, grades,
quizzes/QTI, classlist, announcements/calendar/discussions,
engagement/misc), compiled June 2026 from official Valence docs + live
validation, updated when the tenant disagrees. Not yet researched in
depth: ePortfolio, Awards, Checklists, Surveys, LTI administration —
treat requests there as "check the reference, likely UI."

## Course structure & content

| User wants | Tier | How / workaround | Trigger phrases |
|---|---|---|---|
| Create/organize modules | **API** | `module` verb (nested via parent structure) | "set up modules", "course outline" |
| HTML pages (syllabus, overviews, lessons) | **API** | `page` verb + CCC kit (`assets/ccc-templates/`) | "post syllabus", "module overview page" |
| Upload files (notes, slides, PDFs) | **API** | `upload` verb (≤400MB simple; resumable beyond) | "post my notes", "share slides" |
| Upload videos + captions | **API** | `video` verb; in-course mp4 topics are the house pattern | "post lecture videos" |
| Link topics (external URL, quiz link) | **API** | link topic, `TopicType: 3` | "link to X in content" |
| Copy a whole course / template | **API** | `setup` verb (Course Copy job; copies UI-only artifacts too) | "make my course like X", "new semester copy" |
| Import a course package (.zip) | **API** | import job (`quiz-import` machinery) | "import this export" |
| Reorder content items | **UI-only** (practically) | PUT-based reorder is fragile; do it in UI, or create in order | "move X above Y" |
| Course homepage/banner/navbar design | **UI-only** | Copy from template course via `setup` | "change the homepage" |
| Make course visible/active | **API** (course offering PUT) | deliberate manual step — never do it as a side effect | "publish the course to students" |

## Assessment

| User wants | Tier | How / workaround | Trigger phrases |
|---|---|---|---|
| Assignments (dropbox folders) with due dates, points, instructions | **API** | `assignment` verb, verified read-back | "create homework", "lab due Friday" |
| Read submissions, download files | **API** | dropbox submissions routes | "who submitted?" |
| Post feedback/scores on submissions | **API** (one trap) | feedback POST; RichText shape must be round-trip verified | "enter my feedback" |
| Quiz shell (name, dates, attempts partly) | **API** | quiz shell POST/PUT (GET-first on PUT) | "create a quiz" |
| Quiz **questions** | **UI-only via import** | **No question CRUD (405 everywhere).** QTI 1.2 package → `quiz-import`; author with `course-video-prep`'s make_qti | "add questions", "build the quiz" |
| Quiz settings (timing, shuffling, special access) | mostly **UI-only** | set in template course and copy; or Claude-in-Chrome | "quiz should shuffle" |
| Rubrics — **create** | **UI-only** | build once in a template course → `setup` copy; attach via API is partial | "add a rubric" |
| Rubrics — read/assess with existing | **API** | rubric assessment routes | "grade with the rubric" |
| Grade items & schemes | **API** (items), scheme partly UI | grades routes; create grade item then link `GradeItemId` | "add to gradebook" |
| Bulk grade upload | **Cannot** (no bulk API) | loop per-student PUTs (scripted, still fast) | "upload all grades" |
| Surveys | **UI-only** (unresearched API) | build in template course and copy | "course survey" |

## Communication & people

| User wants | Tier | How / workaround | Trigger phrases |
|---|---|---|---|
| Announcements (now, scheduled, draft, pinned) | **API — currently broken on this tenant** | `announce` verb is correct per docs, but the tenant 500s on every create (probed 2026-08-16, LE 1.93–1.97). Until the LMS update fixes it: post via UI or Claude-in-Chrome. Reads/deletes work. | "tell the class", "schedule an announcement" |
| Discussions (forums/topics/posts) | **API** | discussion routes (not yet a verb — extend on demand) | "create a discussion board" |
| Calendar events | **API** | calendar routes (not yet a verb) | "add to course calendar" |
| Class roster / enrollments | **API** | classlist + enrollment routes | "who's in my class" |
| Email students | **Cannot** (no per-user email API) | announcement instead; or Claude-in-Chrome via Classlist email UI; or mailto list from roster | "email the class" |
| Intelligent Agents (auto-nudges) | **UI-only** | configure in UI once; or scheduled skill run + announcement | "remind students who haven't..." |
| Groups/sections management | **API** (groups), sections read | group category routes | "make lab groups" |

## Analytics

| User wants | Tier | How / workaround | Trigger phrases |
|---|---|---|---|
| Content completion / progress | **API** | content/completions + user progress routes | "who watched the videos" |
| Quiz/assignment statistics | **API** (basic) | attempts + submissions reads | "how did they do" |
| Full engagement dashboards | **UI-only** (Insights) | pull raw via API and compute; Data Hub needs admin | "engagement report" |

## The rules that protect every write

1. Dry-run first, `--execute` second, `--i-mean-production` on the
   production host only with explicit user confirmation.
2. **200 ≠ landed** — every write verified by independent GET.
3. **PUT deletes omitted fields** — GET → modify → PUT whole object.
4. Course-copy jobs and imports are async — poll to COMPLETE, then verify.
5. Manifest-first for anything bigger than a one-off: map the material to
   `course.json`, run `validate`, fix gaps, then `apply`
   (see `course-manifest.md`).
