"""Typed error hierarchy for OpenMic pipeline errors.

These replace generic RuntimeError raises in transcriber.py and polisher.py,
allowing app.py to show context-specific error dialogs with action buttons.
"""


class OpenMicError(RuntimeError):
    """Base class for all OpenMic pipeline errors."""


class InvalidAPIKeyError(OpenMicError):
    """API key is missing, invalid, or revoked."""


class RateLimitError(OpenMicError):
    """API provider rate limit reached."""


class NetworkError(OpenMicError):
    """Cannot reach the API provider (no internet, DNS failure, etc.)."""


class ProviderAPIError(OpenMicError):
    """Catch-all for unexpected API provider errors."""


class EmptyTranscriptionError(OpenMicError):
    """STT returned an empty result (silence or unintelligible audio)."""
