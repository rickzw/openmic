"""Audio recording from the system microphone using sounddevice."""

import logging
import threading

import numpy as np
import sounddevice as sd

from openmic.constants import AUDIO_BLOCKSIZE, AUDIO_DTYPE, CHANNELS, SAMPLE_RATE

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Records audio from the default input device at 16kHz mono float32."""

    def __init__(self):
        self._stream = None  # type: sd.InputStream | None
        self._buffer = []  # type: list[np.ndarray]
        self._lock = threading.Lock()
        self._level = 0.0
        self._level_lock = threading.Lock()

    def start(self):
        """Start recording. Audio chunks accumulate in an internal buffer."""
        with self._lock:
            self._buffer = []

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=AUDIO_DTYPE,
            callback=self._callback,
            blocksize=AUDIO_BLOCKSIZE,
        )
        self._stream.start()
        logger.info("Audio recording started (rate=%d, channels=%d)", SAMPLE_RATE, CHANNELS)

    def _callback(self, indata, frames, time, status):
        """Called on the PortAudio thread for each audio block."""
        if status:
            logger.warning("sounddevice status: %s", status)
        with self._lock:
            self._buffer.append(indata.copy())
        level = float(np.sqrt(np.mean(indata ** 2)))
        with self._level_lock:
            self._level = level

    def stop(self) -> np.ndarray:
        """Stop recording and return the captured audio as a 1-D float32 numpy array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if self._buffer:
                audio = np.concatenate(self._buffer, axis=0).flatten()
            else:
                audio = np.array([], dtype=np.float32)
            self._buffer = []

        duration = len(audio) / SAMPLE_RATE if len(audio) > 0 else 0
        logger.info("Audio recording stopped: %.1f seconds, %d samples", duration, len(audio))
        return audio

    def get_level(self) -> float:
        """Return the current RMS audio level in the range 0.0–1.0.

        Returns 0.0 when not recording.
        """
        if not self.is_recording:
            return 0.0
        with self._level_lock:
            return self._level

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active
