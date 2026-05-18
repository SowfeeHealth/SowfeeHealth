from .base import AssessmentContext


_RETRY_NUDGE = (
    "\n\nIMPORTANT: evidence_phrases must appear WORD-FOR-WORD in "
    "student_response. Re-extract phrases that literally exist in the text."
)


def build_assessment_input_content(text: str, context: AssessmentContext) -> str:
    """Build XML-tagged structured input for Stage 2 assessment.

    Stage 2 input is strictly text + question_text. Likert data and
    rule scores are intentionally excluded — those are Stage 1a's
    responsibility. Stage 2 LLM evaluates student text in isolation.
    """
    sections = [
        "<task>Assess this student's mental health survey response.</task>"
    ]

    if question := context.get("question_text"):
        sections.append(f"<question_asked>{question}</question_asked>")

    sections.append(f"<student_response>{text}</student_response>")

    return "\n\n".join(sections)
