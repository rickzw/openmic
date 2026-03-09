"""Settings persistence for OpenMic app.

Stores configuration as JSON in ~/Library/Application Support/OpenMic/config.json.
"""

import json
import os

from openmic.constants import (
    DEFAULT_ANTHROPIC_POLISH_MODEL,
    DEFAULT_HOTKEY_DESCRIPTION,
    DEFAULT_HOTKEY_MODE,
    DEFAULT_HOTKEY_MODIFIERS,
    DEFAULT_HOTKEY_VK,
    DEFAULT_MLX_WHISPER_MODEL,
    DEFAULT_OPENAI_POLISH_MODEL,
    DEFAULT_OPENAI_STT_MODEL,
    DEFAULT_STT_LANGUAGE,
    LLM_OPENAI,
    STT_OPENAI_API,
)

APP_SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/OpenMic")
CONFIG_FILE = os.path.join(APP_SUPPORT_DIR, "config.json")

DEFAULTS = {
    "stt_engine": STT_OPENAI_API,
    "llm_provider": LLM_OPENAI,
    "openai_api_key": "",
    "anthropic_api_key": "",
    "openai_stt_model": DEFAULT_OPENAI_STT_MODEL,
    "openai_polish_model": DEFAULT_OPENAI_POLISH_MODEL,
    "anthropic_polish_model": DEFAULT_ANTHROPIC_POLISH_MODEL,
    "local_whisper_model": DEFAULT_MLX_WHISPER_MODEL,
    "local_whisper_model_size": "small",
    "hotkey_vk": DEFAULT_HOTKEY_VK,
    "hotkey_modifiers": DEFAULT_HOTKEY_MODIFIERS,
    "hotkey_description": DEFAULT_HOTKEY_DESCRIPTION,
    "hotkey_mode": DEFAULT_HOTKEY_MODE,
    "stt_language": DEFAULT_STT_LANGUAGE,
    "sound_feedback_enabled": True,
    "personal_dictionary": [],
    "first_run_complete": False,
}


class Config:
    def __init__(self):
        os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
        self._data: dict = dict(DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass  # Use defaults if config is corrupted

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        val = self._data.get(key)
        if val is not None:
            return val
        if default is not None:
            return default
        return DEFAULTS.get(key)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def has_api_key(self) -> bool:
        """Check if at least one API key is configured."""
        return bool(self.get("openai_api_key") or self.get("anthropic_api_key"))
