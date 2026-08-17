from types import SimpleNamespace

from app.services.candidate_asr_providers import (
    NVIDIA_PARAKEET_FUNCTION_ID,
    NVIDIA_PARAKEET_MODEL,
    NvidiaParakeetRNNTProvider,
)


def test_nvidia_parakeet_uses_verified_hosted_identity_only():
    provider = NvidiaParakeetRNNTProvider("test-key")
    assert provider.model == NVIDIA_PARAKEET_MODEL
    assert provider.function_id == NVIDIA_PARAKEET_FUNCTION_ID
    assert "test-key" not in provider.model


def test_nvidia_parakeet_duration_conversion_handles_riva_proto_shape():
    assert NvidiaParakeetRNNTProvider._seconds(SimpleNamespace(seconds=2, nanos=125_000_000)) == 2.125

