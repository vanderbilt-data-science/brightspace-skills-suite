# Valence API quick reference (the parts this skill uses)

Distilled from the brightspace-skills lab's `reference/api/` docs (full
detail + sources there). LP `1.57`, LE `1.93` — discover live versions via
`GET /d2l/api/versions/`.

## RichText

- Write bodies take **RichTextInput** `{"Content": "<p>…</p>", "Type": "Html"}`.
- GET returns **RichText** `{Text, Html}` — never echo it back into a
  write; convert first.

## Content

- Root modules: `GET/POST /d2l/api/le/{v}/{ou}/content/root/`
- Module children: `GET/POST .../content/modules/{id}/structure/`
- Module JSON: `Type: 0`; topic JSON: `Type: 1` with `TopicType`
  (1=file, 3=link) — full shapes in `bscourse.py`.
- File topic + bytes in one call: POST to `.../structure/` with
  `multipart/mixed` (part 1 topic JSON, part 2 file with
  `Content-Disposition: attachment`). The topic `Url` must be
  `/content/enforced/{ou}-{orgCode}/{filename}` (org code from
  `GET /d2l/api/lp/{v}/courses/{ou}` → `Code`).
- Simple upload cap ~488MB; beyond that use the resumable protocol
  (`POST .../content/resumable/`, chunked PUTs with `Content-Range`,
  expect `308` per chunk).

## Course Copy (template setup)

- `POST /d2l/api/le/{v}/import/{DEST_ou}/copy/` body
  `{"SourceOrgUnitId": N, "Components": [...]|omit, "DaysToOffsetDates": N}`
  (or `HoursToOffsetDates` / `OffsetByStartDateDifference` — exactly one).
- Returns `{JobToken}`; poll `GET .../copy/{jobToken}` →
  `PENDING|PROCESSING|COMPLETE|FAILED|CANCELLED`.
- Component names include `Content, Grades, Discussions, Dropbox, Quizzes,
  Rubrics, Schedule, Groups, Navbars, Homepages, News, Surveys` —
  spelling not fully verified on-tenant; omit to copy everything.

## Assignments (dropbox)

- `GET/POST /d2l/api/le/{v}/{ou}/dropbox/folders/`,
  `GET/PUT/DELETE .../folders/{id}`.
- POST body essentials: `Name`, `CustomInstructions` (RichTextInput),
  `DueDate` (UTC ISO-8601|null), `DropboxType: 2` (individual),
  `SubmissionType: 0` (file), `CompletionType: 0`,
  `Assessment: {ScoreDenominator: N}`, `GradeItemId` (link to an existing
  grade item; create it first via `06-grades.md` routes).
- `DisplayInCalendar: true` requires at least one date.
- Round-trip PUTs must strip read-only counters (`TotalFiles`,
  `TotalUsers*`, …).

## Quizzes

- Shell CRUD works; **question CRUD is 405 everywhere** — questions enter
  only via package import:
  `POST /d2l/api/le/{v}/import/{ou}/imports/` (multipart/form-data, field
  `file`, QTI 1.2 / D2L package zip) → `{JobToken}`; poll
  `GET .../imports/{jobToken}` until `COMPLETED`/`IMPORTFAILED`
  (`.../logs/` for details).
- Find the quiz after import: `GET /d2l/api/le/{v}/{ou}/quizzes/`, match
  `Name`. Link into content with a `TopicType: 3` topic pointing at
  `/d2l/lms/quizzing/user/quiz_summary.d2l?qi={quizId}&ou={ou}`.

## Announcements (news)

- `GET/POST /d2l/api/le/{v}/{ou}/news/`; body `NewsItemData`
  (`Title`, `Body` RichTextInput, `StartDate` future ⇒ scheduled,
  `IsPublished: false` ⇒ draft; drafts publish via
  `POST .../news/{id}/publish`, and published can't revert to draft).
- **Live-validated 2026-08-16 (Vanderbilt prod, LMS w/ LE 1.97):** the
  create body is NOT RichTextInput — `Body` takes the **RichText** shape
  `{Text, Html}` (same anomaly as dropbox feedback), `StartDate` is
  **required**, all boolean fields + `EndDate`/`SortOrder` keys must be
  present, and the POST must be `multipart/mixed`. Anything else ⇒ 400.
- **KNOWN TENANT BUG (2026-08-16):** even the fully documented body ⇒
  **500 Internal Server Error** on every LE version 1.93–1.97, JSON and
  multipart alike. News create is currently broken server-side on this
  tenant; GET/DELETE work. Fallback: post announcements via the UI or
  Claude-in-Chrome. Re-probe after the next LMS monthly update.

## Auth traps (live-validated)

- Expired cookies ⇒ `/d2l/lp/auth/xsrf-tokens` returns **200 with empty
  referrerToken** (not 401).
- The minted JWT claims `*:*:*` but per-resource scope grants still apply;
  one 403 family ≠ broken auth.
- JWT ~1h; session cookies hours–days; re-mint per run, serialize
  re-mints.

## Known API gaps (browser/UI only)

Rubric creation, quiz-question editing, most quiz settings, Intelligent
Agents, per-user email, bulk grade upload (loop per-student instead).
Preferred workaround: have them pre-built in the template course and use
Course Copy.
