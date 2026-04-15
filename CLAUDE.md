# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenMic is a native macOS menu bar app for system-wide voice-to-text dictation with AI polishing. The user presses a global hotkey (default: Fn) to record audio, which gets transcribed via STT and cleaned up by an LLM, then pasted into the focused app.

## Commands

```bash
make setup          # Create .venv and install dependencies
make setup-mlx      # Also install MLX Whisper (Apple Silicon local STT)
make run            # Run app from terminal (always use this, NOT python -m openmic directly)
make build          # Build py2app bundle → dist/OpenMic.app
make clean          # Remove build artifacts
make test           # Run pytest
```

To deploy after build:
```bash
ditto dist/OpenMic.app /Applications/OpenMic.app
```

## Architecture

### Full Data Flow

```
hotkey.py (CGEvent tap, system thread)
    → queue.put("press" / "release")
app.py (@rumps.timer 20Hz, main thread)
    → drains queue, transitions state machine
    → calls pipeline.py on background thread
pipeline.py
    → recorder.py (sounddevice, PortAudio callback thread)
    → transcriber.py (OpenAI API / MLX Whisper)
    → polisher.py (OpenAI / Anthropic LLM)
    → paster.py (NSPasteboard + simulated Cmd+V)
    → overlay.py (floating pill NSWindow near cursor)
```

### State Machine (app.py)

Three states: `idle` → `recording` → `processing` → `idle`

All state transitions happen on the **main thread** via the 20Hz timer `_process_hotkey_queue()`. The CGEvent tap runs on a system thread and only puts strings into `self._hotkey_queue` — never calls state-change code directly.

### Key Modules

| File | Responsibility |
|------|---------------|
| `src/openmic/app.py` | `OpenMicApp(rumps.App)` — menu bar, state machine, wires everything |
| `src/openmic/pipeline.py` | Orchestrates recorder → transcriber → polisher → paster |
| `src/openmic/hotkey.py` | `HotkeyManager` — global hotkey via CGEvent tap |
| `src/openmic/recorder.py` | `AudioRecorder` — microphone capture via sounddevice |
| `src/openmic/transcriber.py` | `Transcriber` — OpenAI / MLX Whisper |
| `src/openmic/polisher.py` | `Polisher` — LLM filler-word removal (OpenAI / Anthropic) |
| `src/openmic/paster.py` | `Paster` — clipboard + Cmd+V simulation |
| `src/openmic/config.py` | `Config` — JSON persistence at `~/Library/Application Support/OpenMic/config.json` |
| `src/openmic/constants.py` | All defaults, key codes, sample rates |
| `src/openmic/errors.py` | Typed error hierarchy (`OpenMicError`, `InvalidAPIKeyError`, etc.) |
| `src/openmic/history.py` | Persistent dictation history (JSONL, capped at 200 entries) |
| `src/openmic/ui/overlay.py` | `RecordingOverlay` — floating pill NSWindow with pulse + level meter |
| `src/openmic/ui/native_dialogs.py` | NSAlert wrappers, hotkey capture, dropdown picker |
| `src/openmic/ui/history_window.py` | Dictation history viewer (NSTableView) |
| `src/openmic/ui/settings_window.py` | Settings dialogs |
| `src/openmic/ui/onboarding.py` | First-run setup wizard |

## Critical Patterns

### Thread Safety

- CGEvent tap fires on a **system thread** — never mutate app state from tap callbacks
- Queue model: tap → `self._hotkey_queue.put(...)` → main thread drains at 20Hz
- All UI updates from background threads must use `_run_on_main_thread(fn)` (wraps `performSelectorOnMainThread_withObject_waitUntilDone_`)

### API Client Reuse

OpenAI and Anthropic clients are cached and reused across calls (connection pooling). Recreated only if API key changes. Pattern lives in `transcriber.py` and `polisher.py`.

### Config

All settings auto-persist on `config.set(key, value)`. Defaults in `constants.py`. Config keys for engines: `stt_engine` ∈ {`openai_api`, `mlx_whisper`}, `llm_provider` ∈ {`openai`, `anthropic`}.

### py2app Build

`setup.py` contains the `py2app` configuration. Use `semi_standalone` mode (required for PortAudio library loading). Privacy plist descriptions are included for microphone and accessibility. The entry point is `src/openmic/__main__.py`.


## macOS-Specific Considerations

- The app **requires** Accessibility permissions (for CGEvent tap and Cmd+V simulation) and Microphone permissions
- `rumps` is the menu bar framework; its timer callbacks run on the main Cocoa thread
- Quartz (`CGEvent`) is used for global hotkey detection — not NSEvent (NSEvent local monitors don't work when other apps have focus)
- After showing modal dialogs (NSAlert), the CGEvent tap must be explicitly re-enabled
