# Page templates — choosing a look (CCC is optional)

Content pages (syllabus, module overviews, lessons) can follow a house
style or none at all. The choice is per course, set once as
`course.template` in `course.json` (or `--profile` on `validate`/`apply`).
**There is no default house style — `none` unless you pick one.**

| `course.template` | What it means | Kit files | Validator checks |
|---|---|---|---|
| `none` (default) | Raw HTML you (or Claude) write freely. No house style. | — | files exist, placeholders resolved |
| `plain` | Neutral, unbranded, CDN-free pages — clean semantic HTML that inherits the tenant's theme. | `assets/plain-templates/` | above + module-overview good-practice hint |
| `ccc` | The Vanderbilt **CCC Online Programs** kit (hero banner, branded callouts, D2L Courseware V5 assets). | `assets/ccc-templates/` | above + CCC shared-asset `<head>` required on kit pages |
| `custom:<path>` | Your own kit directory. | your files | files exist, placeholders resolved |

Switching is one line in the manifest; nothing else changes. A course that
sets no `template` gets `none` and is never nagged about CCC or overview
pages.

## How Claude authors a page (any template)

1. Look at `course.template`. Copy the matching template file from the kit
   directory (`plain-templates/` or `ccc-templates/`), or start from clean
   HTML for `none`/custom.
2. Fill every `[placeholder]` from the user's material; delete sections
   that don't apply rather than leaving brackets (the validator blocks on
   unresolved `[...]`).
3. Publish with `bscourse.py page --ou N --module "..." --file page.html`
   (or via the manifest `pages` list), then spot-check rendering.

## The kits

- **plain** (`assets/plain-templates/`): `syllabus.html`,
  `module-overview.html`, `page.html`. Self-contained, no external
  requests, safe on any D2L tenant. Good default for anyone who just wants
  clean, consistent pages.
- **ccc** (`assets/ccc-templates/`): the full CCC page set. Details and the
  per-type skeletons live in `template-setup.md`. Use for CCC Online
  Programs courses (and note it was built for graduate online courses —
  adapt wording for in-person/undergrad, as the AI 1010 build did).

## Best-practice guidance (template-independent)

Whatever the look, these hold: lead each module with an overview page
stating objectives and activities; map pages to course outcomes; keep a
consistent structure across modules so students learn the rhythm; and
write student-facing prose, not instructor shorthand. The `plain` and
`ccc` kits bake these in; with `none` you supply them yourself.
