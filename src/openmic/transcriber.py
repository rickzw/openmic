"""Speech-to-text transcription with multiple engine support.

Engines:
- openai_api: OpenAI Whisper API (cloud)
- mlx_whisper: mlx-whisper (local, Apple Silicon)
"""

import io
import logging
import tempfile

import numpy as np
import openai
import soundfile as sf

from openmic.config import Config
from openmic.errors import InvalidAPIKeyError, NetworkError, ProviderAPIError, RateLimitError
from openmic.constants import (
    DEFAULT_OPENAI_STT_MODEL,
    DEFAULT_STT_LANGUAGE,
    SAMPLE_RATE,
    STT_LANGUAGE_AUTO,
    STT_MLX_WHISPER,
    STT_OPENAI_API,
)

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio to text using the configured STT engine."""

    def __init__(self, config: Config):
        self.config = config
        self._mlx_model = None  # Lazy-loaded
        self._openai_client = None
        self._openai_api_key_used = None

    def _get_openai_client(self):
        """Return a cached OpenAI client, creating a new one if the key changed."""
        from openai import OpenAI

        api_key = self.config.get("openai_api_key")
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        if self._openai_client is None or self._openai_api_key_used != api_key:
            self._openai_client = OpenAI(api_key=api_key)
            self._openai_api_key_used = api_key
        return self._openai_client

    def warm_up(self):
        """Pre-load the local whisper model if using a local engine.

        Call this at app startup to avoid a long delay on first dictation.
        Should be called in a background thread to avoid blocking the UI.
        """
        engine = self.config.get("stt_engine", STT_OPENAI_API)

        if engine == STT_MLX_WHISPER:
            try:
                import mlx_whisper

                model = self.config.get(
                    "local_whisper_model", "mlx-community/whisper-small-mlx"
                )
                logger.info("Pre-warming MLX Whisper model: %s", model)
                silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
                wav_path = self._audio_to_wav_path(silence)
                try:
                    mlx_whisper.transcribe(
                        wav_path, path_or_hf_repo=model, language="en"
                    )
                finally:
                    import os

                    os.unlink(wav_path)
                logger.info("MLX Whisper model pre-warmed")
            except ImportError:
                logger.warning("mlx-whisper not installed, skipping warm-up")
            except Exception:
                logger.exception("MLX Whisper warm-up failed")


    def transcribe(self, audio: np.ndarray, prompt_hint: str = "") -> str:
        """Transcribe audio to text.

        Args:
            audio: 1-D float32 numpy array at 16kHz.
            prompt_hint: Optional text hint for the transcription engine
                         (e.g., personal dictionary terms).

        Returns:
            Raw transcribed text.
        """
        if len(audio) == 0:
            return ""

        engine = self.config.get("stt_engine", STT_OPENAI_API)
        logger.info("Transcribing with engine: %s (%d samples)", engine, len(audio))

        if engine == STT_OPENAI_API:
            return self._transcribe_openai(audio, prompt_hint)
        elif engine == STT_MLX_WHISPER:
            return self._transcribe_mlx(audio)
        else:
            raise ValueError("Unknown STT engine: %s" % engine)

    def _audio_to_wav_bytes(self, audio: np.ndarray) -> io.BytesIO:
        """Encode audio to WAV format in memory."""
        buf = io.BytesIO()
        sf.write(buf, audio, SAMPLE_RATE, format="WAV")
        buf.seek(0)
        return buf

    def _audio_to_wav_path(self, audio: np.ndarray) -> str:
        """Write audio to a temporary WAV file and return the path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, audio, SAMPLE_RATE, format="WAV")
        return tmp.name

    def _transcribe_openai(self, audio: np.ndarray, prompt_hint: str) -> str:
        client = self._get_openai_client()
        wav_buf = self._audio_to_wav_bytes(audio)
        model = self.config.get("openai_stt_model", DEFAULT_OPENAI_STT_MODEL)
        language = self.config.get("stt_language", DEFAULT_STT_LANGUAGE)

        kwargs = {
            "model": model,
            "file": ("audio.wav", wav_buf, "audio/wav"),
        }
        # Omit language param for auto-detection (Whisper API auto-detects when absent)
        if language != STT_LANGUAGE_AUTO:
            kwargs["language"] = language
        if prompt_hint:
            kwargs["prompt"] = prompt_hint
        try:
            response = client.audio.transcriptions.create(**kwargs)
        except openai.AuthenticationError:
            logger.exception("OpenAI authentication error during transcription")
            raise InvalidAPIKeyError("Invalid OpenAI API key. Update it in Settings → API Keys.")
        except openai.RateLimitError:
            logger.exception("OpenAI rate limit during transcription")
            raise RateLimitError("OpenAI rate limit reached. Try again in a moment.")
        except openai.APIConnectionError:
            logger.exception("OpenAI connection error during transcription")
            raise NetworkError("Cannot reach OpenAI. Check your internet connection.")
        except openai.APIError:
            logger.exception("OpenAI API error during transcription")
            raise ProviderAPIError("OpenAI transcription failed. Check logs for details.")
        text = response.text
        logger.info("OpenAI STT (%s): '%s'", model, text[:100])
        return text

    def _transcribe_mlx(self, audio: np.ndarray) -> str:
        try:
            import mlx_whisper
        except ImportError:
            raise ImportError(
                "mlx-whisper not installed. Install with: "
                "pip install 'openmic[local-whisper-mlx]'"
            )

        model = self.config.get("local_whisper_model", "mlx-community/whisper-small-mlx")
        language = self.config.get("stt_language", DEFAULT_STT_LANGUAGE)
        wav_path = self._audio_to_wav_path(audio)

        try:
            mlx_kwargs = {"path_or_hf_repo": model}
            if language != STT_LANGUAGE_AUTO:
                mlx_kwargs["language"] = language
            logger.info("Transcribing with mlx-whisper model: %s (language: %s)", model, language)
            result = mlx_whisper.transcribe(
                wav_path,
                **mlx_kwargs,
            )
            text = result["text"].strip()
            logger.info("mlx-whisper: '%s'", text[:100])
            return text
        finally:
            import os
            os.unlink(wav_path)

