"""Always-visible floating overlay pill at bottom-center of screen.

Shows the current app state so the user always knows what OpenMic is doing:
  idle        — thin collapsed capsule with subtle border
  recording   — expanded pill with red dot + "Recording..." label
  processing  — expanded pill with amber dot + "Polishing..." label

Transitions between idle and active states are smoothly animated.
"""

import logging
import math

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
from Foundation import NSObject, NSThread, NSRunLoop, NSDate, NSDefaultRunLoopMode, NSTimer

logger = logging.getLogger(__name__)

# Overlay dimensions
OVERLAY_WIDTH = 160          # active states (recording/processing)
OVERLAY_HEIGHT = 36
OVERLAY_IDLE_WIDTH = 60      # idle state (thin capsule)
OVERLAY_IDLE_HEIGHT = 10
OVERLAY_BOTTOM_MARGIN = 40   # pixels above bottom of visible screen
CORNER_RADIUS = 10.0
ANIMATION_DURATION = 0.25    # seconds for expand/collapse

# Pulse animation (processing state)
PULSE_PERIOD = 0.9           # seconds per full pulse cycle
PULSE_MIN_ALPHA = 0.35       # minimum alpha at the bottom of the sine wave
PULSE_FPS = 30               # timer fires per second

# Audio level meter (recording state)
LEVEL_POLL_INTERVAL = 0.05   # seconds between level reads
LEVEL_BAR_COUNT = 4
LEVEL_THRESHOLDS = [0.05, 0.15, 0.35, 0.60]  # RMS thresholds per bar
LEVEL_BAR_ALPHA_DIM = 0.35


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


class _TimerCallback(NSObject):
    """Wraps a Python callable so NSTimer can fire it via a selector."""

    def initWithCallback_(self, callback):
        self = objc.super(_TimerCallback, self).init()
        if self is None:
            return None
        self._callback = callback
        return self

    def fire_(self, timer):
        try:
            self._callback()
        except Exception:
            logger.exception("Timer callback failed")


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
        self._pulse_alpha = 1.0        # current alpha for processing dot pulse
        self._audio_level = 0.0        # current RMS level for recording meter
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

    def set_pulse_alpha(self, alpha: float):
        """Update the pulse alpha for the processing dot. Must be called on main thread."""
        self._pulse_alpha = alpha
        self.setNeedsDisplay_(True)

    def set_audio_level(self, level: float):
        """Update the audio level for the recording meter. Must be called on main thread."""
        self._audio_level = level
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
                if self._state == "processing":
                    # Apply pulse alpha to the dot color
                    dot_color = self._dot_color.colorWithAlphaComponent_(self._pulse_alpha)
                else:
                    dot_color = self._dot_color
                dot_color.set()
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

            # --- Audio level bars (recording state only) ---
            if self._state == "recording":
                bar_w = 4
                bar_gap = 3
                bar_max_h = bounds.size.height - 10
                total_bars_w = LEVEL_BAR_COUNT * bar_w + (LEVEL_BAR_COUNT - 1) * bar_gap
                bars_x = bounds.size.width - total_bars_w - 10
                # Heights increase left-to-right for a rising-bar effect
                bar_heights = [
                    bar_max_h * 0.35,
                    bar_max_h * 0.55,
                    bar_max_h * 0.75,
                    bar_max_h * 1.0,
                ]
                for i in range(LEVEL_BAR_COUNT):
                    bh = bar_heights[i]
                    bx = bars_x + i * (bar_w + bar_gap)
                    by = (bounds.size.height - bh) / 2
                    bar_rect = NSMakeRect(bx, by, bar_w, bh)
                    active = self._audio_level >= LEVEL_THRESHOLDS[i]
                    if active:
                        NSColor.colorWithCalibratedRed_green_blue_alpha_(
                            0.949, 0.271, 0.271, 1.0
                        ).set()
                    else:
                        NSColor.colorWithCalibratedWhite_alpha_(1.0, LEVEL_BAR_ALPHA_DIM).set()
                    bar_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                        bar_rect, 2.0, 2.0
                    )
                    bar_path.fill()


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
        self._pulse_timer = None
        self._pulse_timer_cb = None
        self._level_timer = None
        self._level_timer_cb = None
        self._level_source = None  # callable() → float
        self._pulse_phase = 0.0

    def set_level_source(self, source):
        """Register a callable that returns the current audio level (0.0–1.0).

        Pass None to unregister. Thread-safe; can be called from any thread.
        """
        self._level_source = source

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

    # --- Pulse and level timer helpers (must only be called from the main thread) ---

    def _start_pulse_timer(self):
        self._stop_pulse_timer()
        self._pulse_phase = 0.0
        cb = _TimerCallback.alloc().initWithCallback_(self._on_pulse_tick)
        self._pulse_timer_cb = cb  # keep strong reference
        self._pulse_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / PULSE_FPS, cb, "fire:", None, True
        )

    def _stop_pulse_timer(self):
        if self._pulse_timer is not None:
            self._pulse_timer.invalidate()
            self._pulse_timer = None
        self._pulse_timer_cb = None
        if self._view is not None:
            self._view.set_pulse_alpha(1.0)

    def _start_level_timer(self):
        self._stop_level_timer()
        cb = _TimerCallback.alloc().initWithCallback_(self._on_level_tick)
        self._level_timer_cb = cb  # keep strong reference
        self._level_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            LEVEL_POLL_INTERVAL, cb, "fire:", None, True
        )

    def _stop_level_timer(self):
        if self._level_timer is not None:
            self._level_timer.invalidate()
            self._level_timer = None
        self._level_timer_cb = None
        if self._view is not None:
            self._view.set_audio_level(0.0)

    def _on_pulse_tick(self):
        self._pulse_phase += (1.0 / PULSE_FPS) / PULSE_PERIOD * 2 * math.pi
        alpha = PULSE_MIN_ALPHA + (1.0 - PULSE_MIN_ALPHA) * (math.sin(self._pulse_phase) + 1) / 2
        if self._view is not None:
            self._view.set_pulse_alpha(alpha)

    def _on_level_tick(self):
        if self._level_source is not None and self._view is not None:
            try:
                level = self._level_source()
                self._view.set_audio_level(level)
            except Exception:
                logger.exception("Level source raised exception")

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

            # Start/stop timers based on new state
            if state == "recording":
                self._stop_pulse_timer()
                self._start_level_timer()
            elif state == "processing":
                self._stop_level_timer()
                self._start_pulse_timer()
            else:  # idle or done
                self._stop_pulse_timer()
                self._stop_level_timer()

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
