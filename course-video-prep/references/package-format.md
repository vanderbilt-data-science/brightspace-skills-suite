# Package format reference

## Directory layout

```
async-package/
├── manifest.json               # the contract consumed by brightspace-publish
├── segment-plan.md             # human-reviewable plan (approved in Phase 1)
├── overview.html               # "Start here" module page
├── plan.json                   # input given to segment_video.py (kept for reruns)
├── videos/
│   ├── 01-tokens-and-embeddings.mp4
│   └── 02-demo-tokenization.mp4
├── captions/
│   ├── 01-tokens-and-embeddings.vtt
│   └── 02-demo-tokenization.vtt
├── intro-cards/
│   ├── 01-tokens-and-embeddings.png
│   └── 02-demo-tokenization.png
├── quizzes/
│   ├── quiz-01-tokens.questions.md    # instructor-facing answer key
│   ├── quiz-01-tokens.questions.json  # input to make_qti.py (kept for reruns)
│   └── quiz-01-tokens.zip             # QTI 1.2 import package
└── instruments/
    └── quiz-01.md                     # KST instrument (grounded courses only)
```

File naming: two-digit index + kebab-case slug. The index orders items within their type; the authoritative module order is `manifest.json`.

## plan.json (input to scripts/segment_video.py)

```json
{
  "source_video": "/abs/path/GMT20260625-164513_Recording_1920x1080.mp4",
  "source_vtt": "/abs/path/GMT20260625-164513_Recording.transcript.vtt",
  "output_dir": "/abs/path/async-package",
  "course_line": "AI 5001 - Foundations of Generative AI",
  "module_line": "Week 1 - How LLMs Process Text",
  "intro_seconds": 6,
  "segments": [
    {
      "index": 1,
      "slug": "tokens-and-embeddings",
      "title": "Tokens and Embeddings",
      "subtitle": "Part 1 of 4  |  about 9 minutes",
      "bullets": [
        "What a token is and why phrasing changes cost",
        "What an embedding represents"
      ],
      "start": "00:03:15",
      "end": "00:12:40"
    }
  ]
}
```

Notes:
- `start`/`end` accept `HH:MM:SS`, `HH:MM:SS.mmm`, or `MM:SS`.
- `course_line` renders small at the top of the intro card; `title` is the big line; `subtitle` under it; up to 4 `bullets`.
- The script re-encodes cuts (frame-accurate), applies loudness normalization (EBU R128, -16 LUFS) to the content, renders the intro card at source resolution/fps with a silent stereo track, and concatenates. Output goes to `videos/`, `captions/`, `intro-cards/`.
- Caption timestamps are shifted by `intro_seconds` automatically.

## manifest.json (the contract with brightspace-publish)

```json
{
  "package_version": "1.0",
  "generated_by": "course-video-prep",
  "generated_date": "2026-07-05",
  "course": "C1",
  "course_display": "AI 5001 - Foundations of Generative AI",
  "week": 1,
  "grounding": {
    "lecture_md": "/abs/path/course01/week-1/lecture.md",
    "domain_json": "/abs/path/course01/knowledge-space/domain.json"
  },
  "source": {
    "recording": "GMT20260625-164513_Recording_1920x1080.mp4",
    "transcript": "GMT20260625-164513_Recording.transcript.vtt",
    "slides": "session-1.pdf"
  },
  "module": {
    "title": "Week 1 Async - How LLMs Process Text",
    "description": "Recorded lecture in four short parts with concept checks.",
    "items": [
      {
        "type": "html",
        "title": "Start here - this week's async work",
        "file": "overview.html",
        "description": "Overview, time commitment, and how the checks count."
      },
      {
        "type": "video",
        "title": "Part 1 - Tokens and Embeddings (9 min)",
        "file": "videos/01-tokens-and-embeddings.mp4",
        "captions": "captions/01-tokens-and-embeddings.vtt",
        "duration_seconds": 565,
        "concepts": ["tokens-embeddings"],
        "description": "What tokens and embeddings are and why phrasing changes cost."
      },
      {
        "type": "quiz",
        "title": "Check 1 - Tokens and Embeddings",
        "qti": "quizzes/quiz-01-tokens.zip",
        "answer_key": "quizzes/quiz-01-tokens.questions.md",
        "instrument": "instruments/quiz-01.md",
        "concepts": ["tokens-embeddings"],
        "grade": { "points": 3, "category": "Quizzes", "low_stakes": true },
        "description": "Three questions on Part 1. Unlimited attempts, highest kept."
      }
    ]
  }
}
```

Rules:
- `items` order = Brightspace module order. Standard pattern: overview, then video/quiz alternating. A quiz may follow a cluster of two short videos; then list both videos before it and give the quiz both concept ids.
- All paths inside the package are relative to the package root; grounding/source paths may be absolute.
- `grounding` fields are omitted (not null) for ungrounded content, and `course` is the string `"ungrounded"`.
- `grade.low_stakes: true` signals intent (unlimited attempts, small points). The publish skill applies what the import supports and reports what needs manual settings.

## KST instrument file (instruments/quiz-NN.md)

Follows the format in course-development's eval fixtures (`items_assessed` is load-bearing for `kst.py status` coverage):

```markdown
---
instrument: quiz-1
items_assessed: [tokens-embeddings, attention]
items_taught: []
generated: 2026-07-05
generated_by: course-video-prep
status: draft
---
# Check 1: Tokens and embeddings

Three low-stakes questions delivered in Brightspace after async video Part 1.
Source package: <package-dir>. Answer key: quizzes/quiz-01-tokens.questions.md.
```
