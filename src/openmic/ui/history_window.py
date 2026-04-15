"""History window — shows persistent dictation history in a native table view.

Menu bar → History… opens this window. Users can copy, paste, delete individual
entries, or clear all history. The window is kept as a persistent singleton and
re-raised on each open.
"""

import logging

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSTitledWindowMask,
    NSClosableWindowMask,
    NSResizableWindowMask,
    NSMiniaturizableWindowMask,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
)
from Foundation import NSObject

logger = logging.getLogger(__name__)

# Single persistent window instance
_window_controller = None


def show_history(history):
    """Open (or raise) the history window.

    Args:
        history: openmic.history.History instance
    """
    global _window_controller
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    if _window_controller is None:
        _window_controller = _HistoryWindowController.alloc().initWithHistory_(history)
    _window_controller.refresh()
    _window_controller.window().makeKeyAndOrderFront_(None)


class _HistoryWindowController(NSObject):
    """Manages the history NSWindow and its table data source."""

    def initWithHistory_(self, history):
        self = objc.super(_HistoryWindowController, self).init()
        if self is None:
            return None
        self._history = history
        self._entries = []  # list of {"ts": ..., "text": ...}
        self._window = None
        self._table = None
        self._build_window()
        return self

    def window(self):
        return self._window

    def refresh(self):
        self._entries = self._history.load(limit=200)
        if self._table is not None:
            self._table.reloadData()

    # --- NSTableViewDataSource ---

    def numberOfRowsInTableView_(self, table_view):
        return len(self._entries)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < 0 or row >= len(self._entries):
            return ""
        entry = self._entries[row]
        identifier = column.identifier()
        if identifier == "ts":
            # Trim ISO timestamp to local-friendly display
            ts = entry.get("ts", "")
            # "2026-04-15T10:23:45.123456+00:00" → "2026-04-15 10:23"
            try:
                ts = ts[:16].replace("T", " ")
            except Exception:
                pass
            return ts
        else:
            return entry.get("text", "")

    # --- Button actions ---

    def onCopy_(self, sender):
        row = self._table.selectedRow()
        if row < 0 or row >= len(self._entries):
            return
        text = self._entries[row].get("text", "")
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSStringPboardType)
        logger.info("History: copied entry at row %d", row)

    def onPaste_(self, sender):
        row = self._table.selectedRow()
        if row < 0 or row >= len(self._entries):
            return
        text = self._entries[row].get("text", "")
        try:
            from openmic.paster import Paster
            Paster().paste(text)
            logger.info("History: pasted entry at row %d", row)
        except Exception:
            logger.exception("History: paste failed")

    def onDelete_(self, sender):
        row = self._table.selectedRow()
        if row < 0 or row >= len(self._entries):
            return
        ts = self._entries[row].get("ts", "")
        self._history.delete(ts)
        self.refresh()

    def onClearAll_(self, sender):
        from openmic.ui.native_dialogs import show_alert
        btn = show_alert(
            title="Clear All History",
            message="Delete all dictation history? This cannot be undone.",
            buttons=["Delete All", "Cancel"],
        )
        if btn == 0:
            self._history.clear()
            self.refresh()

    # --- Window construction ---

    def _build_window(self):
        style_mask = (
            NSTitledWindowMask
            | NSClosableWindowMask
            | NSResizableWindowMask
            | NSMiniaturizableWindowMask
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 200, 680, 480),
            style_mask,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("Dictation History")
        win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        win.setReleasedWhenClosed_(False)

        content = win.contentView()

        # --- Table ---
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 50, 680, 430))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutoresizingMask_(18 | 4 | 2)  # width+height sizable, top+bottom margin

        table = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, 680, 430))
        table.setUsesAlternatingRowBackgroundColors_(True)
        table.setRowHeight_(20.0)
        table.setAutoresizingMask_(18)

        ts_col = NSTableColumn.alloc().initWithIdentifier_("ts")
        ts_col.setTitle_("Time")
        ts_col.setWidth_(130)
        ts_col.setMinWidth_(100)
        table.addTableColumn_(ts_col)

        text_col = NSTableColumn.alloc().initWithIdentifier_("text")
        text_col.setTitle_("Dictation")
        text_col.setWidth_(530)
        text_col.setMinWidth_(200)
        table.addTableColumn_(text_col)

        table.setDataSource_(self)
        scroll.setDocumentView_(table)
        content.addSubview_(scroll)
        self._table = table

        # --- Buttons ---
        button_y = 10
        button_h = 28
        bx = 10
        for title, selector in [
            ("Copy", "onCopy:"),
            ("Paste", "onPaste:"),
            ("Delete", "onDelete:"),
        ]:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(bx, button_y, 80, button_h))
            btn.setTitle_(title)
            btn.setBezelStyle_(1)  # NSRoundedBezelStyle
            btn.setTarget_(self)
            btn.setAction_(selector)
            content.addSubview_(btn)
            bx += 90

        # Clear All — right-aligned
        clear_btn = NSButton.alloc().initWithFrame_(NSMakeRect(580, button_y, 90, button_h))
        clear_btn.setTitle_("Clear All")
        clear_btn.setBezelStyle_(1)
        clear_btn.setTarget_(self)
        clear_btn.setAction_("onClearAll:")
        clear_btn.setAutoresizingMask_(1)  # right margin flexible
        content.addSubview_(clear_btn)

        self._window = win
        logger.info("History window built")
