"""Constants for OpenMic app."""

# Audio recording
SAMPLE_RATE = 16000  # Whisper's native sample rate
CHANNELS = 1
AUDIO_DTYPE = "float32"
AUDIO_BLOCKSIZE = 1024
MIN_RECORDING_SECONDS = 0.5
MAX_RECORDING_SECONDS = 120

# macOS virtual key codes
VK_ANSI_V = 0x09
VK_SPACE = 0x31
VK_FN = 63  # Fn key (generates kCGEventFlagsChanged, not keydown)

# Default hotkey: Fn key alone
DEFAULT_HOTKEY_VK = VK_FN
DEFAULT_HOTKEY_MODIFIERS = 0  # No modifier needed — Fn is detected via FlagsChanged
DEFAULT_HOTKEY_DESCRIPTION = "Fn"

# Hotkey activation mode
HOTKEY_MODE_HOLD = "hold"    # Hold key to record, release to process
HOTKEY_MODE_TOGGLE = "toggle"  # Press to start, press again to stop
DEFAULT_HOTKEY_MODE = HOTKEY_MODE_HOLD

# STT engines
STT_OPENAI_API = "openai_api"
STT_MLX_WHISPER = "mlx_whisper"

# LLM providers
LLM_OPENAI = "openai"
LLM_ANTHROPIC = "anthropic"

# Default models
DEFAULT_OPENAI_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_OPENAI_POLISH_MODEL = "gpt-5-nano"
DEFAULT_ANTHROPIC_POLISH_MODEL = "claude-haiku-4-20250414"
DEFAULT_MLX_WHISPER_MODEL = "mlx-community/whisper-small-mlx"

# Polish token limits
# gpt-5-nano is a reasoning model: max_completion_tokens covers both hidden
# chain-of-thought tokens and the final reply, so the budget must be large
# enough for both (reasoning alone can consume 1000–4000 tokens on short tasks).
POLISH_MAX_TOKENS = 16384

# Speech-to-text language (ISO 639-1 code, or "auto" for auto-detection)
DEFAULT_STT_LANGUAGE = "en"  # en=English, es=Spanish, fr=French, de=German, auto=auto-detect
STT_LANGUAGE_AUTO = "auto"

# App paths
APP_NAME = "OpenMic"
APP_BUNDLE_ID = "com.openmic.voicetotext"

# Paste timing
CLIPBOARD_SETTLE_DELAY = 0.02  # seconds
PASTE_RESTORE_DELAY = 0.1  # seconds
