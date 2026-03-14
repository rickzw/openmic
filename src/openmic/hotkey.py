"""Global hotkey registration using PyObjC CGEvent tap.

Registers a system-wide hotkey (default: Fn) that works
from any application. Requires Accessibility permissions.

Supports two activation modes:
- "hold": hold the hotkey to record, release to stop (default)
- "toggle": press once to start, press again to stop
"""

import logging
from typing import Callable, Optional

from Quartz import (
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    CFMachPortCreateRunLoopSource,
    CFRunLoopGetCurrent,
    CFRunLoopAddSource,
    kCFRunLoopCommonModes,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventFlagMaskAlternate,
)

from openmic.constants import VK_FN, VK_SPACE

# Fn key flag bit in CGEventFlags (kCGEventFlagMaskSecondaryFn)
FN_FLAG = 0x800000

logger = logging.getLogger(__name__)

# Pure-modifier virtual key codes — ignored as the "main" key during capture
# (Command, RightCommand, Shift, RightShift, CapsLock, Option, RightOption,
#  Control, RightControl, Function)
_MODIFIER_KEYCODES = frozenset({54, 55, 56, 57, 58, 59, 60, 61, 62, 63})

# Legacy default modifier mask (kept for reference / migration)
CMD_SHIFT_MASK = kCGEventFlagMaskCommand | kCGEventFlagMaskShift

# Default modifier mask: Ctrl+Shift
CTRL_SHIFT_MASK = kCGEventFlagMaskControl | kCGEventFlagMaskShift

# Mask of all modifier bits we care about (ignore caps lock, fn, etc.)
MODIFIER_CHECK_MASK = (
    kCGEventFlagMaskCommand
    | kCGEventFlagMaskShift
    | kCGEventFlagMaskControl
    | kCGEventFlagMaskAlternate
)


class HotkeyManager:
    """Manages a global hotkey using a CGEvent tap on the current run loop.

    Must be created on the main thread (the thread running the Cocoa event loop)
    so that the event tap fires correctly.

    Supports two callbacks:
      on_press   — called when the hotkey is pressed down
      on_release — called when the hotkey is released (hold mode only)

    For toggle mode, only on_press is used (acts as toggle).
    For hold mode, on_press starts recording and on_release stops it.
    """

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Optional[Callable[[], None]] = None,
        hotkey_vk: int = VK_SPACE,
        hotkey_mods: int = CTRL_SHIFT_MASK,
    ):
        self.on_press = on_press
        self.on_release = on_release
        self.hotkey_vk = hotkey_vk
        self.hotkey_mods = hotkey_mods
        self._tap = None  # type: Optional[object]
        self._key_is_held = False  # track hold state to avoid repeat events
        self.paused = False  # when True, all events pass through (used by hotkey capture UI)
        self.capture_callback = None  # type: Optional[Callable]
        # When set, the tap is in capture mode: the first qualifying keydown
        # (non-modifier + at least one modifier) calls capture_callback(vk, mods)
        # and suppresses the event.  Set to None after firing (one-shot).

    def start(self) -> bool:
        """Register the event tap on the current run loop."""
        # Listen for key-down, key-up, and flags-changed (needed for Fn key)
        event_mask = (
            CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
            | CGEventMaskBit(kCGEventFlagsChanged)
        )

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            0,  # activeFilter (0 = active tap, can suppress events)
            event_mask,
            self._callback,
            None,  # userInfo
        )

        if self._tap is None:
            logger.error(
                "Failed to create CGEvent tap. "
                "Grant Accessibility permissions in System Settings > "
                "Privacy & Security > Accessibility."
            )
            return False

        run_loop_source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), run_loop_source, kCFRunLoopCommonModes)
        logger.info("Global hotkey registered (%s)", self._describe())
        return True

    def stop(self):
        """Unregister the event tap (best-effort)."""
        self._tap = None
        self._key_is_held = False

    def update(
        self,
        hotkey_vk: int,
        hotkey_mods: int,
        description: str = "",
    ):
        """Update the hotkey combo without restarting the tap.

        The tap stays registered; we just change which key combo we match.
        """
        self.hotkey_vk = hotkey_vk
        self.hotkey_mods = hotkey_mods
        self._key_is_held = False
        logger.info("Hotkey updated to %s", description or self._describe())

    def _describe(self) -> str:
        if self.hotkey_vk == VK_FN:
            return "Fn"
        parts = []
        if self.hotkey_mods & kCGEventFlagMaskCommand:
            parts.append("Cmd")
        if self.hotkey_mods & kCGEventFlagMaskShift:
            parts.append("Shift")
        if self.hotkey_mods & kCGEventFlagMaskControl:
            parts.append("Ctrl")
        if self.hotkey_mods & kCGEventFlagMaskAlternate:
            parts.append("Option")
        parts.append("Space" if self.hotkey_vk == VK_SPACE else "key(%d)" % self.hotkey_vk)
        return "+".join(parts)

    def _callback(self, proxy, event_type, event, refcon):
        """CGEvent tap callback — fires on every key-down and key-up system-wide."""
        # macOS auto-disables taps that don't service events fast enough (e.g.
        # during blocking NSAlert.runModal() calls).  Re-enable immediately.
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            logger.warning(
                "CGEvent tap disabled (event_type=0x%x) — re-enabling", event_type
            )
            if self._tap is not None:
                CGEventTapEnable(self._tap, True)
            return event

        # --- Fn key (FlagsChanged path) ---
        # Fn generates kCGEventFlagsChanged, not keydown/keyup.
        # Detect press (FN_FLAG goes 0→1) and release (FN_FLAG goes 1→0).
        if event_type == kCGEventFlagsChanged and self.hotkey_vk == VK_FN:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if keycode == VK_FN and not self.paused:
                flags = CGEventGetFlags(event)
                fn_active = bool(flags & FN_FLAG)
                if fn_active and not self._key_is_held:
                    self._key_is_held = True
                    logger.debug("Fn pressed")
                    try:
                        self.on_press()
                    except Exception:
                        logger.exception("Error in hotkey on_press callback")
                    return None  # suppress
                elif not fn_active and self._key_is_held:
                    self._key_is_held = False
                    logger.debug("Fn released")
                    if self.on_release:
                        try:
                            self.on_release()
                        except Exception:
                            logger.exception("Error in hotkey on_release callback")
                    return None  # suppress
            return event  # pass through other FlagsChanged events

        # Non-Fn FlagsChanged events pass through
        if event_type == kCGEventFlagsChanged:
            return event

        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        flags = CGEventGetFlags(event)
        masked_flags = flags & MODIFIER_CHECK_MASK
        mods_match = masked_flags == self.hotkey_mods

        # Capture mode: intercept the first qualifying keydown (non-modifier key +
        # at least one modifier), fire the one-shot callback, and suppress the event
        # so it never reaches other apps (e.g. Terminal).  This runs BEFORE the
        # paused check so that capture works even when paused is False.
        if self.capture_callback is not None and event_type == kCGEventKeyDown:
            if keycode not in _MODIFIER_KEYCODES and masked_flags != 0:
                cb = self.capture_callback
                self.capture_callback = None  # one-shot: consume immediately
                try:
                    cb(keycode, masked_flags)
                except Exception:
                    logger.exception("Error in capture_callback")
                return None  # suppress — don't let it reach Terminal or other apps

        # When paused (e.g. during hotkey capture UI), pass everything through
        if self.paused:
            return event

        if event_type == kCGEventKeyDown and keycode == self.hotkey_vk and mods_match:
            if not self._key_is_held:
                # First key-down (not a repeat from holding the key down)
                self._key_is_held = True
                logger.debug("Hotkey pressed")
                try:
                    self.on_press()
                except Exception:
                    logger.exception("Error in hotkey on_press callback")
            return None  # Suppress the event

        if event_type == kCGEventKeyUp and keycode == self.hotkey_vk:
            if self._key_is_held:
                self._key_is_held = False
                logger.debug("Hotkey released")
                if self.on_release:
                    try:
                        self.on_release()
                    except Exception:
                        logger.exception("Error in hotkey on_release callback")
            return None  # Suppress the event

        return event  # Pass through all other key events
