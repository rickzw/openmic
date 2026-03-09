"""Always-visible floating overlay pill at bottom-center of screen.

Shows the current app state so the user always knows what OpenMic is doing:
  idle        — thin collapsed capsule with subtle border
  recording   — expanded pill with red dot + "Recording..." label
  processing  — expanded pill with amber dot + "Polishing..." label

Transitions between idle and active states are smoothly animated.
"""

import logging

import objc
from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSColor,
    NSEvent,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSWindow,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSPopUpMenuWindowLevel,
    NSAttributedString,
    NSBezierPath,
    NSApplication,
    NSScreen,
)
from Foundation import NSObject, NSThread, NSRunLoop, NSDate, NSDefaultRunLoopMode

logger = logging.getLogger(__name__)

# Overlay dimensions
OVERLAY_WIDTH = 160          # active states (recording/processing)
OVERLAY_HEIGHT = 36
OVERLAY_IDLE_WIDTH = 60      # idle state (thin capsule)
OVERLAY_IDLE_HEIGHT = 10
OVERLAY_BOTTOM_MARGIN = 40   # pixels above bottom of visible screen
CORNER_RADIUS = 10.0
ANIMATION_DURATION = 0.25    # seconds for expand/collapse


# ---------------------------------------------------------------------------
# Module-level ObjC classes — defined ONCE so the runtime never sees
# duplicate class registrations across repeated show/hide calls.
# ---------------------------------------------------------------------------

class _MainThreadDispatcher(NSObject):
    """Marshals arbitrary callables onto the main Cocoa thread."""

    def callWithBlock_(self, block):
        try:
            block()
        except Exception:
            logger.exception("Overlay main-thread call failed")


# Single shared instance
_dispatcher = _MainThreadDispatcher.alloc().init()


def _run_on_main_thread(fn):
    """Call fn() on the main thread. Safe to call from any thread.

    If already on the main thread, calls fn() directly (avoids deadlock).
    If on a background thread, dispatches synchronously to the main thread.
    """
    if NSThread.isMainThread():
        fn()
    else:
        _dispatcher.performSelectorOnMainThread_withObject_waitUntilDone_(
            "callWithBlock:", fn, True
        )


class _OverlayView(NSView):
    """Draws the rounded pill background, status dot, and label."""

    def initWithFrame_(self, frame):
        self = objc.super(_OverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._dot_color = None
        self._label_text = ""
        self._state = "idle"
        self._drag_start = None        # NSPoint in window coords at mouseDown
        self._position_callback = None # callable(cx, bottom_y) — set by RecordingOverlay
        return self

    def acceptsFirstMouse_(self, event):
        return True  # receive mouseDown without requiring the window to be key

    def mouseDown_(self, event):
        self._drag_start = event.locationInWindow()

    def mouseDragged_(self, event):
        if self._drag_start is None:
            return
        screen_loc = NSEvent.mouseLocation()   # screen coordinates
        new_x = screen_loc.x - self._drag_start.x
        new_y = screen_loc.y - self._drag_start.y
        self.window().setFrameOrigin_((new_x, new_y))

    def mouseUp_(self, event):
        if self._drag_start is not None and self._position_callback is not None:
            frame = self.window().frame()
            cx = frame.origin.x + frame.size.width / 2
            bottom_y = frame.origin.y
            self._position_callback(cx, bottom_y)
        self._drag_start = None

    # macOS NSView uses flipped coordinates (origin top-left) when this is True,
    # which makes positioning text and shapes much more intuitive.
    def isFlipped(self):
        return True

    def set_state(self, state: str):
        self._state = state
        if state == "idle":
            self._dot_color = None
            self._label_text = ""
        elif state == "recording":
            self._dot_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.95, 0.27, 0.27, 1.0   # red
            )
            self._label_text = "Recording..."
        elif state == "processing":
            self._dot_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.98, 0.78, 0.20, 1.0   # amber
            )
            self._label_text = "Polishing..."
        elif state == "done":
            self._dot_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.30, 0.85, 0.40, 1.0   # green
            )
            self._label_text = "Done"
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        bounds = self.bounds()
        # Adapt corner radius: fully rounded for thin capsule, standard for expanded
        radius = min(CORNER_RADIUS, bounds.size.height / 2)

        # --- Pill background ---
        bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.10, 0.12, 0.92)
        bg.set()
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, radius, radius
        )
        pill.fill()

        if self._state == "idle":
            # --- Idle: thin capsule with subtle border ---
            border = NSColor.colorWithCalibratedWhite_alpha_(0.35, 0.8)
            border.set()
            inset = NSMakeRect(
                0.5, 0.5, bounds.size.width - 1, bounds.size.height - 1
            )
            border_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                inset, radius, radius
            )
            border_path.setLineWidth_(1.0)
            border_path.stroke()
        else:
            # --- Recording/Processing/Done: colored dot + label ---
            dot_size = 10
            dot_x = 12
            dot_y = (bounds.size.height - dot_size) / 2
            dot_rect = NSMakeRect(dot_x, dot_y, dot_size, dot_size)

            if self._state == "done":
                # Green circle background with a white checkmark
                self._dot_color.set()
                dot_path = NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
                dot_path.fill()
                # Draw checkmark
                check = NSBezierPath.bezierPath()
                cx, cy = dot_x + dot_size / 2, dot_y + dot_size / 2
                check.moveToPoint_((cx - 3, cy))
                check.lineToPoint_((cx - 0.5, cy + 3))
                check.lineToPoint_((cx + 3.5, cy - 2.5))
                NSColor.whiteColor().set()
                check.setLineWidth_(1.5)
                check.stroke()
            else:
                dot_path = NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
                self._dot_color.set()
                dot_path.fill()

            attrs = {
                NSFontAttributeName: NSFont.systemFontOfSize_(12.0),
                NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(
                    0.95, 1.0
                ),
            }
            astr = NSAttributedString.alloc().initWithString_attributes_(
                self._label_text, attrs
            )
            text_x = dot_x + dot_size + 8
            text_y = (bounds.size.height - 16) / 2
            astr.drawAtPoint_((text_x, text_y))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class RecordingOverlay:
    """Controls the floating overlay panel lifecycle.

    Always visible at bottom-center of screen. Shows a thin capsule when idle,
    smoothly expands for recording/processing states.

    All public methods are thread-safe — they marshal to the main thread.
    """

    def __init__(self, config=None):
        self._panel = None
        self._view = None
        self._current_state = None
        self._config = config

    # --- Helpers ---

    def _compute_frame_for_state(self, state):
        """Return (x, y, w, h) for bottom-center positioning based on state."""
        if state == "idle":
            w, h = OVERLAY_IDLE_WIDTH, OVERLAY_IDLE_HEIGHT
        elif state == "done":
            w, h = 120, OVERLAY_HEIGHT  # slightly narrower for short "Done" label
        else:
            w, h = OVERLAY_WIDTH, OVERLAY_HEIGHT

        # Use saved anchor if available, otherwise default to bottom-center
        cx = self._config.get("overlay_anchor_x") if self._config else None
        bottom_y = self._config.get("overlay_anchor_y") if self._config else None

        if cx is None or bottom_y is None:
            screen = NSScreen.mainScreen()
            if screen:
                visible = screen.visibleFrame()
                screen_x = visible.origin.x
                screen_y = visible.origin.y
                screen_w = visible.size.width
            else:
                screen_x, screen_y, screen_w = 0, 0, 1440
            cx = screen_x + screen_w / 2
            bottom_y = screen_y + OVERLAY_BOTTOM_MARGIN

        x = cx - w / 2
        y = bottom_y
        return x, y, w, h

    def _save_position(self, cx: float, bottom_y: float):
        if self._config is not None:
            self._config.set("overlay_anchor_x", cx)
            self._config.set("overlay_anchor_y", bottom_y)
            logger.info("Overlay position saved: cx=%.1f bottom_y=%.1f", cx, bottom_y)

    # --- Main-thread workers (must only be called from the main thread) ---

    def _create_panel_if_needed(self):
        if self._panel is not None:
            return
        try:
            x, y, w, h = self._compute_frame_for_state("idle")
            frame = NSMakeRect(x, y, w, h)

            # Use NSWindow (not NSPanel) — NSPanel has rendering quirks in
            # LSUIElement/rumps apps; NSWindow renders reliably.
            panel = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                NSBorderlessWindowMask,
                NSBackingStoreBuffered,
                False,
            )

            # NSPopUpMenuWindowLevel (101) floats above all normal windows,
            # the menu bar (25), and Dock — guaranteed to be visible.
            panel.setLevel_(NSPopUpMenuWindowLevel)
            panel.setAlphaValue_(1.0)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setIgnoresMouseEvents_(False)
            panel.setHasShadow_(False)
            panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)

            view = _OverlayView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            # Auto-resize with window during animations
            view.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable
            panel.setContentView_(view)
            view._position_callback = self._save_position

            self._panel = panel
            self._view = view
            logger.info("Overlay panel created OK")
        except Exception:
            logger.exception("Failed to create overlay panel")

    def _set_state_main(self, state):
        """Unified state transition — creates panel if needed, resizes, updates view."""
        self._create_panel_if_needed()
        if self._panel is None:
            logger.error("Overlay panel is None, cannot show")
            return
        try:
            x, y, w, h = self._compute_frame_for_state(state)
            target_frame = NSMakeRect(x, y, w, h)

            # Update view content
            self._view.set_state(state)

            # Animate if transitioning between different states
            should_animate = (
                self._current_state is not None and self._current_state != state
            )
            self._current_state = state

            if should_animate:
                NSAnimationContext.beginGrouping()
                NSAnimationContext.currentContext().setDuration_(ANIMATION_DURATION)
                self._panel.animator().setFrame_display_(target_frame, True)
                NSAnimationContext.endGrouping()
            else:
                self._panel.setFrame_display_(target_frame, True)
                self._panel.display()

            self._panel.orderFrontRegardless()
            # Flush the run loop so the window compositing actually happens
            # before we return to the caller (critical for LSUIElement apps)
            NSRunLoop.mainRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.01)
            )
        except Exception:
            logger.exception("Failed to set overlay state to %s", state)

    def _hide_main(self):
        if self._panel is None:
            return
        try:
            self._panel.orderOut_(None)
            logger.info("Overlay hidden")
        except Exception:
            logger.exception("Failed to hide overlay")

    # --- Public thread-safe API ---

    def show_idle(self):
        _run_on_main_thread(lambda: self._set_state_main("idle"))

    def show_recording(self):
        _run_on_main_thread(lambda: self._set_state_main("recording"))

    def show_processing(self):
        _run_on_main_thread(lambda: self._set_state_main("processing"))

    def show_done(self):
        """Show green 'Done' pill for 0.5s, then auto-collapse to idle."""
        def _show():
            self._set_state_main("done")
            # Use delayed dispatch via the dispatcher to transition to idle
            _dispatcher.performSelector_withObject_afterDelay_(
                "callWithBlock:", lambda: self._set_state_main("idle"), 0.5
            )
        _run_on_main_thread(_show)

    def hide(self):
        _run_on_main_thread(self._hide_main)
