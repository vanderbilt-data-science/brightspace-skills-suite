#!/usr/bin/env python3
# VENDORED DUPLICATE — keep in sync with
#   brightspace-course/scripts/qti.py
# These two files are intentionally byte-identical: this skill is standalone
# (it imports nothing from sibling skills), so it carries its own copy of the
# QTI generator. Any fix here MUST be applied there as well.
# Verify with:  md5sum brightspace-course/scripts/qti.py \
#                      course-video-prep/scripts/make_qti.py
"""Build a Brightspace-importable QTI 1.2 package from a quiz JSON file.

Usage: python3 qti.py quiz.json output.zip
       python3 qti.py --validate quiz.json      # check only, no zip

Schema in references/quiz-format.md. Question types:
  MC  - multiple choice, single correct answer
  TF  - true/false
  MS  - multi-select, all-or-nothing scoring
  WR  - written response (essay); not auto-scored, graded manually

Accepts the full quiz.json shape ({"quiz": {settings}, "questions": [...]})
or the legacy course-video-prep shape ({"quiz_title", "questions"}).
The "quiz" settings block is applied by bscourse.py quiz-publish AFTER
import, via the quiz shell PUT (import carries questions; settings ride
the API). Derived from course-video-prep's proven make_qti.py.

Brightspace (D2L) has no quiz-question write API; importing a QTI 1.2
package is the only automatable path. The output zip contains
imsmanifest.xml + quiz.xml in the shape D2L's importer accepts.
"""

import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def mattext(html):
    return f'<material><mattext texttype="text/html"><![CDATA[{html}]]></mattext></material>'


def feedback_block(ident, html):
    return (f'<itemfeedback ident="{ident}">'
            f'<material><mattext texttype="text/html"><![CDATA[{html}]]></mattext></material>'
            f'</itemfeedback>')


def outcomes():
    return ('<outcomes><decvar varname="SCORE" vartype="Decimal" '
            'defaultval="0" minvalue="0" maxvalue="100"/></outcomes>')


def item_title(q, qid):
    """Item titles surface in the quiz editor — use the question text."""
    import re as _re
    t = q.get("title") or _re.sub(r"<[^>]+>", " ", q.get("text", qid))
    return " ".join(t.split())[:80] or qid


def item_metadata(qtype):
    """D2L's converter requires type metadata per item — without it the
    import logs 'Question type not found' and drops every question
    (live-validated 2026-08-16, job 5092)."""
    cc = {"MC": "cc.multiple_choice.v0p1", "TF": "cc.true_false.v0p1",
          "MS": "cc.multiple_response.v0p1", "WR": "cc.essay.v0p1"}[qtype]
    qmd = {"MC": "Multiple Choice", "TF": "True/False",
           "MS": "Multi-Select", "WR": "Written Response"}[qtype]
    return ('<itemmetadata><qtimetadata>'
            f'<qtimetadatafield><fieldlabel>cc_profile</fieldlabel>'
            f'<fieldentry>{cc}</fieldentry></qtimetadatafield>'
            f'<qtimetadatafield><fieldlabel>qmd_questiontype</fieldlabel>'
            f'<fieldentry>{qmd}</fieldentry></qtimetadatafield>'
            '</qtimetadata></itemmetadata>')


def item_mc(q, qid):
    """MC and TF share a shape; TF is MC with fixed True/False options."""
    if q["type"] == "TF":
        options = [
            {"text": "True", "correct": q["answer"] is True,
             "feedback": q.get("feedback_true")},
            {"text": "False", "correct": q["answer"] is False,
             "feedback": q.get("feedback_false")},
        ]
    else:
        options = q["options"]
        if sum(1 for o in options if o.get("correct")) != 1:
            die(f"{qid}: MC needs exactly one correct option")

    labels, feedbacks, conditions = [], [], []
    correct_ident = None
    for i, o in enumerate(options, 1):
        ident = f"{qid}_A{i}"
        labels.append(f'<response_label ident="{ident}">{mattext(escape_html(o["text"]))}'
                      '</response_label>')
        if o.get("correct"):
            correct_ident = ident
        fb = o.get("feedback")
        fb_ref = ""
        if fb:
            fb_id = f"{qid}_FB{i}"
            feedbacks.append(feedback_block(fb_id, escape_html(fb)))
            fb_ref = f'<displayfeedback feedbacktype="Response" linkrefid="{fb_id}"/>'
        score = "100" if o.get("correct") else "0"
        conditions.append(
            f'<respcondition continue="No"><conditionvar>'
            f'<varequal respident="{qid}_RL">{ident}</varequal></conditionvar>'
            f'<setvar varname="SCORE" action="Set">{score}</setvar>{fb_ref}'
            f'</respcondition>')

    return f"""<item ident="{qid}" title={quoteattr(item_title(q, qid))}>
{item_metadata(q["type"])}
<presentation>
{mattext(q_html(q))}
<response_lid ident="{qid}_RL" rcardinality="Single">
<render_choice shuffle="No">
{''.join(labels)}
</render_choice>
</response_lid>
</presentation>
<resprocessing>
{outcomes()}
{''.join(conditions)}
<respcondition continue="No"><conditionvar><other/></conditionvar>
<setvar varname="SCORE" action="Set">0</setvar></respcondition>
</resprocessing>
{''.join(feedbacks)}
</item>"""


def item_ms(q, qid):
    options = q["options"]
    corrects = [i for i, o in enumerate(options, 1) if o.get("correct")]
    if not corrects:
        die(f"{qid}: MS needs at least one correct option")

    labels, feedbacks = [], []
    for i, o in enumerate(options, 1):
        ident = f"{qid}_A{i}"
        labels.append(f'<response_label ident="{ident}">{mattext(escape_html(o["text"]))}'
                      '</response_label>')
        if o.get("feedback"):
            feedbacks.append(feedback_block(f"{qid}_FB{i}", escape_html(o["feedback"])))

    # all-or-nothing: all correct selected AND no incorrect selected
    parts = []
    for i, o in enumerate(options, 1):
        ve = f'<varequal respident="{qid}_RL">{qid}_A{i}</varequal>'
        parts.append(ve if o.get("correct") else f"<not>{ve}</not>")
    win = (f'<respcondition continue="No"><conditionvar><and>{"".join(parts)}</and>'
           f'</conditionvar><setvar varname="SCORE" action="Set">100</setvar>'
           f'</respcondition>')

    return f"""<item ident="{qid}" title={quoteattr(item_title(q, qid))}>
{item_metadata("MS")}
<presentation>
{mattext(q_html(q))}
<response_lid ident="{qid}_RL" rcardinality="Multiple">
<render_choice shuffle="No">
{''.join(labels)}
</render_choice>
</response_lid>
</presentation>
<resprocessing>
{outcomes()}
{win}
<respcondition continue="No"><conditionvar><other/></conditionvar>
<setvar varname="SCORE" action="Set">0</setvar></respcondition>
</resprocessing>
{''.join(feedbacks)}
</item>"""


def item_wr(q, qid):
    """Written Response (essay). No scoring condition awards points: Brightspace
    routes WR to manual grading, which is the point — open-ended prompts cannot
    be machine-scored. The model answer, when supplied as 'answer_key', rides
    along as response feedback so whoever grades sees it in the quiz editor."""
    rows = int(q.get("rows", 10))
    key = q.get("answer_key") or q.get("feedback")
    feedbacks, fb_ref = [], ""
    if key:
        fb_id = f"{qid}_KEY"
        feedbacks.append(feedback_block(fb_id, escape_html(key)))
        fb_ref = f'<displayfeedback feedbacktype="Response" linkrefid="{fb_id}"/>'

    return f"""<item ident="{qid}" title={quoteattr(item_title(q, qid))}>
{item_metadata("WR")}
<presentation>
{mattext(q_html(q))}
<response_str ident="{qid}_RS" rcardinality="Single">
<render_fib fibtype="String" rows="{rows}" columns="80"/>
</response_str>
</presentation>
<resprocessing>
{outcomes()}
<respcondition continue="No"><conditionvar><other/></conditionvar>
<setvar varname="SCORE" action="Set">0</setvar>{fb_ref}</respcondition>
</resprocessing>
{''.join(feedbacks)}
</item>"""


def escape_html(text):
    """Text fields may carry simple HTML; wrap bare text in <p> if no tags."""
    t = str(text)
    return t if "<" in t else escape(t)


def q_html(q):
    t = q["text"]
    return t if t.lstrip().startswith("<") else f"<p>{escape(t)}</p>"


def load_spec(path):
    """Accept new ({"quiz": {...}, "questions": []}) or legacy shape."""
    spec = json.loads(Path(path).read_text())
    quiz = spec.get("quiz", {})
    title = quiz.get("name") or spec.get("quiz_title")
    return title, quiz, spec.get("questions", [])


def validate_spec(path):
    """Return (errors, warnings) — completeness before any import."""
    errors, warnings = [], []
    try:
        title, quiz, questions = load_spec(path)
    except (ValueError, OSError) as e:
        return [f"cannot read {path}: {e}"], []
    if not title:
        errors.append("no quiz name (quiz.name or quiz_title)")
    if not questions:
        errors.append("no questions")
    for n, q in enumerate(questions, 1):
        ctx = f"question {n}"
        t = q.get("type")
        if t not in ("MC", "TF", "MS", "WR"):
            errors.append(f"{ctx}: type must be MC, TF, MS or WR (got {t!r})")
            continue
        if not q.get("text"):
            errors.append(f"{ctx}: no text")
        if t == "WR":
            if not q.get("answer_key"):
                warnings.append(f"{ctx}: WR has no 'answer_key' — the grader will see no "
                                "model answer in Brightspace (it is graded manually either way)")
        elif t == "TF":
            if not isinstance(q.get("answer"), bool):
                errors.append(f"{ctx}: TF needs boolean 'answer'")
        else:
            opts = q.get("options", [])
            if len(opts) < 2:
                errors.append(f"{ctx}: needs at least 2 options")
            ncorrect = sum(1 for o in opts if o.get("correct"))
            if t == "MC" and ncorrect != 1:
                errors.append(f"{ctx}: MC needs exactly 1 correct option "
                              f"(has {ncorrect})")
            if t == "MS" and ncorrect < 1:
                errors.append(f"{ctx}: MS needs at least 1 correct option")
        if t != "WR" \
                and not any(o.get("feedback") for o in q.get("options", [])) \
                and not q.get("feedback_true") and not q.get("feedback_false"):
            warnings.append(f"{ctx}: no answer feedback (low-stakes quizzes "
                            "should teach — consider adding)")
    if quiz:
        for k in ("due", "attempts", "time_limit_minutes"):
            if k not in quiz:
                warnings.append(f"quiz settings: no '{k}' — the shell PUT "
                                "will leave the tenant default")
    else:
        warnings.append("no quiz settings block — import will land with "
                        "D2L defaults (inactive, no dates)")
    return errors, warnings


def build(questions_path, out_zip):
    title, _quiz, questions = load_spec(questions_path)
    spec = {"questions": questions}
    title = title or "Quiz"
    items = []
    for n, q in enumerate(spec["questions"], 1):
        qid = f"QUE_{n}"
        if q["type"] in ("MC", "TF"):
            items.append(item_mc(q, qid))
        elif q["type"] == "MS":
            items.append(item_ms(q, qid))
        elif q["type"] == "WR":
            items.append(item_wr(q, qid))
        else:
            die(f"question {n}: unknown type {q['type']} (use MC, TF, MS, WR)")

    quiz_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<questestinterop>
<assessment ident="ASMT_1" title="{escape(title)}">
<section ident="SECT_1">
{''.join(items)}
</section>
</assessment>
</questestinterop>"""

    # The <schema>/<schemaversion> block is what selects D2L's conversion
    # plugin — omitting it fails the job with "Plugin not found for
    # conversion" (live-validated 2026-08-16, job 5089).
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MAN_1"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<metadata>
  <schema>IMS Content</schema>
  <schemaversion>1.1.3</schemaversion>
</metadata>
<organizations/>
<resources>
  <resource identifier="RES_1" type="imsqti_xmlv1p2" href="quiz.xml">
    <file href="quiz.xml"/>
  </resource>
</resources>
</manifest>"""

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("imsmanifest.xml", manifest)
        z.writestr("quiz.xml", quiz_xml)
    print(f"OK: {len(items)} questions -> {out_zip}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--validate":
        errs, warns = validate_spec(sys.argv[2])
        for e in errs:
            print(f"  ERROR   {e}")
        for w in warns:
            print(f"  warning {w}")
        print("valid" if not errs else f"{len(errs)} error(s)")
        sys.exit(1 if errs else 0)
    if len(sys.argv) != 3:
        die("usage: qti.py quiz.json output.zip | qti.py --validate quiz.json")
    errs, warns = validate_spec(sys.argv[1])
    for w in warns:
        print(f"  warning {w}")
    if errs:
        for e in errs:
            print(f"  ERROR   {e}")
        die("fix the quiz spec before packaging")
    build(sys.argv[1], sys.argv[2])
