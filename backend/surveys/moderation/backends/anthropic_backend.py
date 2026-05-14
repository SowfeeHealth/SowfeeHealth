import json
import os
import time

import anthropic

from ..schemas import (
    CrisisAssessment,
    LikertResponse,
    LikertSummary,
    Severity,
    validate_evidence_phrases,
)
from .base import AssessmentContext, BackendInvalidOutput, BackendUnavailable

_ASSESS_TOOL = {
    "name": "submit_crisis_assessment",
    "description": (
        "Submit clinical assessment of a student's mental health survey response. "
        "Always call this tool with your assessment. Do not respond in plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "description": "Overall clinical severity. Use 'high' for explicit self-harm.",
            },
            "evidence_phrases": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
                "description": (
                    "Verbatim phrases from student_response that justify the severity. "
                    "MUST appear word-for-word in student_response. Do not paraphrase. "
                    "Empty list if severity is 'none'."
                ),
            },
            "primary_concern": {
                "type": "string",
                "enum": [
                    "suicide_self_harm", "depression", "anxiety", "trauma",
                    "substance_use", "interpersonal", "academic_stress",
                    "other", "none",
                ],
                "description": "The primary clinical category of concern.",
            },
            "counselor_brief": {
                "type": "string",
                "maxLength": 600,
                "description": (
                    "One-paragraph clinical summary for counselor. "
                    "Focus on clinically actionable info. Non-jargon language."
                ),
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in this assessment, 0.0-1.0.",
            },
        },
        "required": [
            "severity", "evidence_phrases", "primary_concern",
            "counselor_brief", "confidence",
        ],
    },
}

_SYSTEM_PROMPT = """\
You are a clinical assistant for a university mental-health screening
system. You assess student survey responses for risk indicators.

You will receive structured input with XML-tagged sections:
- <task>: brief description of what to do
- <question_asked>: the question the student was answering (context)
- <student_response>: the text the student wrote (primary thing to assess)
- <likert_summary>: scoring rubric or instrument indicator
- <stage_1_rule_scores>: pre-computed category scores from rule engine
- <likert_responses>: detailed list of Likert questions with fields:
    * question: the question text
    * answer_choices: mapping of numeric values to text labels
    * category: institution-tagged category
    * answer: the numeric value the student chose
  Look up answer_choices[answer] to find the student's selection label.

Integrate all signals. The student_response is primary; Likert and
rule_scores provide clinical context.

Evidence phrases must be quoted verbatim from student_response. Do not
paraphrase. PII tokens like [PERSON_REDACTED] are intentional.

Always submit your assessment via the submit_crisis_assessment tool.
"""

_RETRY_NUDGE = (
    "\n\nIMPORTANT: evidence_phrases must appear WORD-FOR-WORD in "
    "student_response. Re-extract phrases that literally exist in the text."
)


class AnthropicAssessmentBackend:
    MODEL = "claude-haiku-4-5"

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"],
            timeout=15.0,
        )

    async def assess(self, text: str, context: AssessmentContext) -> CrisisAssessment:
        t0 = time.monotonic()
        user_content = self._build_input_content(text, context)

        tool_input = await self._call_and_extract(user_content)
        valid_phrases = validate_evidence_phrases(text, tool_input["evidence_phrases"])

        if len(valid_phrases) < len(tool_input["evidence_phrases"]):
            tool_input = await self._call_and_extract(user_content + _RETRY_NUDGE)
            valid_phrases = validate_evidence_phrases(text, tool_input["evidence_phrases"])
            if len(valid_phrases) < len(tool_input["evidence_phrases"]):
                raise BackendInvalidOutput(
                    "Evidence phrases not grounded in source text after retry: "
                    f"{tool_input['evidence_phrases']!r}"
                )

        try:
            severity = Severity(tool_input["severity"])
        except ValueError:
            raise BackendInvalidOutput(
                f"Invalid severity: {tool_input['severity']!r}"
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        return CrisisAssessment(
            severity=severity,
            evidence_phrases=valid_phrases,
            primary_concern=tool_input["primary_concern"],
            counselor_brief=tool_input["counselor_brief"],
            confidence=tool_input["confidence"],
            provider="anthropic/claude-haiku-4-5",
            latency_ms=latency_ms,
        )

    async def _call_and_extract(self, user_content: str) -> dict:
        try:
            response = await self._client.messages.create(
                model=self.MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=[_ASSESS_TOOL],
                tool_choice={"type": "tool", "name": "submit_crisis_assessment"},
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APITimeoutError:
            raise BackendUnavailable("Anthropic API timeout")
        except anthropic.APIConnectionError:
            raise BackendUnavailable("Network error to Anthropic")
        except anthropic.RateLimitError:
            raise BackendUnavailable("Rate limited by Anthropic")
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise BackendUnavailable(f"Anthropic API error {exc.status_code}")
            raise

        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_crisis_assessment":
                return block.input

        raise BackendInvalidOutput(
            "No submit_crisis_assessment tool_use block in response"
        )

    def _build_input_content(self, text: str, context: AssessmentContext) -> str:
        """Build XML-tagged structured input. Simple strings go directly inside
        tags; complex data (lists/dicts) is JSON-serialized inside tags."""
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
