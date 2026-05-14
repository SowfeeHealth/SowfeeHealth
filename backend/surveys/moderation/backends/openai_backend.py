import os
import time

import openai
from openai import AsyncOpenAI

from ..schemas import (
    AssessmentOutput,
    CrisisAssessment,
    Severity,
    validate_evidence_phrases,
)
from ._shared import _RETRY_NUDGE, build_assessment_input_content
from .base import AssessmentContext, BackendInvalidOutput, BackendUnavailable

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

Respond with valid JSON matching the required schema.
"""


class OpenAIAssessmentBackend:
    """Stage 2 assessment backend using OpenAI's GPT-4o-mini as failover for Anthropic.

    Uses the SDK's `.beta.chat.completions.parse()` with `response_format` set to
    the `AssessmentOutput` Pydantic class, which guarantees a parsed object
    matching the schema. Retries once with a stronger prompt when
    evidence_phrases cannot be grounded verbatim in the source text; raises
    `BackendInvalidOutput` on second failure.
    """

    MODEL = "gpt-4o-mini"
    MAX_OUTPUT_TOKENS = 1024
    REQUEST_TIMEOUT_SECONDS = 15.0

    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["OPENAI_API_KEY"],
            timeout=self.REQUEST_TIMEOUT_SECONDS,
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
            provider="openai/gpt-4o-mini",
            latency_ms=latency_ms,
        )

    async def _call_and_extract(self, user_content: str) -> dict:
        try:
            response = await self._client.beta.chat.completions.parse(
                model=self.MODEL,
                max_completion_tokens=self.MAX_OUTPUT_TOKENS,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format=AssessmentOutput,
            )
        except openai.APITimeoutError:
            raise BackendUnavailable("OpenAI API timeout")
        except openai.APIConnectionError:
            raise BackendUnavailable("Network error to OpenAI")
        except openai.RateLimitError:
            raise BackendUnavailable("Rate limited by OpenAI")
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise BackendUnavailable(f"OpenAI API error {exc.status_code}")
            raise

        message = response.choices[0].message
        if message.parsed is None:
            raise BackendInvalidOutput(
                f"OpenAI failed to parse structured output. Refusal: {message.refusal!r}"
            )

        return message.parsed.model_dump()
