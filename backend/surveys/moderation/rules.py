"""Stage 1a Likert rule engine.

Aggregates per-category Likert scores and applies institution-configured
FlaggingRules. Returns a RuleResult indicating flag status and severity.

No LLM, no external API. Pure deterministic Python.

Rule types supported:
- any_question: wildcard — any individual answer across ALL categories
    vs threshold (rule.category is ignored for this type).
- sum: category total sum vs threshold
- average: category mean vs threshold

Multiple rules combine via OR (any rule triggered → flagged=True).
Suggested severity = highest severity among triggered rules.
"""
import time
from collections import defaultdict

from .schemas import (
    FlaggingRule,
    LikertResponse,
    RuleResult,
    Severity,
)


_SEVERITY_PRIORITY = [
    Severity.NONE,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
]


def compute_rule_scores(
    likert_responses: list[LikertResponse],
    rules: list[FlaggingRule],
) -> RuleResult:
    """Aggregate Likert scores by category and evaluate institution rules.

    Args:
        likert_responses: Student's Likert answers.
        rules: Institution-configured flagging rules.

    Returns:
        RuleResult with:
            - category_scores: sum per category (for display / debug)
            - triggered_rules: descriptions of fired rules
            - flagged: True if any rule triggered
            - suggested_severity: highest severity among triggered, or 'none'
            - latency_ms: wall-clock duration of this computation

    Edge cases:
        - Empty likert_responses: category_scores={}, flagged=False, severity='none'
        - Empty rules: scores computed but no rules to evaluate
        - Rule references category with no Likert responses: rule skipped (no crash)
        - Unknown rule_type: rule skipped (no crash)
    """
    t0 = time.monotonic()

    by_category: dict[str, list[int]] = defaultdict(list)
    for response in likert_responses:
        by_category[response.category].append(response.answer)

    category_scores: dict[str, int] = {
        cat: sum(answers) for cat, answers in by_category.items()
    }

    # Wildcard pool for any_question rules: all Likert answers across categories.
    # Built once outside the loop and reused per any_question rule.
    all_answers: list[int] = [
        ans for cat_answers in by_category.values()
        for ans in cat_answers
    ]

    triggered_rules: list[str] = []
    triggered_severities: list[Severity] = []

    for rule in rules:
        # any_question is wildcard across all categories; rule.category is ignored.
        if rule.rule_type == "any_question":
            answers = all_answers
        else:
            answers = by_category.get(rule.category, [])

        if not answers:
            continue

        if _evaluate_rule(rule, answers):
            description = rule.description or (
                f"{rule.category} {rule.rule_type} {rule.comparison} {rule.threshold}"
            )
            triggered_rules.append(description)
            triggered_severities.append(rule.severity)

    if triggered_severities:
        suggested_severity = max(
            triggered_severities,
            key=lambda s: _SEVERITY_PRIORITY.index(s),
        )
    else:
        suggested_severity = Severity.NONE

    latency_ms = int((time.monotonic() - t0) * 1000)

    return RuleResult(
        flagged=len(triggered_rules) > 0,
        category_scores=category_scores,
        triggered_rules=triggered_rules,
        suggested_severity=suggested_severity,
        latency_ms=latency_ms,
    )


def _evaluate_rule(rule: FlaggingRule, answers: list[int]) -> bool:
    """Evaluate a single rule against an answers list. Returns True if triggered.

    For any_question rules, `answers` is the wildcard pool (all categories).
    For sum/average rules, `answers` is the category-scoped list.
    """
    if rule.rule_type == "any_question":
        if rule.comparison == "gte":
            return any(a >= rule.threshold for a in answers)
        else:
            return any(a <= rule.threshold for a in answers)

    elif rule.rule_type == "sum":
        score = sum(answers)
        if rule.comparison == "gte":
            return score >= rule.threshold
        else:
            return score <= rule.threshold

    elif rule.rule_type == "average":
        avg = sum(answers) / len(answers)
        if rule.comparison == "gte":
            return avg >= rule.threshold
        else:
            return avg <= rule.threshold

    else:
        return False
