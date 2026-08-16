# Brightspace API notes (distilled, live-validated where marked)

Condensed from the research lab at
the Valence API reference (11 API
docs + `vu-brightspace-analysis.md`, which analyzed a toolkit run against the
live Vanderbilt tenant). Go there for full detail.

## Auth: session cookies -> JWT bearer

Vanderbilt grants faculty no OAuth app registration; the working pattern
mints a token from a real browser session:

1. Hold valid session cookies (`d2lSessionVal` etc.) — ours come from the
   playwright-skill `storage_state.json`.
2. `GET https://{host}/d2l/lp/auth/xsrf-tokens` -> `{"referrerToken": "..."}`
3. `POST https://{host}/d2l/lp/auth/oauth2/token` with the cookies, header
   `X-Csrf-Token: {referrerToken}`, form body `scope=*:*:*`
4. Response `access_token` is a JWT valid ~1 hour. Use as
   `Authorization: Bearer ...` against `https://{host}/d2l/api/...`.

**Traps (validated):**
- Expired cookies => the XSRF endpoint returns **HTTP 200 with an empty
  referrerToken**, not 401. Detect the empty token explicitly.
- The JWT claims `scope: *:*:*` but the tenant still enforces per-resource
  scope grants — a 403 "No scopes defined" on one endpoint family does not
  mean auth is broken overall.
- Session cookies last hours-days; the JWT ~1h. Re-mint per run; serialize
  re-mints if parallelizing.

## Routes and versions

- Discover versions: `GET /d2l/api/versions/`. Known-good: LP `1.57`,
  LE `1.92`/`1.93`.
- Learning Platform (users, enrollments): `/d2l/api/lp/{ver}/...`
- Learning Environment (content, quizzes): `/d2l/api/le/{ver}/...`
- Whoami: `GET /d2l/api/lp/{ver}/users/whoami`
- My courses: `GET /d2l/api/lp/{ver}/enrollments/myenrollments/?orgUnitTypeId=3`
  (paged via `Bookmark`; each item has `OrgUnit.Id` = the `ou`).

## Content (modules and topics) — validated working

- Course content root: `GET/POST /d2l/api/le/{ver}/{ou}/content/root/`
- Create module: POST to root (or to a parent module's `/structure/`) with:
  ```json
  {"Title": "...", "ShortTitle": "...", "Type": 0,
   "ModuleStartDate": null, "ModuleEndDate": null, "ModuleDueDate": null,
   "IsHidden": false, "IsLocked": false, "Description": {"Html": "..."}}
  ```
  (`Type: 0` = module, `Type: 1` = topic.)
- Create a **file topic with upload** in one call: POST
  `/d2l/api/le/{ver}/{ou}/content/modules/{moduleId}/structure/` with
  `Content-Type: multipart/mixed; boundary=...`:
  - part 1: `application/json` — topic JSON:
    ```json
    {"Title": "...", "ShortTitle": "...", "Type": 1, "TopicType": 1,
     "Url": "/content/enforced/{ou}-{orgCode}/{filename}",
     "StartDate": null, "EndDate": null, "DueDate": null,
     "IsHidden": false, "IsLocked": false, "IsExempt": false,
     "Description": {"Html": "..."}}
    ```
  - part 2: the file bytes with its own Content-Type and
    `Content-Disposition: attachment; filename="..."`.
  The `Url` must point inside the course's enforced content space. Get the
  org code from `GET /d2l/api/lp/{ver}/courses/{ou}` (`Code` field), or use
  the path segment other topics in the course already use.
- **Link topic** (used to place a quiz in the module): same POST with
  `"TopicType": 3` and `"Url"` set to the quiz's user URL
  (`/d2l/lms/quizzing/user/quiz_summary.d2l?qi={quizId}&ou={ou}`).
- Simple upload limit ~488 MB. Bigger: resumable protocol —
  `POST /d2l/api/le/{ver}/{ou}/content/resumable/` style flow with
  `X-Upload-Content-Type` / `X-Upload-Content-Length` headers, then chunked
  PUTs with `Content-Range`, expecting `308 Resume Incomplete` per chunk;
  finish by POSTing the resulting file key to the module structure. See
  `reference/api/03-content.md` for the exact sequence.
- Real-world confirmation: the CS 6315 course archive contained 99 mp4
  lecture videos served as ordinary content file topics — video hosting in
  Brightspace-native content is the house pattern (no Kaltura/Panopto).

## Quizzes — the hard constraints (validated)

- Quiz **shell** create/update: works via API.
- Quiz **question** CRUD: **405 on every LE version tried.** Questions enter
  only via course import: QTI 1.2 / IMS package to
  `POST /d2l/api/le/{ver}/import/{ou}/imports/` (multipart/form-data, field
  name `file`). Response gives a `JobToken`; poll
  `GET /d2l/api/le/{ver}/import/{ou}/imports/{jobToken}` until
  `Status` is `IMPORTFAILED` or complete.
- After import, find the quiz: `GET /d2l/api/le/{ver}/{ou}/quizzes/` (paged),
  match by `Name`. Import may land questions in the Question Library and/or
  create the quiz depending on package shape — verify and report which.
- Quiz settings (attempts, grade association) are typically post-import UI
  work; some are settable via quiz shell PUT (GET first — see PUT trap).

## Write-safety invariants (learned the hard way)

1. **PUT deletes omitted fields.** Always GET -> modify -> PUT whole object.
   The "q01 incident": a partial PUT severed a live quiz->gradebook link.
2. **200 != landed.** Dropbox feedback (and others) return 200 while
   silently dropping a malformed RichText body. Independent GET read-back
   after every write; compare the field you set.
3. No bulk grade API (per-student PUT loop); no rubric-creation API
   (UI-only); no per-user email API; Intelligent Agents UI-only.

## Tenant facts

- Production: `brightspace.vanderbilt.edu`, SAML SSO + Duo, student
  RoleId = 110.
- All development against the test tenant per the lab's safety rules;
  production writes only with explicit user confirmation.
