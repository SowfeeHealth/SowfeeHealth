from typing import TYPE_CHECKING

from ..schemas import FlaggingRule
from .base import AssessmentBackend, ClassifierBackend

if TYPE_CHECKING:
    from ..pipeline import ModerationPipeline


def get_classifier(tenant) -> ClassifierBackend:
    """Return the ClassifierBackend (Llama Guard 4 via Together.ai).

    v1 always uses the API backend. Phase 9 will add
    Institution.inference_backend ('api' / 'self_hosted') for institutions
    requiring on-premise inference (FERPA-strict / HIPAA-strict / institutional
    policy against cloud LLM). See docs/known-deferred.md.

    tenant param is kept for forward compatibility with that future routing.
    """
    from .together import TogetherClassifierBackend
    return TogetherClassifierBackend()


def get_assessor(tenant) -> AssessmentBackend:
    """Return the AssessmentBackend (Anthropic primary, OpenAI failover).

    Returns an AssessorWithFailover wrapping Anthropic (primary) and OpenAI
    (failover) so transient outages on the primary vendor transparently
    fall through to the secondary.

    v1 always uses the API backends. Phase 9 will add
    Institution.inference_backend ('api' / 'self_hosted') for institutions
    requiring on-premise inference. See docs/known-deferred.md.

    tenant param is kept for forward compatibility with that future routing.
    """
    from .anthropic_backend import AnthropicAssessmentBackend
    from .failover import AssessorWithFailover
    from .openai_backend import OpenAIAssessmentBackend
    return AssessorWithFailover(
        primary=AnthropicAssessmentBackend(),
        failover=OpenAIAssessmentBackend(),
    )


def get_pipeline(
    tenant,
    rules: list[FlaggingRule],
) -> "ModerationPipeline":
    """Build full ModerationPipeline for tenant + rules.

    Convenience wrapper around get_classifier + get_assessor.
    """
    from ..pipeline import ModerationPipeline

    return ModerationPipeline(
        classifier=get_classifier(tenant),
        assessor=get_assessor(tenant),
        rules=rules,
    )
