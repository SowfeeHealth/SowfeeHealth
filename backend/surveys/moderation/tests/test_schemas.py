import pytest
from pydantic import ValidationError

from surveys.moderation.schemas import (
    CrisisAssessment,
    HazardCategory,
    RuleResult,
    Severity,
    validate_evidence_phrases,
)


def test_severity_is_str_enum():
    assert Severity.HIGH == "high"
    assert Severity.NONE != Severity.HIGH


def test_hazard_category_values():
    assert HazardCategory.SUICIDE_SELF_HARM.value == "S11"
    assert HazardCategory.VIOLENT_CRIMES.value == "S1"


def test_crisis_assessment_confidence_valid():
    a = CrisisAssessment(
        severity=Severity.LOW,
        evidence_phrases=[],
        primary_concern="test",
        counselor_brief="brief",
        confidence=0.5,
        provider="test",
        latency_ms=100,
    )
    assert a.confidence == 0.5


def test_crisis_assessment_confidence_too_high():
    with pytest.raises(ValidationError):
        CrisisAssessment(
            severity=Severity.LOW,
            evidence_phrases=[],
            primary_concern="test",
            counselor_brief="brief",
            confidence=1.5,
            provider="test",
            latency_ms=100,
        )


def test_crisis_assessment_confidence_negative():
    with pytest.raises(ValidationError):
        CrisisAssessment(
            severity=Severity.LOW,
            evidence_phrases=[],
            primary_concern="test",
            counselor_brief="brief",
            confidence=-0.1,
            provider="test",
            latency_ms=100,
        )


def test_validate_evidence_exact_match():
    result = validate_evidence_phrases("I want to hurt myself", ["want to hurt"])
    assert result == ["want to hurt"]


def test_validate_evidence_case_insensitive():
    result = validate_evidence_phrases("i want to hurt myself", ["HURT"])
    assert result == ["HURT"]


def test_validate_evidence_no_match():
    result = validate_evidence_phrases("I feel fine today", ["hurt", "crisis"])
    assert result == []


def test_validate_evidence_empty_phrases():
    result = validate_evidence_phrases("some text", [])
    assert result == []


def test_validate_evidence_substring_match():
    result = validate_evidence_phrases("he is a killer", ["kill"])
    assert result == ["kill"]
