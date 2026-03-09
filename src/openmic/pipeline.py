"""Pipeline orchestrator: record → transcribe → polish → paste."""

import concurrent.futures
import logging
import re
import threading

import numpy as np

from openmic.config import Config
from openmic.constants import MIN_RECORDING_SECONDS, SAMPLE_RATE
from openmic.dictionary import PersonalDictionary
from openmic.paster import Paster
from openmic.polisher import Polisher
from openmic.recorder import AudioRecorder
from openmic.transcriber import Transcriber

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """Raised when the pipeline is cancelled by the user."""


class Pipeline:
    """Orchestrates the full voice-to-text pipeline.

    Manages the recorder, transcriber, polisher, and paster components.
    The app.py state machine calls these methods in sequence.
    """

    def __init__(self, config: Config):
        self.config = config
        self.recorder = AudioRecorder()
        self.dictionary = PersonalDictionary(config)
        self.transcriber = Transcriber(config)
        self.polisher = Polisher(config, self.dictionary)
        self.paster = Paster()
        self._cancel_event = threading.Event()

    def cancel(self):
        """Signal the running pipeline to abort before the next stage."""
        self._cancel_event.set()
        logger.info("Pipeline cancel requested")

    def _check_cancelled(self):
        """Raise if cancel has been requested."""
        if self._cancel_event.is_set():
            raise CancelledError("Pipeline cancelled by user")

    def warm_up(self):
        """Pre-load models for the configured engine.

        Call from a background thread at app startup to avoid first-call delays.
        """
        self.transcriber.warm_up()

    def start_recording(self):
        """Start audio recording."""
        self._cancel_event.clear()
        self.recorder.start()

    def stop_recording_and_get_audio(self) -> np.ndarray:
        """Stop recording and return the audio data."""
        audio = self.recorder.stop()
        self._check_cancelled()
        return audio

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to raw text.

        Returns empty string if audio is too short.
        """
        duration = len(audio) / SAMPLE_RATE if len(audio) > 0 else 0
        if duration < MIN_RECORDING_SECONDS:
            logger.warning(
                "Recording too short (%.2f sec < %.2f sec minimum), skipping",
                duration,
                MIN_RECORDING_SECONDS,
            )
            return ""

        prompt_hint = self.dictionary.get_prompt_hint()
        # Always include voice formatting commands so the STT model transcribes
        # them literally rather than suppressing them as speech artifacts.
        voice_hint = "new line, new paragraph"
        prompt_hint = (prompt_hint + " " + voice_hint).strip() if prompt_hint else voice_hint
        result = self.transcriber.transcribe(audio, prompt_hint=prompt_hint)
        self._check_cancelled()
        return result

    def polish(self, raw_text: str, app_context: dict = None) -> str:
        """Polish raw transcription with LLM.

        If the text is empty or API key is missing, returns the raw text as-is.
        Voice formatting commands are split out before the LLM so they can never
        be removed or reformatted by the model.
        """
        if not raw_text.strip():
            return raw_text

        self._check_cancelled()

        if not self.config.has_api_key():
            logger.warning("No API key configured, returning raw transcript")
            return self._apply_voice_commands(raw_text)

        segments, separators = self._split_on_voice_commands(raw_text)

        if len(segments) == 1:
            # No voice commands — single API call as before
            polished = self.polisher.polish(raw_text, app_context=app_context)
            if not polished.strip():
                logger.warning("Polisher returned empty result, falling back to raw transcript")
                return raw_text
            return polished

        # Polish each segment in parallel so latency stays low
        def _polish_one(seg: str) -> str:
            seg = seg.strip()
            if not seg:
                return ""
            try:
                result = self.polisher.polish(seg, app_context=app_context)
            except Exception:
                logger.exception("Polisher raised exception for segment, using raw: '%.50s'", seg)
                return seg
            if not result.strip():
                logger.warning("Polisher returned empty for segment, using raw: '%.50s'", seg)
                return seg
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(segments)) as executor:
            polished_segments = list(executor.map(_polish_one, segments))

        return "".join(
            seg + sep for seg, sep in zip(polished_segments, separators + [""])
        ).strip()

    def _split_on_voice_commands(self, text: str) -> tuple:
        """Split text at voice formatting commands.

        Returns (segments, separators) where len(separators) == len(segments) - 1.
        Each separator is '\\n' (new line) or '\\n\\n' (new paragraph).
        """
        pattern = re.compile(
            r'\bnew\s+paragraph\b[.,;]?|\bnew\s+line\b[.,;]?', re.IGNORECASE
        )
        segments = []
        separators = []
        last_end = 0
        for match in pattern.finditer(text):
            segments.append(text[last_end:match.start()])
            sep = '\n\n' if re.match(r'new\s+paragraph', match.group(), re.IGNORECASE) else '\n'
            separators.append(sep)
            last_end = match.end()
        segments.append(text[last_end:])
        return segments, separators

    def _apply_voice_commands(self, text: str) -> str:
        """Replace spoken formatting commands with actual whitespace (no-LLM fallback path)."""
        text = re.sub(r'\bnew\s+paragraph\b[.,;]?', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'\bnew\s+line\b[.,;]?', '\n', text, flags=re.IGNORECASE)
        return text

    def paste(self, text: str):
        """Paste text into the focused application."""
        if not text.strip():
            logger.info("Nothing to paste (empty text)")
            return
        self.paster.paste(text)
