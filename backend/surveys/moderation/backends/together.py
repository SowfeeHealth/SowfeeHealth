import os
import time

import openai
from openai import AsyncOpenAI

from ..schemas import ClassifierResult, HazardCategory
from .base import ClassifierContext, BackendInvalidOutput, BackendUnavailable

# Maps "S1" → HazardCategory.VIOLENT_CRIMES, etc.
_CATEGORY_MAP: dict[str, HazardCategory] = {cat.value: cat for cat in HazardCategory}

_LLAMA_GUARD_PROMPT = """\
Task: Check if there is unsafe content in 'User' messages in conversations \
according to our safety policy with the categories below.

<BEGIN UNSAFE CONTENT CATEGORIES>
S1: Violent Crimes.
S2: Non-Violent Crimes.
S3: Sex Crimes.
S4: Child Sexual Exploitation.
S5: Defamation.
S6: Specialized Advice.
S7: Privacy.
S8: Intellectual Property.
S9: Indiscriminate Weapons.
S10: Hate.
S11: Suicide & Self-Harm. This category includes:
  - Explicit self-harm: direct statements of intent, methods, or plans
  - Implicit self-harm and passive suicidal ideation (equally significant
    in mental-health screening contexts):
    * Hopelessness ("I feel hopeless", "I see no way out")
    * Wishes for non-existence ("I want to give up", "I'm tired of living")
    * Despair markers ("Nothing matters", "I can't go on")
    * Passive ideation ("I wish I wouldn't wake up")
  - Affirmative responses to direct screening questions about self-harm
    (e.g., answering "yes" to "do you have thoughts of hurting yourself?")
S12: Sexual Content.
S13: Elections.
S14: Code Interpreter Abuse.
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>
{conversation}
<END CONVERSATION>

Provide your safety assessment for ONLY THE LAST User in the above conversation:
- First line must read 'safe' or 'unsafe'.
- If unsafe, a second line must include a comma-separated list of violated categories."""


class TogetherClassifierBackend:
    MODEL = "meta-llama/Llama-Guard-4-12B"
    BASE_URL = "https://api.together.xyz/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["TOGETHER_API_KEY"],
            base_url=self.BASE_URL,
            timeout=10.0,
        )

    async def classify(self, text: str, context: ClassifierContext) -> ClassifierResult:
        question = context.get("question_text", "")
        if question:
            conversation = f"Agent: {question}\nUser: {text}"
        else:
            conversation = f"User: {text}"

        prompt = _LLAMA_GUARD_PROMPT.format(conversation=conversation)
        t0 = time.monotonic()

        try:
            response = await self._client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=64,
                temperature=0,
            )
        except openai.APITimeoutError:
            raise BackendUnavailable("Together API timeout")
        except openai.APIConnectionError:
            raise BackendUnavailable("Network error to Together")
        except openai.RateLimitError:
            raise BackendUnavailable("Rate limited by Together")
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise BackendUnavailable(f"Together API error {exc.status_code}")
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_output = response.choices[0].message.content or ""

        flagged, categories = _parse_llama_guard_output(raw_output)

        return ClassifierResult(
            flagged=flagged,
            categories=categories,
            confidence=0.85 if flagged else 0.95,
            raw_output=raw_output,
            latency_ms=latency_ms,
            provider="together/llama-guard-4-12b",
        )


def _parse_llama_guard_output(raw: str) -> tuple[bool, list[HazardCategory]]:
    lines = raw.strip().split("\n")
    first = lines[0].strip().lower()

    if first == "safe":
        return False, []

    if first == "unsafe":
        if len(lines) < 2:
            return True, []
        categories = [
            _CATEGORY_MAP[code]
            for token in lines[1].split(",")
            if (code := token.strip()) in _CATEGORY_MAP
        ]
        return True, categories

    raise BackendInvalidOutput(
        f"Llama Guard returned unexpected output: {raw!r}"
    )
