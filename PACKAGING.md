# Packaging Guide - OpenMic.app

## What Was Built

A standalone macOS application bundle (`OpenMic.app`) that includes:
- All Python dependencies bundled
- No need for terminal or visible Python installation
- Native macOS app behavior (menu bar, permissions, etc.)
- Can be distributed to other Macs

---

## Build Process

### 1. Install py2app (already done)
```bash
.venv/bin/pip install py2app
```

### 2. Build the .app bundle
```bash
.venv/bin/python setup.py py2app
```

This creates:
- `build/` - temporary build artifacts (can be deleted)
- `dist/OpenMic.app` - the final application bundle

### 3. Launch the app
```bash
open dist/OpenMic.app
```

---

## What py2app Does

1. **Bundles Python interpreter** - Includes Python 3.9 inside the .app
2. **Includes all dependencies** - Packages numpy, PyObjC, rumps, openai, anthropic, etc.
3. **Creates proper macOS structure**:
   ```
   OpenMic.app/
   ├── Contents/
   │   ├── Info.plist          # App metadata, permissions
   │   ├── MacOS/
   │   │   └── OpenMic            # Executable launcher
   │   ├── Resources/
   │   │   ├── icon.icns       # App icon
   │   │   ├── lib/python3.9/  # Python + packages
   │   │   └── ...
   │   └── Frameworks/         # Native libraries
   ```

4. **Sets proper permissions** - Info.plist includes:
   - `LSUIElement: True` - No dock icon (menu bar only)
   - `NSMicrophoneUsageDescription` - Microphone permission prompt
   - `NSAppleEventsUsageDescription` - Accessibility permission prompt

---

## Distribution Options

### Option 1: Copy to Applications folder
```bash
cp -r dist/OpenMic.app /Applications/
```

### Option 2: Create a DMG (for sharing)
```bash
# Install create-dmg if needed
brew install create-dmg

# Create DMG
create-dmg \
  --volname "OpenMic" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --icon "OpenMic.app" 200 190 \
  --hide-extension "OpenMic.app" \
  --app-drop-link 600 185 \
  "OpenMic-0.1.0.dmg" \
  "dist/"
```

Users can then:
1. Download `OpenMic-0.1.0.dmg`
2. Open it
3. Drag `OpenMic.app` to their Applications folder

### Option 3: Create a ZIP (simpler sharing)
```bash
cd dist
zip -r OpenMic-0.1.0.zip OpenMic.app
cd ..
```

---

## Code Signing (Optional, for Distribution)

If you want to distribute OpenMic to other users without Gatekeeper warnings:

### 1. Get an Apple Developer account
- Sign up at https://developer.apple.com ($99/year)
- Get a "Developer ID Application" certificate

### 2. Sign the app
```bash
codesign --force --deep --sign "Developer ID Application: Your Name" dist/OpenMic.app
```

### 3. Notarize the app (required for macOS 10.15+)
```bash
# Create a ZIP for notarization
ditto -c -k --keepParent dist/OpenMic.app OpenMic.zip

# Submit for notarization
xcrun notarytool submit OpenMic.zip \
  --apple-id "your@email.com" \
  --password "app-specific-password" \
  --team-id "YOUR_TEAM_ID" \
  --wait

# Staple the notarization ticket
xcrun stapler staple dist/OpenMic.app
```

**Without code signing**, users will see:
- "OpenMic.app is from an unidentified developer"
- They can right-click → Open → Open anyway (one time)
- Or run: `sudo xattr -rd com.apple.quarantine OpenMic.app`

---

## Debugging the .app Bundle

### Check what's inside
```bash
ls -la dist/OpenMic.app/Contents/
```

### View the Info.plist
```bash
cat dist/OpenMic.app/Contents/Info.plist
```

### Run the app from terminal (see logs)
```bash
dist/OpenMic.app/Contents/MacOS/OpenMic
```

This shows all `print()` and `logger.*()` output, useful for debugging.

### Check for missing dependencies
```bash
# See what modules were included
ls dist/OpenMic.app/Contents/Resources/lib/python3.9/site-packages/
```

---

## File Size

The built `OpenMic.app` is approximately **150-200 MB** because it includes:
- Python interpreter (~30 MB)
- NumPy (~25 MB)
- PyObjC frameworks (~20 MB)
- sounddevice/soundfile (~10 MB)
- OpenAI/Anthropic SDK (~5 MB)
- Everything else (~60-110 MB)

This is normal for bundled Python apps. Users don't need to install anything.

---

## Rebuilding After Code Changes

```bash
# 1. Make your code changes in src/openmic/

# 2. Clean previous build
rm -rf build dist

# 3. Rebuild
.venv/bin/python setup.py py2app

# 4. Test
open dist/OpenMic.app
```

**Tip:** For faster iteration during development, use `python -m openmic` instead of rebuilding the .app every time. Only rebuild when you want to test the packaged app or distribute it.

---

## Configuration File Location

When running as .app bundle:
```
~/Library/Application Support/OpenMic/config.json
```

This is the same location whether running from source or as .app, so your settings persist.

---

## Common Issues

### "Application is damaged and can't be opened"
```bash
sudo xattr -rd com.apple.quarantine /Applications/OpenMic.app
```

### App crashes on launch
```bash
# Run from terminal to see error messages
dist/OpenMic.app/Contents/MacOS/OpenMic
```

### Missing modules
Add to `setup.py` OPTIONS `"packages"` list:
```python
"packages": ["openmic", "rumps", "sounddevice", "soundfile", "openai", "anthropic", "your_module"],
```

### Native library not found
Add to `setup.py` OPTIONS `"includes"` list:
```python
"includes": ["AppKit", "Quartz", "AVFoundation", "YourFramework"],
```

---

## Comparison: .app vs Source

| Feature | Running from Source | Running as .app |
|---------|---------------------|-----------------|
| Permissions | Terminal app | OpenMic app |
| Dock icon | Terminal icon | No icon (menu bar only) |
| Distribution | Share code + deps | Share single .app file |
| Updates | Git pull | Replace .app file |
| Debugging | Easy (see all logs) | Harder (need terminal launch) |
| User experience | Developer-only | End-user friendly |

---

## Success Checklist

✅ `.app` bundle built successfully
✅ App launches without errors
✅ Menu bar icon appears
✅ Permissions prompt for Accessibility
✅ Permissions prompt for Microphone
✅ Hotkey (Fn) works
✅ Recording → Processing → Paste works
✅ Settings UI accessible

If all checkboxes pass, your app is ready for distribution! 🎉
