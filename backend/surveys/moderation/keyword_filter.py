"""Stage 1c keyword filter.

Substring-matches student text against a curated list of distress
phrases. Runs in parallel with Stage 1a rule engine as backup for
the Stage 1b LLM classifier.

Scope: crisis signals (suicide / self-harm / hopelessness) AND broader
distress signals (self-deprecation, academic distress, social isolation,
emotional exhaustion) appropriate for college mental-health screening.
Severity disambiguation is delegated to Stage 2 LLM assessment.

Sources for keyword list:
- C-SSRS (Columbia Suicide Severity Rating Scale) language patterns
- PHQ-9 Q9 (suicide ideation) common phrasings
- Empirical: phrases Llama Guard 4 missed in Round 10 smoke testing
- Counselor / clinician input on common distress phrasings in
  university student populations
"""
import time

from .schemas import KeywordResult


# Curated list of crisis phrases. Each phrase is a substring match target.
# Phrases are checked case-insensitively. Order does not matter.
#
# Maintenance: when adding new phrases, prefer specificity over generic
# emotional language. "I'm sad" is too broad. "I want to die" is specific.
#
# DO NOT add phrases that match casual idioms ("I could die for some pizza",
# "I'm dying of laughter"). Validate against false-positive eval set (Phase 8).
_CRISIS_KEYWORDS = [
    # Suicide — explicit ideation
    "want to die",
    "wanna die",
    "wish i was dead",
    "wish i were dead",
    "wish i could die",
    "kill myself",
    "killing myself",
    "end my life",
    "ending my life",
    "take my own life",
    "taking my own life",
    "commit suicide",
    "suicidal",
    "suicide note",

    # Self-harm — explicit
    "hurt myself",
    "hurting myself",
    "harm myself",
    "harming myself",
    "cut myself",
    "cutting myself",
    "burn myself",
    "burning myself",

    # Passive ideation / hopelessness (Llama Guard 4 known to miss these)
    "want to give up",
    "wanna give up",
    "give up on life",
    "giving up on life",
    "no point in living",
    "no point living",
    "no reason to live",
    "no reason for living",
    "not worth living",
    "not worth being alive",
    "tired of living",
    "tired of being alive",
    "better off dead",
    "everyone would be better without me",
    "world would be better without me",
    "better off without me",

    # Crisis / breaking point
    "can't go on",
    "cant go on",
    "can't take it anymore",
    "cant take it anymore",
    "can't do this anymore",
    "cant do this anymore",
    "at the end of my rope",
    "nothing left to live for",

    # Plan / means (highest severity signal)
    "have a plan",
    "made a plan to",
    "have the means",

    # Self-deprecation
    "stupid",
    "worthless",
    "loser",
    "I'm a failure",
    "such a failure",
    "hate myself",
    "disappoint everyone",
    "let everyone down",
    "I'm so dumb",
    "I'm an idiot",
    "I'm useless",

    # Academic distress
    "failed",
    "failing classes",
    "failing my classes",
    "failed my classes",
    "can't pass",
    "cant pass",
    "dropping out",
    "drop out",
    "behind in everything",
    "can't keep up",
    "cant keep up",
    "falling apart at school",

    # Social isolation
    "no one cares",
    "everyone hates me",
    "have no friends",
    "all alone",
    "completely alone",
    "nobody likes me",
    "left out",

    # Emotional exhaustion
    "tired of everything",
    "can't take it",
    "cant take it",
    "exhausted",
    "burnt out",
    "burned out",
    "overwhelmed",
    "drowning",
    "suffocating",
    "can't cope",
    "cant cope",
    "breaking down",

    # Hopelessness (mild)
    "no point",
    "what's the point",
    "whats the point",
    "pointless",
    "meaningless",
    "no future",
    "nothing matters",
    "nothing helps",
]


def check_keywords(text: str) -> KeywordResult:
    """Check text against crisis keyword list. Case-insensitive substring match.

    Args:
        text: Student response text (after PII redaction).

    Returns:
        KeywordResult with matched (bool), matched_keywords (list), latency_ms.

    Edge cases:
        - Empty text: matched=False, matched_keywords=[]
        - None or non-string: matched=False (defensive, no crash)
    """
    t0 = time.monotonic()

    if not text or not isinstance(text, str):
        return KeywordResult(
            matched=False,
            matched_keywords=[],
            latency_ms=0,
        )

    text_lower = text.lower()
    matched_keywords = [
        phrase for phrase in _CRISIS_KEYWORDS
        if phrase in text_lower
    ]

    latency_ms = int((time.monotonic() - t0) * 1000)

    return KeywordResult(
        matched=len(matched_keywords) > 0,
        matched_keywords=matched_keywords,
        latency_ms=latency_ms,
    )
