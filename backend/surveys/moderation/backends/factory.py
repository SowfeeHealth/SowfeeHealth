from typing import TYPE_CHECKING

from ..schemas import FlaggingRule
from .base import AssessmentBackend

if TYPE_CHECKING:
    from ..pipeline import ModerationPipeline


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
    """Build ModerationPipeline for tenant + rules.

    Stage 1b classifier was removed from the pipeline (see commit history
    for backends/together.py deletion). Only Stage 2 assessor is needed.
    """
    from ..pipeline import ModerationPipeline

    return ModerationPipeline(
        assessor=get_assessor(tenant),
        rules=rules,
    )
