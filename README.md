# OpenMic — Speak anywhere, type everywhere.

<em>Simple, fast, no-fuss voice typing with BYOK (Bring-Your-Own-Key).</em>

Press a hotkey anywhere on macOS to dictate. Your speech is transcribed and polished by the context-aware AI, then automatically pasted.

---

## 🚀 Quick Start

### Option 1: Run from Terminal (Development)
```bash
cd /path/to/openmic
make run          # uses .venv/bin/python — do NOT use bare python -m openmic
```

### Option 2: Run as .app Bundle (Recommended)
```bash
open /Applications/OpenMic.app
```

Or build it yourself — see [Rebuilding the .app](#rebuilding-the-app) below.

---

## 📋 First-Time Setup

When you launch OpenMic for the first time:

1. **Onboarding wizard** will guide you through:
   - Granting Accessibility permission (for global hotkey + paste)
   - Granting Microphone permission (for recording)
   - Entering your OpenAI API key

2. **Grant permissions in System Settings**:
   - **System Settings → Privacy & Security → Accessibility** → Add "OpenMic"
   - **System Settings → Privacy & Security → Microphone** → Add "OpenMic"

3. **Get an API key**:
   - OpenAI: https://platform.openai.com/api-keys
   - (Optional) Anthropic: https://console.anthropic.com/keys

---

## 🎙️ How to Use

### Hold-to-Record (default)
1. **Hold Fn** → microphone icon turns red 🔴, bottom-center pill expands to show "Recording..."
2. **Speak** your message
3. **Release Fn** → icon turns yellow 🟡, pill shows "Polishing..."
4. **Polished text is pasted** automatically into your focused app, pill briefly shows green "Done" ✓ then collapses

### Toggle Mode (alternative)
1. **Press Fn once** → starts recording
2. **Press Fn again** → stops and pastes

Switch between modes in **Settings → Hotkey**.

### Cancel During Processing
Changed your mind? **Press the hotkey while processing** to cancel — OpenMic returns to idle without pasting anything.

### Sound Feedback
OpenMic plays subtle macOS system sounds to confirm state changes:
- **Tink** when recording starts
- **Glass** when recording stops and processing begins
- **Funk** when processing is cancelled

Disable in config: set `sound_feedback_enabled` to `false` in `~/Library/Application Support/OpenMic/config.json`.

### Example

**You say:** "um, so like, this is a test message, you know?"

**OpenMic pastes:** "This is a test message."

### Context-Aware Polishing

OpenMic automatically captures the app you're typing in and its window title, so the LLM can tailor the polished output to fit your context.

**Example — typing in a Slack DM:**

> **You say:** "hey can we move the standup to like 10 30 instead"
>
> **OpenMic pastes:** "Hey, can we move the standup to 10:30 instead?"

**Example — typing in a code review tool:**

> **You say:** "um this function looks like it could be refactored to reduce duplication"
>
> **OpenMic pastes:** "This function could be refactored to reduce duplication."

The context is captured at the moment you release the hotkey (the app you were just typing in), so it's always accurate even if you switch windows during processing. On native AppKit apps (Notes, Mail, TextEdit), the existing text in the focused field is also included. Electron-based apps (Slack, VS Code) provide app name and window title only.

---

## ⚙️ Settings

Click the **microphone icon** in your menu bar → **Settings...**

The settings dialog has four buttons (left to right):

| Button | What it configures |
|---|---|
| **Engine Settings** | STT engine (Whisper API / local) and LLM provider (OpenAI / Anthropic) |
| **API Keys** | OpenAI and Anthropic API keys |
| **Hotkey** | Hotkey mode (hold vs toggle) and key combination |
| **Close** | Dismiss the dialog |

### Hotkey Customization

OpenMic supports any modifier + key combination as your hotkey:

1. Open **Settings → Hotkey → Change Hotkey**
2. A dialog appears with a capture field
3. Press your desired combination (e.g. `Cmd+Option+K`)
4. Click **Save** — the new hotkey is active immediately, no restart needed

**Requirements**: Must include at least one modifier key (Cmd, Shift, Option, or Ctrl).

### STT Engines

| Engine | Model | Speed | Quality | Requires |
|---|---|---|---|---|
| OpenAI Whisper API | `gpt-4o-mini-transcribe` (default) | Fast | Best | Internet + API key |
| OpenAI Whisper API | `whisper-1` (legacy) | Slower | Good | Internet + API key |
| Local Whisper (mlx) | whisper-small | Fast | Great | Apple Silicon |

The default model `gpt-4o-mini-transcribe` is faster and more accurate than the legacy `whisper-1`. The active model is stored in config and can be changed directly in `~/Library/Application Support/OpenMic/config.json` under `openai_stt_model`.

### Language Support

OpenMic supports 100+ languages via Whisper. Configure in **Settings → Engine Settings → STT Language**:

- Enter an ISO 639-1 code (e.g. `en`, `es`, `fr`, `de`, `zh`, `ja`, `ko`)
- Enter `auto` for **automatic language detection** — Whisper will detect the spoken language

Auto-detection works with both STT engines (OpenAI API and MLX Whisper).

### LLM Providers

| Provider | Model | Notes |
|---|---|---|
| OpenAI | gpt-5-nano | Fast, cheap |
| Anthropic | Claude Haiku | Fast, cheap |

---

## ⚡ Performance

End-to-end latency (hotkey release → text pasted) depends on audio length and network conditions:

| Scenario | Typical latency |
|---|---|
| 5-second dictation, OpenAI cloud | ~2–5s |
| Consecutive dictations (warm connection) | ~1.5–4s |
| Local Whisper (Apple Silicon) | ~1–2s |

**Optimizations applied:**
- **`gpt-4o-mini-transcribe`** — faster than legacy `whisper-1` for cloud STT
- **Connection pooling** — OpenAI and Anthropic API clients are reused across calls (avoids per-call TLS handshake overhead)
- **In-memory audio encoding** — WAV audio is encoded to memory, not written to a temp file, before being sent to the API
- **Reduced paste delays** — clipboard settle and restore delays tuned down from 250ms to 120ms total
- **Local model pre-warming** — if using a local Whisper engine, the model loads at startup in a background thread so the first dictation isn't slow

---

## 🔧 Troubleshooting

### "Hotkey doesn't work"
- Grant Accessibility permission to OpenMic in System Settings
- Restart OpenMic after granting permission
- Check the hotkey isn't conflicting with another app (change it in Settings → Hotkey)

### "No microphone input"
- Grant Microphone permission to OpenMic in System Settings
- Check your microphone is connected and selected as default input

### "403 or 400 API errors"
- Verify your API key is correct in Settings → API Keys
- Check your OpenAI/Anthropic account has credits

### "Text doesn't paste"
- Grant Accessibility permission (needed for simulated Cmd+V)
- Ensure a text field is focused when processing completes

---

## 🏗️ Rebuilding the .app

If you modify the code:

```bash
# Clean previous build
rm -rf build dist

# Rebuild
.venv/bin/python setup.py py2app

# Deploy to Applications folder
ditto dist/OpenMic.app /Applications/OpenMic.app
```

---

## 📦 Project Structure

```
openmic/
├── src/openmic/
│   ├── app.py              # Menu bar app + state machine
│   ├── hotkey.py           # Global hotkey via CGEvent tap (hold + toggle modes)
│   ├── recorder.py         # Audio recording (sounddevice)
│   ├── transcriber.py      # Speech-to-text (Whisper)
│   ├── polisher.py         # LLM text polish (OpenAI/Anthropic)
│   ├── context.py          # App context capture via NSWorkspace + AXUIElement
│   ├── paster.py           # Clipboard + paste automation
│   ├── pipeline.py         # Orchestrates the full flow
│   ├── config.py           # JSON config persistence
│   ├── constants.py        # Key codes, defaults, mode constants
│   ├── dictionary.py       # Personal dictionary CRUD
│   ├── permissions.py      # Accessibility + microphone checks
│   └── ui/
│       ├── overlay.py          # Always-visible overlay pill with animations (NSWindow)
│       ├── native_dialogs.py   # NSAlert wrappers + hotkey capture
│       ├── settings_window.py  # Settings dialogs
│       └── onboarding.py       # First-run setup wizard
├── setup.py                # py2app configuration
└── pyproject.toml          # Dependencies
```

Config stored at: `~/Library/Application Support/OpenMic/config.json`

---

## 🔒 Privacy & Security

- **Your API key** is stored locally in `~/Library/Application Support/OpenMic/config.json`
- **Audio** is processed by your chosen STT engine (cloud or local)
- **No data** is sent anywhere except to your configured API providers
- **Bring Your Own Key** model — you control costs and usage

---

## 📄 License

MIT License - see LICENSE file for details.

---

## 🙏 Credits

Built with:
- [rumps](https://github.com/jaredks/rumps) - macOS menu bar apps in Python
- [sounddevice](https://python-sounddevice.readthedocs.io/) - Audio I/O
- [PyObjC](https://pyobjc.readthedocs.io/) - macOS native APIs
- [OpenAI Whisper](https://platform.openai.com/docs/guides/speech-to-text) - Speech recognition
- [OpenAI GPT](https://platform.openai.com/) / [Anthropic Claude](https://www.anthropic.com/) - Text polishing
- [Claude Code](https://claude.ai/)
