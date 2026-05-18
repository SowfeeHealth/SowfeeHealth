import os
import time

import anthropic

from ..schemas import (
    AssessmentOutput,
    CrisisAssessment,
    Severity,
    validate_evidence_phrases,
)
from ._shared import _RETRY_NUDGE, build_assessment_input_content
from .base import AssessmentContext, BackendInvalidOutput, BackendUnavailable

_ASSESS_TOOL = {
    "name": "submit_crisis_assessment",
    "description": (
        "Submit clinical assessment of a student's mental health survey response. "
        "Always call this tool with your assessment. Do not respond in plain text."
    ),
    "input_schema": AssessmentOutput.model_json_schema(),
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


class AnthropicAssessmentBackend:
    """Stage 2 assessment backend using Anthropic's Claude Sonnet via tool-use.

    Forces structured output by requiring a `submit_crisis_assessment` tool call
    whose `input_schema` is generated from `AssessmentOutput`. Retries once with
    a stronger prompt when evidence_phrases cannot be grounded verbatim in the
    source text; raises `BackendInvalidOutput` on second failure.
    """

    MODEL = "claude-sonnet-4-6"
    MAX_OUTPUT_TOKENS = 1024
    REQUEST_TIMEOUT_SECONDS = 15.0

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"],
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            max_retries=2,
        )

    async def assess(self, text: str, context: AssessmentContext) -> CrisisAssessment:
        t0 = time.monotonic()
        user_content = build_assessment_input_content(text, context)

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
            provider="anthropic/claude-sonnet-4-6",
            latency_ms=latency_ms,
        )

    async def _call_and_extract(self, user_content: str) -> dict:
        try:
            response = await self._client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_OUTPUT_TOKENS,
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
