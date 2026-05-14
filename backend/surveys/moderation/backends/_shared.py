import json

from .base import AssessmentContext


_RETRY_NUDGE = (
    "\n\nIMPORTANT: evidence_phrases must appear WORD-FOR-WORD in "
    "student_response. Re-extract phrases that literally exist in the text."
)


def build_assessment_input_content(text: str, context: AssessmentContext) -> str:
    """Build XML-tagged structured input for Stage 2 assessment.

    Simple strings go directly inside tags; complex data (lists/dicts) is
    JSON-serialized inside tags.

    Shared by AnthropicAssessmentBackend and OpenAIAssessmentBackend.
    """
    sections = [
        "<task>Assess this student's mental health survey response.</task>"
    ]

    if question := context.get("question_text"):
        sections.append(f"<question_asked>{question}</question_asked>")

    sections.append(f"<student_response>{text}</student_response>")

    if likert_summary := context.get("likert_summary"):
        sections.append(
            f"<likert_summary>\n{likert_summary.model_dump_json(indent=2)}\n</likert_summary>"
        )

    if rule_scores := context.get("rule_scores"):
        sections.append(
            f"<stage_1_rule_scores>\n{json.dumps(rule_scores, indent=2)}\n</stage_1_rule_scores>"
        )

    if likert_responses := context.get("likert_responses"):
        items_json = json.dumps(
            [r.model_dump() for r in likert_responses],
            indent=2,
        )
        sections.append(f"<likert_responses>\n{items_json}\n</likert_responses>")

    return "\n\n".join(sections)
