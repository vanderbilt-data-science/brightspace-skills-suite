# Quiz authoring reference

## Why these quizzes exist

They are retrieval practice, not gatekeeping. A student watches a 6-12 minute
segment and immediately retrieves the key ideas. The syllabus treats them as
low-stakes ("Low-stakes concept checks", ~10% of grade across the course).
Design for: quick (under 3 minutes), fair (answerable entirely from the
segment), and instructive (feedback teaches).

## The Bloom gate (program assessment-blueprint rule)

Objective items (MC/TF/multi-select) can only evidence **remember /
understand** and light **apply**. They cannot evidence analyze / evaluate /
create — "a multiple-choice question cannot evidence a *create* item" is
called out as the most common blueprint error in course-development.

- Grounded segment with understand-level items in `domain.json`: quiz those
  items directly. The item's `"Mastery means:"` description defines what
  counts as evidence; its `assessment_hint` is a pre-approved question seed.
- Segment whose grounded items are all higher-Bloom (e.g., a demo of
  agent-building, item bloom=create): do NOT pretend to assess mastery.
  Write comprehension questions about the demonstrated process ("What did
  the error in step 2 indicate?", "Why was the prompt restructured?") and
  state in the answer key that the item's real assessment happens in the
  week's assignment.

## Question quality

- 2-4 questions per segment. One per key idea beats four about one idea.
- Scenario > recall where possible: "A prompt is rephrased from X to Y and
  the cost drops. Why?" beats "What is a token?"
- Every distractor is a real misconception a student in this course might
  hold. If you cannot say what confusion an option represents, replace it.
- No "all of the above", no trick negatives, no options distinguishable by
  length or grammar.
- Feedback on wrong answers explains *why it is wrong and what is right*,
  in 1-2 sentences. Feedback on correct answers reinforces the principle.
- For demos: ask about decisions and observations, not incidental details
  ("which button was clicked" is trivia; "why did Jesse start a new chat
  before the second attempt" is understanding).
- Answerable from the segment alone — no outside reading, no other segment.

## questions.json schema (input to scripts/make_qti.py)

```json
{
  "quiz_title": "Check 1 - Tokens and Embeddings",
  "description": "Three questions on Part 1. Feedback appears after each attempt.",
  "questions": [
    {
      "type": "MC",
      "points": 1,
      "text": "A student rewrites a prompt using shorter common words and the token count drops by 30%. What best explains this?",
      "options": [
        { "text": "Common words map to single tokens more often than rare words", "correct": true,
          "feedback": "Right - tokenizers learn frequent character sequences, so common words are usually one token." },
        { "text": "The model compresses shorter prompts automatically", "correct": false,
          "feedback": "The model does not compress input; tokenization happens before the model sees anything." },
        { "text": "Token count depends only on character count", "correct": false,
          "feedback": "Character count correlates loosely, but rare words split into more tokens than common ones of the same length." }
      ]
    },
    {
      "type": "TF",
      "points": 1,
      "text": "Two prompts with the same meaning always cost the same number of tokens.",
      "answer": false,
      "feedback_true": "Phrasing changes tokenization, so equivalent meanings can differ substantially in token count.",
      "feedback_false": "Correct - tokenization follows surface form, not meaning."
    },
    {
      "type": "MS",
      "points": 1,
      "text": "Which of the following are true of embeddings? Select all that apply.",
      "options": [
        { "text": "They are numeric vectors", "correct": true },
        { "text": "Similar meanings land near each other", "correct": true },
        { "text": "Each word has exactly one fixed embedding in a transformer", "correct": false,
          "feedback": "Context changes the representation as it moves through the layers." }
      ]
    }
  ]
}
```

- `type`: `MC` (single correct), `TF`, `MS` (multi-select, all-or-nothing scoring).
- `feedback` on options is optional but strongly encouraged for MC distractors.
- Keep `points` at 1 per question; weighting happens in the gradebook, not here.
- Plain ASCII in all text. HTML tags allowed in `text` (e.g., `<code>`), used sparingly.

## questions.md answer key (instructor review surface)

```markdown
---
quiz: quiz-01-tokens
segment: 01-tokens-and-embeddings
items_assessed: [tokens-embeddings]
generated_by: course-video-prep
status: draft
---
# Check 1 - Tokens and Embeddings

## Q1 (MC) - tokens-embeddings, understand
A student rewrites a prompt using shorter common words...
- [correct] Common words map to single tokens more often...
- Distractor: "the model compresses..." - targets the misconception that the model preprocesses input.
- Distractor: "character count only" - targets surface-level reasoning about cost.
Grounding: segment 00:04:10-00:06:30; domain.json assessment_hint for tokens-embeddings.
```

Every question records: the concept id, Bloom level, why each distractor
exists, and where in the segment the answer was taught. This is what makes
the instructor's review fast — and it is the audit trail when a student
disputes a question.
