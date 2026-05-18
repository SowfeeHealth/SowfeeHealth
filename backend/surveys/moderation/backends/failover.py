import logging

from ..schemas import CrisisAssessment
from .base import AssessmentBackend, AssessmentContext, BackendUnavailable


logger = logging.getLogger(__name__)


class AssessorWithFailover:
    """Wraps a primary AssessmentBackend with a failover backend.

    Calls primary first. On BackendUnavailable (transient infrastructure
    issue: timeout, connection error, rate limit, 5xx), transparently
    switches to failover backend.

    BackendInvalidOutput is NOT caught — that's a data/schema problem
    that won't be fixed by trying a different LLM vendor. Let it propagate
    to pipeline-level handler (which falls back to Stage 1a rule-only).

    Implements the AssessmentBackend protocol so pipeline code is unaware
    of failover existence.
    """

    def __init__(
        self,
        primary: AssessmentBackend,
        failover: AssessmentBackend,
    ) -> None:
        self._primary = primary
        self._failover = failover

    async def assess(self, text: str, context: AssessmentContext) -> CrisisAssessment:
        try:
            return await self._primary.assess(text, context)
        except BackendUnavailable as exc:
            logger.warning(
                "Primary assessment backend unavailable, using failover: %s",
                exc,
            )
            return await self._failover.assess(text, context)
