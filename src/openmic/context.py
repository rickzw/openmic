"""Capture application context from the frontmost window.

Uses NSWorkspace for app identity and AXUIElement for window title and
focused field text. Must be called from the main thread (NSWorkspace).

No additional permissions required — Accessibility is already granted.
"""
import logging
from typing import Optional

from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
)

logger = logging.getLogger(__name__)

# AX attribute name constants (string literals avoid import issues across OS versions)
_AX_FOCUSED        = "AXFocusedUIElement"
_AX_FOCUSED_WINDOW = "AXFocusedWindow"
_AX_VALUE          = "AXValue"
_AX_WINDOWS        = "AXWindows"
_AX_TITLE          = "AXTitle"

FOCUSED_TEXT_MAX_CHARS = 500  # truncate to last N chars of focused field


def get_app_context() -> dict:
    """Return context dict: app_name, window_title, focused_text (any may be None).

    Call on the main thread. Silently returns {} on any error.
    """
    try:
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication()
        if not app:
            return {}

        app_name = app.localizedName()
        pid      = int(app.processIdentifier())
        app_el   = AXUIElementCreateApplication(pid)

        window_title = _get_window_title(app_el)
        focused_text = _get_focused_text(app_el)

        ctx = {"app_name": app_name}
        if window_title:
            ctx["window_title"] = window_title
        if focused_text:
            ctx["focused_text"] = focused_text

        logger.info("App context: app=%r window=%r text_len=%d",
                    app_name, window_title, len(focused_text or ""))
        return ctx
    except Exception:
        logger.debug("Could not capture app context", exc_info=True)
        return {}


def _get_window_title(app_el) -> Optional[str]:
    try:
        err, windows = AXUIElementCopyAttributeValue(app_el, _AX_WINDOWS, None)
        if err or not windows:
            return None
        err, title = AXUIElementCopyAttributeValue(windows[0], _AX_TITLE, None)
        return str(title) if not err and title else None
    except Exception:
        return None


def _get_focused_text(app_el) -> Optional[str]:
    try:
        # Strategy 1: app-level (native AppKit apps)
        err, focused = AXUIElementCopyAttributeValue(app_el, _AX_FOCUSED, None)

        # Strategy 2: window-level (some apps)
        if err or focused is None:
            _, win = AXUIElementCopyAttributeValue(app_el, _AX_FOCUSED_WINDOW, None)
            if win is not None:
                err, focused = AXUIElementCopyAttributeValue(win, _AX_FOCUSED, None)

        # Strategy 3: system-wide element (last resort)
        if err or focused is None:
            sys_el = AXUIElementCreateSystemWide()
            err, focused = AXUIElementCopyAttributeValue(sys_el, _AX_FOCUSED, None)

        if err or focused is None:
            return None

        err, value = AXUIElementCopyAttributeValue(focused, _AX_VALUE, None)
        if err or not value:
            return None
        text = str(value)
        # Return only the tail so the prompt stays concise
        return text[-FOCUSED_TEXT_MAX_CHARS:] if len(text) > FOCUSED_TEXT_MAX_CHARS else text
    except Exception:
        logger.debug("_get_focused_text exception", exc_info=True)
        return None
