from typing import TYPE_CHECKING

from ..schemas import FlaggingRule
from .base import AssessmentBackend, ClassifierBackend

if TYPE_CHECKING:
    from ..pipeline import ModerationPipeline


def get_classifier(tenant) -> ClassifierBackend:
    """Return the ClassifierBackend for tenant.inference_mode."""
    if tenant.inference_mode == "api":
        from .together import TogetherClassifierBackend
        return TogetherClassifierBackend()
    elif tenant.inference_mode == "self_hosted":
        raise NotImplementedError(
            "Self-hosted inference (Ollama) is not implemented in v1. "
            "Tenants requiring self-hosted must use inference_mode='api' "
            "until Ollama backends are added. See docs/known-deferred.md."
        )
    else:
        raise ValueError(f"Unknown inference_mode: {tenant.inference_mode!r}")


def get_assessor(tenant) -> AssessmentBackend:
    """Return the AssessmentBackend for tenant.inference_mode.

    For inference_mode='api', returns an AssessorWithFailover wrapping
    Anthropic (primary) and OpenAI (failover) so transient outages on
    the primary vendor transparently fall through to the secondary.
    """
    if tenant.inference_mode == "api":
        from .anthropic_backend import AnthropicAssessmentBackend
        from .failover import AssessorWithFailover
        from .openai_backend import OpenAIAssessmentBackend
        return AssessorWithFailover(
            primary=AnthropicAssessmentBackend(),
            failover=OpenAIAssessmentBackend(),
        )
    elif tenant.inference_mode == "self_hosted":
        raise NotImplementedError(
            "Self-hosted inference (Ollama) is not implemented in v1. "
            "Tenants requiring self-hosted must use inference_mode='api' "
            "until Ollama backends are added. See docs/known-deferred.md."
        )
    else:
        raise ValueError(f"Unknown inference_mode: {tenant.inference_mode!r}")


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
