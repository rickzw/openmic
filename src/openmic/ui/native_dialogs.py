"""Native macOS dialogs using NSAlert directly.

Provides clean wrappers around AppKit NSAlert for predictable dialog behavior.
Uses rumps.Window for text input (supports paste) and NSAlert for button dialogs.
"""

import logging
from typing import Optional

import objc
import rumps
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSAlertThirdButtonReturn,
    NSApplication,
    NSModalPanelWindowLevel,
    NSObject,
    NSPopUpButton,
    NSTextField,
    NSMakeRect,
    NSFont,
    NSColor,
    NSTextAlignmentCenter,
    NSBezelBorder,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
)
from Quartz import (
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskControl,
)

logger = logging.getLogger(__name__)


class _LabelUpdater(NSObject):
    """Tiny NSObject used to marshal label updates onto the main AppKit thread.

    The CGEvent tap callback fires on a Quartz/system thread.  AppKit UI calls
    (setStringValue_, setTextColor_) must happen on the main thread.  We use
    performSelectorOnMainThread_withObject_waitUntilDone_ to schedule the update.
    """

    # ivar-style attributes — set before calling performSelector
    _label = None
    _text = None
    _color = None

    def updateLabel_(self, _sender):
        if self._label is not None:
            if self._text is not None:
                self._label.setStringValue_(self._text)
            if self._color is not None:
                self._label.setTextColor_(self._color)


def _ensure_alert_visible(alert):
    """Ensure an NSAlert's window is visible in LSUIElement (menu bar) apps.

    LSUIElement apps have no dock icon or main window, so NSAlert.runModal()
    can render behind other windows. This forces the alert to float above
    everything, matching the approach used by overlay.py for its NSWindow.
    """
    alert.layout()
    alert_window = alert.window()
    alert_window.setLevel_(NSModalPanelWindowLevel)
    alert_window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)


def show_alert(
    title: str,
    message: str,
    buttons: list[str],
) -> int:
    """Show a native alert dialog with custom buttons.

    Args:
        title: Alert title (large text at top)
        message: Alert message (smaller text below title)
        buttons: List of button titles (1-3 buttons). First button is default/primary.

    Returns:
        Button index (0 = first button, 1 = second, 2 = third)
    """
    # Activate app to ensure dialog appears in foreground
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)

    # Add buttons — NSAlert supports any number; constants start at 1000
    for button_title in buttons:
        alert.addButtonWithTitle_(button_title)

    _ensure_alert_visible(alert)

    # Run modal and convert response
    response = alert.runModal()

    # NSAlert button return values start at NSAlertFirstButtonReturn (1000)
    # and increment by 1 for each additional button.
    button_map = {
        NSAlertFirstButtonReturn + i: i for i in range(len(buttons))
    }

    button_index = button_map.get(response, -1)
    logger.info("Alert '%s' response: %s → button index %s", title, response, button_index)

    return button_index


def show_text_input(
    title: str,
    message: str,
    default_text: str = "",
    ok_button: str = "OK",
    cancel_button: str = "Cancel",
) -> Optional[str]:
    """Show a text input dialog using rumps.Window (supports paste).

    Args:
        title: Dialog title
        message: Prompt message
        default_text: Pre-filled text (optional)
        ok_button: OK button title
        cancel_button: Cancel button title

    Returns:
        User's text input, or None if cancelled
    """
    # Activate app
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    # Use rumps.Window which DOES support paste
    window = rumps.Window(
        title=title,
        message=message,
        default_text=default_text,
        ok=ok_button,
        cancel=cancel_button,
        dimensions=(400, 24),
    )
    window.icon = None

    # Ensure the underlying NSAlert is visible in LSUIElement apps
    _ensure_alert_visible(window._alert)

    response = window.run()

    # rumps.Window returns a Response object with:
    # - response.clicked: 1 for OK, 0 for Cancel
    # - response.text: the entered text
    if response.clicked == 1 and response.text and response.text.strip():
        logger.info("Text input '%s': user entered text (length=%s)", title, len(response.text))
        return response.text.strip()
    else:
        logger.info("Text input '%s': user cancelled or empty", title)
        return None


# ---------------------------------------------------------------------------
# Hotkey capture dialog
# ---------------------------------------------------------------------------

# Key code → human-readable name for common non-character keys
_KEYCODE_NAMES = {
    49: "Space", 36: "Return", 48: "Tab", 51: "Delete",
    123: "←", 124: "→", 125: "↓", 126: "↑",
    116: "Page Up", 121: "Page Down", 115: "Home", 119: "End",
    96: "F5", 97: "F6", 98: "F7", 99: "F8",
    100: "F3", 101: "F4", 103: "F5", 109: "F10",
    118: "F4", 120: "F5", 122: "F1", 120: "F2",
}

_MOD_FLAGS = [
    (kCGEventFlagMaskCommand,  "Cmd"),
    (kCGEventFlagMaskShift,    "Shift"),
    (kCGEventFlagMaskAlternate,"Option"),
    (kCGEventFlagMaskControl,  "Ctrl"),
]

# Pure-modifier key codes — ignore these as the "main" key
_MODIFIER_KEYCODES = {54, 55, 56, 57, 58, 59, 60, 61, 62, 63}


def _describe_combo(vk: int, mods: int, chars: str) -> str:
    """Build a human-readable string like 'Cmd+Shift+Space'."""
    parts = [name for flag, name in _MOD_FLAGS if mods & flag]
    key_name = _KEYCODE_NAMES.get(vk) or (chars.upper() if chars else "Key%d" % vk)
    parts.append(key_name)
    return "+".join(parts)


def _process_hotkey_event(event):
    """Extract hotkey info from an NSEvent, returning (vk, mods, chars) or None.

    Returns None for pure-modifier key presses.
    Maps NSEvent modifier flags to CGEvent flags for HotkeyManager compatibility.
    """
    vk = event.keyCode()
    # Ignore bare modifier key presses
    if vk in _MODIFIER_KEYCODES:
        return None

    # NSEvent modifier flags use different bit positions than CGEvent flags.
    # Map NSEvent flags → CGEvent flags so they're consistent with HotkeyManager.
    ns_flags = event.modifierFlags()
    mods = 0
    NSCommandKeyMask = 1 << 20
    NSShiftKeyMask = 1 << 17
    NSAlternateKeyMask = 1 << 19
    NSControlKeyMask = 1 << 18
    if ns_flags & NSCommandKeyMask:
        mods |= kCGEventFlagMaskCommand
    if ns_flags & NSShiftKeyMask:
        mods |= kCGEventFlagMaskShift
    if ns_flags & NSAlternateKeyMask:
        mods |= kCGEventFlagMaskAlternate
    if ns_flags & NSControlKeyMask:
        mods |= kCGEventFlagMaskControl

    chars = event.charactersIgnoringModifiers() or ""
    return vk, mods, chars


def show_hotkey_capture(
    current_desc: str = "Fn",
    hotkey_manager=None,
) -> Optional[tuple]:
    """Show a dialog that captures a live keypress as the new hotkey.

    Uses the HotkeyManager's CGEvent tap (capture_callback) to intercept key
    events at the system level — this works regardless of which app currently
    has OS-level keyboard focus, and suppresses the event so it doesn't leak
    to other apps (e.g. Terminal).

    Unlike NSEvent.addLocalMonitorForEventsMatchingMask (which only fires when
    the OpenMic app's window has focus), the CGEvent tap fires before any app sees
    the keystroke, making it reliable when run from a terminal.

    Args:
        current_desc: Human-readable description of the current hotkey combo.
        hotkey_manager: Live HotkeyManager instance. capture_callback is set
                        on it during capture so the tap intercepts keypresses.
                        If None, falls back silently (no capture).

    Returns:
        (vk, mods, description) tuple if the user confirmed a new combo,
        or None if cancelled / no combo entered.
    """
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_("Set Custom Hotkey")
    alert.setInformativeText_(
        "Press your desired key combination.\n"
        "Current: %s" % current_desc
    )
    alert.addButtonWithTitle_("Save")
    alert.addButtonWithTitle_("Cancel")

    # Display field to show the captured combo (read-only label, not for input)
    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 36))
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setBezeled_(True)
    label.setBezelStyle_(NSBezelBorder)
    label.setAlignment_(NSTextAlignmentCenter)
    label.setFont_(NSFont.systemFontOfSize_(14.0))
    label.setStringValue_("Press your hotkey combination\u2026")
    label.setTextColor_(NSColor.secondaryLabelColor())
    alert.setAccessoryView_(label)

    # Mutable capture state — written from CGEvent tap thread, read on main thread
    capture_state = {"vk": None, "mods": None, "description": None}

    def _on_capture(vk, mods):
        """Called from CGEvent tap thread when a qualifying keypress is intercepted.

        Must not call AppKit directly (wrong thread).  Instead, schedule a label
        update on the main thread using performSelectorOnMainThread_.
        """
        desc = _describe_combo(vk, mods, "")
        capture_state["vk"] = vk
        capture_state["mods"] = mods
        capture_state["description"] = desc
        logger.info("Hotkey captured via CGEvent tap: %s (vk=%d, mods=0x%x)", desc, vk, mods)

        # Marshal the UI update to the main AppKit thread
        updater = _LabelUpdater.alloc().init()
        updater._label = label
        updater._text = "\u2713  " + desc
        updater._color = NSColor.systemGreenColor()
        updater.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateLabel:", None, False
        )

    # Register capture_callback on the HotkeyManager BEFORE runModal.
    # The CGEvent tap (already running) will call _on_capture on the first
    # qualifying keydown and then clear capture_callback automatically.
    if hotkey_manager is not None:
        hotkey_manager.capture_callback = _on_capture
        hotkey_manager._key_is_held = False
        logger.info("HotkeyManager capture_callback set")

    # Bring the alert window to the front (visual polish only — capture works
    # regardless of which app has focus because CGEvent tap is system-wide)
    _ensure_alert_visible(alert)
    alert_window = alert.window()
    alert_window.makeKeyAndOrderFront_(None)

    try:
        response = alert.runModal()
    finally:
        # Always clear the capture callback so the tap returns to normal operation
        if hotkey_manager is not None:
            hotkey_manager.capture_callback = None
            hotkey_manager._key_is_held = False
            logger.info("HotkeyManager capture_callback cleared")

    if response != NSAlertFirstButtonReturn:
        return None

    if capture_state["vk"] is None:
        logger.info("Hotkey capture: user clicked Save but no combo was entered")
        return None

    vk = capture_state["vk"]
    mods = capture_state["mods"]
    desc = capture_state["description"]
    return vk, mods, desc


def show_picker(
    title: str,
    message: str,
    options: list,
    default: str = None,
    ok_button: str = "OK",
    cancel_button: str = "Cancel",
) -> Optional[str]:
    """Show a native picker dialog with a dropdown (NSPopUpButton).

    Args:
        title: Alert title
        message: Prompt message shown above the picker
        options: List of option strings to display
        default: Pre-selected option (must be in options); defaults to first
        ok_button: OK button title
        cancel_button: Cancel button title

    Returns:
        The selected option string, or None if cancelled.
    """
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_(ok_button)
    alert.addButtonWithTitle_(cancel_button)

    popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 26))
    for option in options:
        popup.addItemWithTitle_(option)

    if default and default in options:
        popup.selectItemWithTitle_(default)

    alert.setAccessoryView_(popup)
    _ensure_alert_visible(alert)

    response = alert.runModal()

    if response != NSAlertFirstButtonReturn:
        logger.info("Picker '%s': user cancelled", title)
        return None

    selected = popup.titleOfSelectedItem()
    logger.info("Picker '%s': selected '%s'", title, selected)
    return selected
