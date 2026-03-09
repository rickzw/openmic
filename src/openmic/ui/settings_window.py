"""Settings window for configuring API keys, STT engine, LLM provider, and hotkey.

Uses native NSAlert dialogs for reliable cross-platform behavior.
"""

import logging

import rumps  # Still used for notifications

from openmic.config import Config
from openmic.ui.native_dialogs import show_alert, show_text_input
from openmic.constants import (
    HOTKEY_MODE_HOLD,
    HOTKEY_MODE_TOGGLE,
    LLM_ANTHROPIC,
    LLM_OPENAI,
    STT_MLX_WHISPER,
    STT_OPENAI_API,
)

logger = logging.getLogger(__name__)


def show_settings(config: Config, hotkey_manager=None):
    """Show the settings dialog sequence."""
    stt_names = {
        STT_OPENAI_API: "OpenAI Whisper API (cloud)",
        STT_MLX_WHISPER: "Local Whisper (mlx, Apple Silicon)",
    }
    llm_names = {
        LLM_OPENAI: "OpenAI",
        LLM_ANTHROPIC: "Anthropic",
    }
    mode_names = {
        HOTKEY_MODE_HOLD: "Hold to record",
        HOTKEY_MODE_TOGGLE: "Toggle (press to start/stop)",
    }

    current_stt = stt_names.get(config.get("stt_engine"), "Unknown")
    current_llm = llm_names.get(config.get("llm_provider"), "Unknown")
    current_hotkey = config.get("hotkey_description", "Fn")
    current_mode = mode_names.get(config.get("hotkey_mode"), "Hold to record")
    has_openai = "Set" if config.get("openai_api_key") else "Not set"
    has_anthropic = "Set" if config.get("anthropic_api_key") else "Not set"

    summary = (
        "Current Settings:\n\n"
        "STT Engine: %s\n"
        "LLM Provider: %s\n"
        "OpenAI API Key: %s\n"
        "Anthropic API Key: %s\n"
        "Hotkey: %s (%s)\n\n"
        "What would you like to configure?"
        % (current_stt, current_llm, has_openai, has_anthropic, current_hotkey, current_mode)
    )

    # NSAlert adds buttons right-to-left, so first = rightmost (default/blue).
    # Desired visual order (left→right): Engine Settings | API Keys | Hotkey | Close
    # Array order (right→left):          Close | Hotkey | API Keys | Engine Settings
    button = show_alert(
        title="OpenMic Settings",
        message=summary,
        buttons=["Close", "Hotkey", "API Keys", "Engine Settings"],
    )

    if button == 1:  # Hotkey
        logger.info("User clicked Hotkey")
        _configure_hotkey(config, hotkey_manager)
    elif button == 2:  # API Keys
        logger.info("User clicked API Keys")
        _configure_api_keys(config)
    elif button == 3:  # Engine Settings
        logger.info("User clicked Engine Settings")
        _configure_engines(config)
    # button == 0 → Close, do nothing


def _configure_api_keys(config: Config):
    """Prompt for API keys."""
    current = config.get("openai_api_key", "")
    masked = ("*" * (len(current) - 4) + current[-4:]) if len(current) > 4 else current

    text = show_text_input(
        title="OpenAI API Key",
        message="Enter your OpenAI API key (for Whisper + GPT polish).\nCurrent: %s" % (masked or "Not set"),
        default_text=current,
        ok_button="Save",
        cancel_button="Skip",
    )
    if text and text.strip():
        config.set("openai_api_key", text.strip())
        logger.info("OpenAI API key updated")

    current = config.get("anthropic_api_key", "")
    masked = ("*" * (len(current) - 4) + current[-4:]) if len(current) > 4 else current

    text = show_text_input(
        title="Anthropic API Key",
        message="Enter your Anthropic API key (for Claude polish).\nCurrent: %s" % (masked or "Not set"),
        default_text=current,
        ok_button="Save",
        cancel_button="Skip",
    )
    if text and text.strip():
        config.set("anthropic_api_key", text.strip())
        logger.info("Anthropic API key updated")


def _configure_hotkey(config: Config, hotkey_manager=None):
    """Configure hotkey mode and key combination."""

    # Step 1: Choose mode (hold vs toggle)
    current_mode = config.get("hotkey_mode", HOTKEY_MODE_HOLD)
    current_mode_name = "Hold to record" if current_mode == HOTKEY_MODE_HOLD else "Toggle (press to start/stop)"

    mode_button = show_alert(
        title="Hotkey Mode",
        message=(
            "Choose how the hotkey activates recording:\n\n"
            "Hold: Hold the hotkey while speaking, release to paste.\n"
            "Toggle: Press once to start, press again to stop.\n\n"
            "Currently: %s" % current_mode_name
        ),
        buttons=["Hold to Record", "Cancel", "Toggle Mode"],
    )

    if mode_button == 0:
        config.set("hotkey_mode", HOTKEY_MODE_HOLD)
        logger.info("Hotkey mode set to: hold")
        rumps.notification("OpenMic", "Hotkey Mode", "Hold to record mode enabled.")
    elif mode_button == 2:
        config.set("hotkey_mode", HOTKEY_MODE_TOGGLE)
        logger.info("Hotkey mode set to: toggle")
        rumps.notification("OpenMic", "Hotkey Mode", "Toggle mode enabled.")
    # Cancel = do nothing

    # Step 2: Optionally change the key combination
    change_button = show_alert(
        title="Hotkey Key Combination",
        message=(
            "Current hotkey: %s\n\n"
            "Would you like to change the key combination?"
            % config.get("hotkey_description", "Fn")
        ),
        buttons=["Keep Current", "Cancel", "Change Hotkey"],
    )

    if change_button == 2:  # Change Hotkey
        _configure_hotkey_combo(config, hotkey_manager)


def _configure_hotkey_combo(config: Config, hotkey_manager=None):
    """Let the user press any key combo to set as the new hotkey."""
    from openmic.ui.native_dialogs import show_hotkey_capture

    current_desc = config.get("hotkey_description", "Fn")
    result = show_hotkey_capture(current_desc=current_desc, hotkey_manager=hotkey_manager)

    if result is None:
        logger.info("Hotkey capture cancelled or no combo entered")
        return

    vk, mods, desc = result
    config.set("hotkey_vk", vk)
    config.set("hotkey_modifiers", mods)
    config.set("hotkey_description", desc)
    logger.info("Hotkey changed to: %s (vk=%d, mods=0x%x)", desc, vk, mods)

    # Update the live hotkey manager without restarting
    if hotkey_manager:
        hotkey_manager.update(vk, mods, desc)
        logger.info("HotkeyManager updated live")

    rumps.notification("OpenMic", "Hotkey Updated", "New hotkey: %s" % desc)


def _configure_engines(config: Config):
    """Configure STT engine, STT model, language, and LLM provider."""
    logger.info("_configure_engines() called")

    # --- Step 1: STT engine ---
    stt_options = [
        ("OpenAI API (cloud)", STT_OPENAI_API),
        ("Local mlx (Apple Silicon)", STT_MLX_WHISPER),
    ]
    current_stt = config.get("stt_engine", STT_OPENAI_API)
    current_stt_name = next(
        (name for name, val in stt_options if val == current_stt), "Unknown"
    )

    # NSAlert adds buttons top-to-bottom (first = default/blue).
    # Index 0 = OpenAI API, 1 = mlx, 2 = Cancel
    stt_button = show_alert(
        title="Speech-to-Text Engine",
        message=(
            "Choose your STT engine:\n\n"
            "1. OpenAI API — best quality, requires internet + API key\n"
            "2. Local mlx — fast offline (Apple Silicon only)\n\n"
            "Currently: %s" % current_stt_name
        ),
        buttons=["1. OpenAI API", "2. Local mlx", "Cancel"],
    )

    if stt_button == 0:
        config.set("stt_engine", STT_OPENAI_API)
        logger.info("STT engine set to OpenAI API")
        _configure_openai_stt_model(config)  # model sub-step (OpenAI only)
    elif stt_button == 1:
        config.set("stt_engine", STT_MLX_WHISPER)
        logger.info("STT engine set to Local mlx")
    # stt_button == 2 → Cancel: no engine change

    # --- Step 2: Language (applies to all STT engines) ---
    _configure_stt_language(config)

    # --- Step 3: LLM provider ---
    button = show_alert(
        title="LLM Provider",
        message=(
            "Choose which LLM to use for text polish:\n\n"
            "1. OpenAI (gpt-5-nano) — fast, cheap\n"
            "2. Anthropic (Claude Haiku) — fast, cheap\n\n"
            "Currently: %s" % config.get("llm_provider", LLM_OPENAI)
        ),
        buttons=["1. OpenAI", "Cancel", "2. Anthropic"],
    )

    if button == 0:
        config.set("llm_provider", LLM_OPENAI)
        logger.info("LLM provider set to OpenAI")
    elif button == 2:
        config.set("llm_provider", LLM_ANTHROPIC)
        logger.info("LLM provider set to Anthropic")


def _configure_openai_stt_model(config: Config):
    """Choose OpenAI STT model variant. Only called when OpenAI API engine is selected."""
    current_model = config.get("openai_stt_model", "gpt-4o-mini-transcribe")

    button = show_alert(
        title="OpenAI STT Model",
        message=(
            "Choose the OpenAI speech-to-text model:\n\n"
            "1. gpt-4o-mini-transcribe — faster, lower cost (recommended)\n"
            "2. whisper-1 — legacy, widely tested\n\n"
            "Currently: %s" % current_model
        ),
        buttons=["1. gpt-4o-mini-transcribe", "Cancel", "2. whisper-1"],
    )

    if button == 0:
        config.set("openai_stt_model", "gpt-4o-mini-transcribe")
        logger.info("OpenAI STT model set to gpt-4o-mini-transcribe")
    elif button == 2:
        config.set("openai_stt_model", "whisper-1")
        logger.info("OpenAI STT model set to whisper-1")


def _configure_stt_language(config: Config):
    """Configure the STT transcription language via free-text ISO 639-1 code entry."""
    current_lang = config.get("stt_language", "en")
    current_display = "Auto-detect" if current_lang == "auto" else current_lang

    text = show_text_input(
        title="STT Language",
        message=(
            "Enter the ISO 639-1 language code for transcription,\n"
            "or 'auto' for automatic language detection.\n\n"
            "auto=Auto-detect  en=English  es=Spanish  fr=French\n"
            "de=German  zh=Chinese  ja=Japanese  pt=Portuguese\n"
            "ko=Korean  it=Italian  nl=Dutch  ru=Russian  ar=Arabic\n\n"
            "Currently: %s" % current_display
        ),
        default_text=current_lang,
        ok_button="Save",
        cancel_button="Keep Current",
    )

    if text and text.strip():
        lang_code = text.strip().lower()
        if lang_code == "auto":
            config.set("stt_language", "auto")
        else:
            lang_code = lang_code[:2]  # normalize: max 2 chars
            config.set("stt_language", lang_code)
        logger.info("STT language set to: %s", lang_code)


def show_dictionary_editor(config: Config):
    """Simple dictionary editor using native dialogs."""
    from openmic.dictionary import PersonalDictionary
    dictionary = PersonalDictionary(config)

    entries = dictionary.get_entries()
    if entries:
        entry_list = "\n".join(
            "- %s%s" % (e["term"], (": " + e["definition"]) if e.get("definition") else "")
            for e in entries
        )
    else:
        entry_list = "(empty)"

    button = show_alert(
        title="Personal Dictionary",
        message="Your custom words and terms:\n\n%s\n\n"
        "These terms are used to improve transcription accuracy." % entry_list,
        buttons=["Add Entry", "Remove Entry", "Close"],
    )

    if button == 0:  # Add
        term = show_text_input(
            title="Add Dictionary Entry",
            message="Enter a term (e.g., 'Kubernetes'):",
            default_text="",
            ok_button="Next",
            cancel_button="Cancel",
        )
        if term and term.strip():
            term = term.strip()
            definition = show_text_input(
                title="Add Dictionary Entry",
                message="Optional definition for '%s'\n(leave blank to skip):" % term,
                default_text="",
                ok_button="Save",
                cancel_button="Skip",
            )
            definition = definition.strip() if definition else ""
            dictionary.add_entry(term, definition)
            logger.info("Added dictionary entry: %s", term)
            rumps.notification("OpenMic", "Dictionary", "Added: %s" % term)

    elif button == 1:  # Remove
        if not entries:
            show_alert(title="Dictionary Empty", message="No entries to remove.", buttons=["OK"])
            return
        term = show_text_input(
            title="Remove Dictionary Entry",
            message="Enter the term to remove:",
            default_text="",
            ok_button="Remove",
            cancel_button="Cancel",
        )
        if term and term.strip():
            dictionary.remove_entry(term.strip())
            logger.info("Removed dictionary entry: %s", term.strip())
            rumps.notification("OpenMic", "Dictionary", "Removed: %s" % term.strip())
