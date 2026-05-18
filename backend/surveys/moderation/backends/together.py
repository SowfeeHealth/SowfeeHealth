import logging
import math
import os
import time

import openai
from openai import AsyncOpenAI

from ..schemas import ClassifierResult, HazardCategory
from .base import ClassifierContext, BackendInvalidOutput, BackendUnavailable


logger = logging.getLogger(__name__)

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
    SENSITIVITY_THRESHOLD = 0.06  # P(unsafe) cutoff for flagging.
    # Llama Guard 4 was fine-tuned with greedy decoding on the first token
    # (safe/unsafe), so default behavior is equivalent to a 0.5 threshold.
    # In mental-health screening we want very high sensitivity: 0.06 catches
    # even subtle distress signals that greedy decoding would suppress.
    # Expect a high Stage 2 call rate — Stage 2 LLM makes the final severity
    # call and will filter out true negatives.

    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["TOGETHER_API_KEY"],
            base_url=self.BASE_URL,
            timeout=10.0,
        )

    async def classify(self, text: str, context: ClassifierContext) -> ClassifierResult:
        # Llama Guard evaluates User text in isolation. Survey question context
        # belongs in Stage 2 LLM, not Stage 1b classifier.
        conversation = f"User: {text}"
        prompt = _LLAMA_GUARD_PROMPT.format(conversation=conversation)
        t0 = time.monotonic()

        try:
            response = await self._client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=64,
                temperature=0,
                logprobs=True,
                top_logprobs=5,
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

        # TEMPORARY DEBUG (disabled — uncomment to re-enable token-format check):
        # Logs raw first-token logprobs to verify Together returns tokens like
        # "unsafe" / " unsafe" / "▁unsafe" / etc. Adjust normalization in
        # _parse_llama_guard_output based on what this shows.
        # try:
        #     _first_token_dbg = response.choices[0].logprobs.content[0]
        #     logger.warning(
        #         "DEBUG llama-guard tokens (top_logprobs=5): %r",
        #         [(item.token, item.logprob) for item in _first_token_dbg.top_logprobs],
        #     )
        # except (AttributeError, IndexError, TypeError) as _dbg_exc:
        #     logger.warning("DEBUG llama-guard logprobs access failed: %s", _dbg_exc)

        flagged, categories, scores = _parse_llama_guard_output(
            response, self.SENSITIVITY_THRESHOLD
        )

        return ClassifierResult(
            flagged=flagged,
            categories=categories,
            confidence=scores["p_unsafe"] if flagged else (1.0 - scores["p_unsafe"]),
            raw_output=f"{response.choices[0].message.content or ''} [scores: {scores}]",
            latency_ms=latency_ms,
            provider="together/llama-guard-4-12b",
        )


def _parse_llama_guard_output(response, threshold: float) -> tuple[bool, list[HazardCategory], dict]:
    """Parse Llama Guard response using first-token logprobs for calibrated threshold.

    Returns:
        (flagged, categories, debug_scores)
        debug_scores: {"p_safe": float, "p_unsafe": float, "threshold": float, ...}
    """
    raw = response.choices[0].message.content or ""

    if not response.choices[0].logprobs or not response.choices[0].logprobs.content:
        raise BackendInvalidOutput("Llama Guard returned no logprobs")

    first_token_data = response.choices[0].logprobs.content[0]
    top_probs = {
        item.token.strip().lower(): math.exp(item.logprob)
        for item in first_token_data.top_logprobs
    }

    p_unsafe = top_probs.get("unsafe", 0.0)
    p_safe = top_probs.get("safe", 0.0)

    debug_scores = {
        "p_safe": p_safe,
        "p_unsafe": p_unsafe,
        "threshold": threshold,
        "top_tokens": {item.token: math.exp(item.logprob) for item in first_token_data.top_logprobs},
    }

    # Custom threshold: flag if P(unsafe) > threshold (more sensitive than greedy 0.5)
    flagged = p_unsafe > threshold

    # Categories: only parse if flagged AND model output indicates unsafe
    # (avoid garbage categories when we override greedy decision)
    categories: list[HazardCategory] = []
    if flagged:
        lines = raw.strip().split("\n")
        if len(lines) >= 2 and lines[0].strip().lower() == "unsafe":
            categories = [
                _CATEGORY_MAP[code]
                for token in lines[1].split(",")
                if (code := token.strip()) in _CATEGORY_MAP
            ]
        # If threshold flagged but model said "safe", no categories.
        # That's fine — categories are nice-to-have, severity comes from Stage 2 LLM.

    return flagged, categories, debug_scores
