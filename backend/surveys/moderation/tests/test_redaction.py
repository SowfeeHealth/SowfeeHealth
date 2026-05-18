import pytest

from surveys.moderation.redaction import redact_pii


# ── helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    import asyncio
    return asyncio.run(coro)


# ── 1. PERSON redaction ───────────────────────────────────────────────────────

def test_person_redacted():
    text, audit = run(redact_pii("John said he was sad"))
    assert "[PERSON_NAME]" in text
    assert "John" not in text
    assert len(audit) == 1
    assert audit[0]["entity_type"] == "PERSON"


# ── 2. PHONE redaction ────────────────────────────────────────────────────────

def test_phone_redacted():
    text, audit = run(redact_pii("Call me at 555-123-4567"))
    assert "[PHONE]" in text
    assert "555-123-4567" not in text
    entry = next(e for e in audit if e["entity_type"] == "PHONE_NUMBER")
    assert entry is not None


# ── 3. EMAIL redaction ────────────────────────────────────────────────────────

def test_email_redacted():
    text, audit = run(redact_pii("Email me at sarah@example.com"))
    assert "[EMAIL]" in text
    assert "sarah@example.com" not in text


# ── 4. Clinical text unchanged ────────────────────────────────────────────────

@pytest.mark.parametrize("clinical_text", [
    "I feel hopeless and want to give up",
    "I haven't slept in three days",
])
def test_clinical_text_unchanged(clinical_text):
    text, audit = run(redact_pii(clinical_text))
    assert text == clinical_text
    assert audit == []


# ── 5. Mental health keywords not misdetected as PII ─────────────────────────

@pytest.mark.parametrize("mh_text", [
    "I want to die",
    "I have suicidal thoughts",
    "I want to hurt myself",
])
def test_mental_health_keywords_preserved(mh_text):
    text, audit = run(redact_pii(mh_text))
    assert text == mh_text, f"String was altered: {mh_text!r} → {text!r}"


# ── 6. Audit log structure ────────────────────────────────────────────────────

def test_audit_log_entry_keys():
    _, audit = run(redact_pii("John said he was sad"))
    required = {"entity_type", "start", "end", "original", "replacement"}
    for entry in audit:
        assert required == entry.keys()


# ── 7. ValueError on unsupported language ─────────────────────────────────────

@pytest.mark.parametrize("lang", ["fr", "zh"])
def test_unsupported_language_raises(lang):
    with pytest.raises(ValueError, match=lang):
        run(redact_pii("some text", language=lang))
