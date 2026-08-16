# rubric.json — the intermediate rubric format

Rubric **creation and attachment have no API** (confirmed through LE
1.93+). The pipeline keeps them safe anyway: author as structured data,
validate, preview to the user, let Claude-in-Chrome (or the user) do the
UI entry from an exact step plan, then **verify by API read-back** —
write-verify discipline even when the write is a browser.

```
rubric.json ──► rubric.py validate      ← completeness gate
      │
      ▼         rubric.py preview       ← markdown table; user approves
      │
      ▼         rubric.py entry-plan    ← exact UI steps
      │            └── Claude-in-Chrome drives Course Admin → Rubrics
      ▼
      rubric.py verify rubric.json --ou N
                   └── GET dropbox folder → Assessment.Rubrics[] must
                       contain the rubric on every associate target
```

## Schema

```json
{
  "name": "AI 1010 Lab Rubric",
  "type": "analytic",              // analytic (grid) | holistic
  "scoring": "points",             // points | custom-points | text-only
  "levels": [                      // grid columns, best first
    { "name": "Excellent",  "points": 4 },
    { "name": "Proficient", "points": 3 },
    { "name": "Developing", "points": 2 },
    { "name": "Beginning",  "points": 1 }
  ],
  "criteria": [                    // grid rows
    { "name": "Diagnosis quality",
      "descriptions": [            // one cell per level, same order
        "Pinpoints the failure and names the mechanism behind it.",
        "Identifies the failure correctly; mechanism partly explained.",
        "Notices something is wrong but misattributes the cause.",
        "No meaningful diagnosis." ] }
  ],
  "overall_levels": [              // optional Overall Score band
    { "name": "Meets expectations", "range_min": 3,
      "description": "Ready for the next lab." },
    { "name": "Revise and resubmit", "range_min": 0,
      "description": "See criterion feedback." }
  ],
  "associate": [                   // where to attach it
    { "tool": "Dropbox", "title": "Lab 1: Prompt Refinement" }
  ]
}
```

## Authoring guidance (for Claude)

Gather from the user before drafting — and ask if missing:
1. What assignment(s) it grades (→ `associate`, exact folder titles).
2. The criteria (what dimensions matter) — derive from the assignment's
   instructions/objectives if the user hasn't listed them, then confirm.
3. Level count and point scheme (departmental default? out-of total that
   must match the assignment's `out_of`?).
4. Tone of cell descriptions (student-facing! write them as feedback the
   student reads, not grader shorthand).

The validator enforces cell/level alignment and warns on empty cells.
Always `preview` to the user and get approval before any UI entry.

## Alternatives when Chrome entry isn't wanted

- **Template copy:** build the rubric once in a master/template course
  and `setup --components Rubrics,Dropbox` — associations copy when the
  dropbox comes along in the same copy job.
- **Course package import:** a D2L export zip containing rubrics imports
  via the import API (hand-crafting that XML is undocumented — export a
  real one).

## Grading with a rubric (API — works!)

Unlike creation, **rubric assessment is writable**:
`PUT /d2l/api/le/{v}/{ou}/assessment?objectType=Dropbox&objectId={folderId}&userId={id}`
with a `RubricAssessment` body, and `RubricAssessments[]` rides the
dropbox feedback POST. The grading skill uses this to fill scored rubrics
per student.
