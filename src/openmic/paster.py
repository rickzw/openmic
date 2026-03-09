"""Clipboard management and simulated Cmd+V paste.

Saves the current clipboard, writes polished text, simulates Cmd+V,
then restores the previous clipboard contents.
"""

import logging
import time

from openmic.constants import CLIPBOARD_SETTLE_DELAY, PASTE_RESTORE_DELAY, VK_ANSI_V

logger = logging.getLogger(__name__)


class Paster:
    """Pastes text into the focused application via clipboard + Cmd+V."""

    def paste(self, text: str):
        """Write text to clipboard, simulate Cmd+V, restore previous clipboard.

        Args:
            text: The polished text to paste.
        """
        from AppKit import NSPasteboard, NSPasteboardTypeString
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            CGEventSetFlags,
            CGEventSourceCreate,
            kCGEventFlagMaskCommand,
            kCGSessionEventTap,
            kCGEventSourceStateCombinedSessionState,
        )

        pasteboard = NSPasteboard.generalPasteboard()

        # Save current clipboard
        old_contents = pasteboard.stringForType_(NSPasteboardTypeString)
        old_change_count = pasteboard.changeCount()

        # Set new clipboard content
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)

        # Let clipboard settle
        time.sleep(CLIPBOARD_SETTLE_DELAY)

        # Simulate Cmd+V
        source = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)
        key_down = CGEventCreateKeyboardEvent(source, VK_ANSI_V, True)
        key_up = CGEventCreateKeyboardEvent(source, VK_ANSI_V, False)
        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGSessionEventTap, key_down)
        CGEventPost(kCGSessionEventTap, key_up)

        logger.info("Simulated Cmd+V paste (%d chars)", len(text))

        # Wait for paste to complete, then restore clipboard
        time.sleep(PASTE_RESTORE_DELAY)

        # Only restore if the clipboard wasn't changed by something else
        if pasteboard.changeCount() == old_change_count + 1:
            pasteboard.clearContents()
            if old_contents is not None:
                pasteboard.setString_forType_(old_contents, NSPasteboardTypeString)
            logger.debug("Clipboard restored")
        else:
            logger.debug("Clipboard was modified externally, not restoring")
