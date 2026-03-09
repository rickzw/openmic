# Installation Guide

## Quick Install (Recommended)

1. **Copy OpenMic.app to Applications**:
   ```bash
   cp -r dist/OpenMic.app /Applications/
   ```

2. **Launch OpenMic**:
   ```bash
   open /Applications/OpenMic.app
   ```

   Or open via Spotlight (Cmd+Space, type "OpenMic")

3. **Follow the onboarding wizard**:
   - Grant Accessibility permission
   - Grant Microphone permission
   - Enter your OpenAI API key

4. **Start using OpenMic**:
   - Press **Fn** to start recording
   - Press **Fn** again to stop and process
   - Your polished text will be automatically pasted

---

## Permissions Setup

### Accessibility Permission (Required)

**Why:** OpenMic needs this to:
- Register the global hotkey
- Simulate Cmd+V to paste text into other apps

**How to grant:**
1. **System Settings** → **Privacy & Security** → **Accessibility**
2. Click the **+** button or toggle **OpenMic** on
3. Restart OpenMic

### Microphone Permission (Required)

**Why:** OpenMic needs this to record your voice for transcription.

**How to grant:**
1. macOS will prompt you automatically when OpenMic first tries to record
2. Click **Allow** when prompted
3. Or manually: **System Settings** → **Privacy & Security** → **Microphone** → Enable **OpenMic**

---

## Getting an API Key

### OpenAI (Required for default setup)

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Click **Create new secret key**
4. Copy the key (starts with `sk-...`)
5. Paste into OpenMic's onboarding wizard or Settings

**Cost:** ~$0.006 per minute of audio transcription + ~$0.0001 per polish operation

### Anthropic (Optional)

1. Go to https://console.anthropic.com/keys
2. Sign up or log in
3. Create an API key
4. Add to OpenMic Settings if you want to use Claude for polishing

---

## Alternative: Run from Source

If you don't want to use the .app bundle:

```bash
cd /path/to/openmic
.venv/bin/python -m openmic
```

**Note:** When running from source, you'll need to grant permissions to your **Terminal app** (Terminal.app, iTerm2, VS Code, etc.) instead of "OpenMic".

---

## Uninstall

1. **Remove the app**:
   ```bash
   rm -rf /Applications/OpenMic.app
   ```

2. **Remove config and data**:
   ```bash
   rm -rf ~/Library/Application\ Support/OpenMic
   ```

3. **Revoke permissions** (optional):
   - System Settings → Privacy & Security → Accessibility → Remove OpenMic
   - System Settings → Privacy & Security → Microphone → Remove OpenMic

---

## Updating OpenMic

1. **Rebuild** the app (if you've made code changes):
   ```bash
   cd /path/to/openmic
   rm -rf build dist
   .venv/bin/python setup.py py2app
   ```

2. **Replace** the old app:
   ```bash
   rm -rf /Applications/OpenMic.app
   cp -r dist/OpenMic.app /Applications/
   ```

3. **Restart** OpenMic

Your settings and API keys are preserved in `~/Library/Application Support/OpenMic/config.json`.

---

## Troubleshooting

### "OpenMic is damaged and can't be opened"

This happens on macOS Catalina+ if the app isn't code-signed. Fix:

```bash
sudo xattr -rd com.apple.quarantine /Applications/OpenMic.app
```

### Permissions not working

1. **Remove OpenMic from Accessibility/Microphone lists**
2. **Restart your Mac** (permission changes sometimes require reboot)
3. **Re-add OpenMic** when prompted
4. **Restart OpenMic.app**

### Hotkey conflicts

If the default hotkey (Fn) conflicts with another app, you can change it in **Settings → Hotkey**.

---

## Development Setup

For development work:

```bash
# Clone/navigate to repo
cd /path/to/openmic

# Create virtual environment and install dependencies
make setup

# Or also install local Whisper support (Apple Silicon)
make setup-mlx

# Run in development mode
make run
```

---

## Next Steps

- Read the [README.md](README.md) for usage instructions
- Configure your Personal Dictionary in Settings for better recognition of custom terms
