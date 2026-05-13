from .base import AssessmentBackend, ClassifierBackend


def get_classifier(tenant) -> ClassifierBackend:
    """Return the ClassifierBackend for tenant.inference_mode."""
    if tenant.inference_mode == "api":
        from .together import TogetherClassifierBackend
        return TogetherClassifierBackend()
    elif tenant.inference_mode == "self_hosted":
        from .ollama_backend import OllamaClassifierBackend
        return OllamaClassifierBackend()
    else:
        raise ValueError(f"Unknown inference_mode: {tenant.inference_mode!r}")


def get_assessor(tenant) -> AssessmentBackend:
    """Return the AssessmentBackend for tenant.inference_mode."""
    if tenant.inference_mode == "api":
        from .anthropic_backend import AnthropicAssessmentBackend
        return AnthropicAssessmentBackend()
    elif tenant.inference_mode == "self_hosted":
        from .ollama_backend import OllamaAssessmentBackend
        return OllamaAssessmentBackend()
    else:
        raise ValueError(f"Unknown inference_mode: {tenant.inference_mode!r}")
