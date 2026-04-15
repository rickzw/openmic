"""First-run onboarding: permissions check and API key setup."""

import logging

from AppKit import NSLocale

from openmic.config import Config
from openmic.ui.native_dialogs import show_alert, show_picker, show_text_input
from openmic.permissions import (
    check_accessibility,
    check_microphone,
    prompt_accessibility,
    prompt_microphone,
)

logger = logging.getLogger(__name__)


def run_onboarding(config: Config) -> bool:
    """Run the first-time setup flow.

    Returns True if onboarding was completed (or skipped), False if the user cancelled.
    """
    # Welcome
    button = show_alert(
        title="Welcome to OpenMic!",
        message=(
            "OpenMic lets you dictate text anywhere on your Mac.\n\n"
            "Hold the Fn key to record, "
            "release to stop.\n\n"
            "Your speech will be transcribed and polished by AI, "
            "then pasted into the focused app.\n\n"
            "Let's set up a few things first."
        ),
        buttons=["Let's go", "Skip setup"],
    )
    if button == 1:  # Skip setup
        config.set("first_run_complete", True)
        return True

    # Permissions
    if not check_accessibility():
        show_alert(
            title="Accessibility Permission",
            message=(
                "OpenMic needs Accessibility permission to:\n"
                "- Register a global keyboard shortcut\n"
                "- Paste text into other applications\n\n"
                "Click OK to open System Settings.\n"
                "Add OpenMic (or Terminal/Python) to the Accessibility list."
            ),
            buttons=["Open Settings"],
        )
        prompt_accessibility()
        # Wait for user to grant permission
        show_alert(
            title="Accessibility Permission",
            message="After granting permission, click OK to continue.\n"
            "(You may need to restart OpenMic if the hotkey doesn't work.)",
            buttons=["OK"],
        )

    if not check_microphone():
        show_alert(
            title="Microphone Permission",
            message=(
                "OpenMic needs Microphone permission to record your voice.\n\n"
                "macOS will prompt you automatically when you first record. "
                "Click 'Allow' when prompted."
            ),
            buttons=["OK"],
        )

    # API Key
    _setup_api_key(config)

    # Language
    _setup_language(config)

    config.set("first_run_complete", True)
    logger.info("Onboarding complete")
    return True


def _setup_api_key(config: Config):
    """Prompt for at least one API key."""
    button = show_alert(
        title="API Key Setup",
        message=(
            "OpenMic needs an API key for transcription and text polish.\n\n"
            "You'll need at least an OpenAI API key (used for both "
            "Whisper transcription and GPT text polish).\n\n"
            "Optionally, add an Anthropic key for Claude-based polish."
        ),
        buttons=["Enter OpenAI Key", "Skip (configure later)", "Enter Anthropic Key"],
    )

    if button == 0:  # OpenAI
        text = show_text_input(
            title="OpenAI API Key",
            message="Enter your OpenAI API key (starts with sk-...):",
            default_text="",
            ok_button="Save",
            cancel_button="Cancel",
        )
        if text and text.strip():
            config.set("openai_api_key", text.strip())
            logger.info("OpenAI API key saved during onboarding")

            # Also offer Anthropic
            _offer_anthropic_key(config)

    elif button == 2:  # Anthropic
        text = show_text_input(
            title="Anthropic API Key",
            message="Enter your Anthropic API key:",
            default_text="",
            ok_button="Save",
            cancel_button="Cancel",
        )
        if text and text.strip():
            config.set("anthropic_api_key", text.strip())
            config.set("llm_provider", "anthropic")
            logger.info("Anthropic API key saved during onboarding")


_LANGUAGE_OPTIONS = [
    "Auto-detect",
    "English",
    "Spanish",
    "French",
    "German",
    "Portuguese",
    "Chinese",
    "Japanese",
    "Korean",
    "Italian",
    "Dutch",
    "Hindi",
    "Arabic",
    "Russian",
    "Other\u2026",
]

_LANGUAGE_CODES = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Portuguese": "pt",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "Italian": "it",
    "Dutch": "nl",
    "Hindi": "hi",
    "Arabic": "ar",
    "Russian": "ru",
}


def _setup_language(config: Config):
    """Prompt the user to select a transcription language."""
    # Detect system language and pre-select if it's in our list
    try:
        sys_lang = NSLocale.currentLocale().languageCode()
        # Find the display name for the system language code
        default = next(
            (name for name, code in _LANGUAGE_CODES.items() if code == sys_lang),
            "Auto-detect",
        )
    except Exception:
        default = "Auto-detect"

    selected = show_picker(
        title="Transcription Language",
        message=(
            "Which language will you primarily dictate in?\n\n"
            "Auto-detect works well but specifying a language improves accuracy."
        ),
        options=_LANGUAGE_OPTIONS,
        default=default,
        ok_button="Continue",
        cancel_button="Skip",
    )

    if selected is None or selected == "Auto-detect":
        config.set("stt_language", "auto")
        logger.info("Onboarding: language set to auto-detect")
        return

    if selected == "Other\u2026":
        code = show_text_input(
            title="Custom Language Code",
            message="Enter an ISO 639-1 language code (e.g. 'sv' for Swedish):",
            default_text="",
            ok_button="Save",
            cancel_button="Cancel",
        )
        if code and code.strip():
            config.set("stt_language", code.strip().lower())
            logger.info("Onboarding: language set to custom code '%s'", code.strip())
        else:
            config.set("stt_language", "auto")
        return

    code = _LANGUAGE_CODES.get(selected, "auto")
    config.set("stt_language", code)
    logger.info("Onboarding: language set to '%s' (%s)", selected, code)


def _offer_anthropic_key(config: Config):
    """Offer to also add an Anthropic key after setting up OpenAI."""
    button = show_alert(
        title="Anthropic API Key (Optional)",
        message="Would you also like to add an Anthropic API key?\n"
        "(This lets you use Claude for text polish instead of GPT.)",
        buttons=["Yes", "No, I'm done"],
    )
    if button == 0:  # Yes
        text = show_text_input(
            title="Anthropic API Key",
            message="Enter your Anthropic API key:",
            default_text="",
            ok_button="Save",
            cancel_button="Cancel",
        )
        if text and text.strip():
            config.set("anthropic_api_key", text.strip())
            logger.info("Anthropic API key saved during onboarding")
