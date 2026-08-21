# quiz.json — the intermediate quiz format

Same philosophy as `course-manifest.md`: author the quiz as structured
data, **validate for completeness first**, then one command does
generate → import → settings → placement → verify. No UI needed for the
standard path.

```
quiz.json ──► qti.py --validate        ← gaps reported here
    │
    ▼
bscourse.py quiz-publish --ou N --quiz-json quiz.json --module "Module 2"
    │ 1. builds the QTI 1.2 zip (questions)
    │ 2. Course Import API job (the only way questions can enter)
    │ 3. finds the quiz by name, applies settings via shell PUT
    │    (GET→transform→PUT — dates, attempts, time limit, shuffle,
    │     grade linkage, description, active flag)
    │ 4. links it into the module, verifies question count + settings
    ▼
```

## Schema

```json
{
  "quiz": {
    "name": "Module 2 Quiz: Transformer Parts",
    "description": "<p>Low-stakes check on the transformer pipeline.</p>",
    "due":   "2026-09-09T04:59:00.000Z",
    "start": "2026-09-01T12:00:00.000Z",
    "end":   "2026-09-16T04:59:00.000Z",
    "attempts": 2,
    "time_limit_minutes": 20,
    "shuffle": false,
    "grade_item_id": null,
    "is_active": false
  },
  "questions": [
    { "type": "MC", "text": "Which component lets tokens influence each other?",
      "options": [
        { "text": "Attention", "correct": true,
          "feedback": "Right — attention relates every token to every other." },
        { "text": "The tokenizer",
          "feedback": "The tokenizer only splits text into tokens." }
      ] },
    { "type": "TF", "text": "Temperature affects sampling randomness.",
      "answer": true,
      "feedback_true": "Correct.", "feedback_false": "Reconsider — it does." },
    { "type": "MS", "text": "Select every transformer pipeline stage:",
      "options": [
        { "text": "Embedding", "correct": true },
        { "text": "Attention", "correct": true },
        { "text": "Gradient descent",
          "feedback": "That's training, not the inference pipeline." }
      ] },
    { "type": "WR", "text": "Explain in your own words why context length limits what a model can use.",
      "answer_key": "Full credit names the finite window and that anything outside it is invisible to the model. 0-5 anchors: 5 = mechanism plus a consequence; 3 = mechanism only; 1 = restates the prompt.",
      "rows": 12 }
  ]
}
```

Types: `MC` (exactly one correct), `TF` (boolean `answer`), `MS`
(multi-select, all-or-nothing), `WR` (written response / essay). Question
`text` and option `text` may be plain text or HTML. Per-option `feedback`
is shown after answering — low-stakes quizzes should teach, so the
validator warns when feedback is absent.

### `WR` — written response

`WR` carries an open-ended prompt: no options, and **no auto-scoring**.
Brightspace routes it to manual grading, which is the point — an
open-ended prompt cannot be machine-scored, and forcing one into `MC` to
gain auto-grading changes what the question measures. It imports as
Brightspace's Written Response type (Common Cartridge `cc.essay.v0p1`).

| Field | Meaning |
|-------|---------|
| `text` | the prompt (required) |
| `answer_key` | the model answer / score anchors, shown to whoever grades as the question's feedback. Optional, but the validator warns without it — a grader with no key grades inconsistently. |
| `rows` | height of the student's answer box (default `10`) |

Points per WR question are set by the import's default; per-question
point overrides still need the UI (see below). Because nothing is
auto-scored, a quiz containing WR questions will show as needing grading
in Brightspace until the instructor scores it.

## Authoring guidance (for Claude)

- Gather from the user before generating: which module/topic the quiz
  assesses, how many questions, due/availability dates (convert Central
  → UTC), attempts, time limit, graded or practice
  (`grade_item_id`/`is_active`), and the source material to draw
  questions from.
- Write questions against the module's stated objectives, distribute
  across them, and include distractor feedback that names the
  misconception. For `WR`, write the `answer_key` at the same time as the
  prompt — it is the grading standard, not an afterthought.
- Fill in the Blanks, Arithmetic, Significant Figures, Matching, and
  Ordering are **not** supported by this format. They need the UI, or the
  CSV fallback (see below) where it can carry them.
- Show the drafted questions to the user for review BEFORE
  `quiz-publish` — content approval is the user's, always.
- `is_active: false` (default) keeps the quiz invisible to students
  until the instructor flips it.

## What still needs the UI (Claude-in-Chrome fallback)

Question pools/sections, per-question point overrides after import,
random sections, special access beyond the API's SpecialAccessData, and
the newer assessment-experience toggles. Everything else — dates,
attempts, time limit, shuffle, grade linkage, description, active flag —
rides the shell PUT automatically.

## The CSV fallback

For anything QTI cannot carry, Brightspace's Question Library also
accepts a row-key CSV upload (Question Library > Import > Upload a File).
That path is manual — a human uploads the file — so it is a fallback, not
the standard path: QTI import is scripted end to end and should be
preferred whenever the question types allow it.
