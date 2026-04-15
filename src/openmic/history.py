"""Persistent dictation history stored as JSONL.

Entries are appended to ~/Library/Application Support/OpenMic/history.jsonl.
The file is capped at MAX_ENTRIES (200) lines; older entries are dropped.
All public methods are thread-safe.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MAX_ENTRIES = 200
_HISTORY_DIR = os.path.expanduser("~/Library/Application Support/OpenMic")
_HISTORY_FILE = os.path.join(_HISTORY_DIR, "history.jsonl")


class History:
    """Manages persistent dictation history as a JSONL file."""

    def __init__(self):
        self._lock = threading.Lock()
        os.makedirs(_HISTORY_DIR, exist_ok=True)

    def append(self, text: str):
        """Add a polished dictation entry to history.

        Trims the file to MAX_ENTRIES after appending.
        """
        if not text or not text.strip():
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "text": text.strip(),
        }
        with self._lock:
            try:
                # Read existing lines
                lines = self._read_lines()
                # Append new entry and cap
                lines.append(json.dumps(entry, ensure_ascii=False))
                if len(lines) > MAX_ENTRIES:
                    lines = lines[-MAX_ENTRIES:]
                self._write_lines(lines)
                logger.debug("History: appended entry (total=%d)", len(lines))
            except Exception:
                logger.exception("History: failed to append entry")

    def load(self, limit: int = 50) -> list:
        """Return the most recent entries, newest first.

        Each entry is a dict with 'ts' (ISO timestamp) and 'text' keys.
        """
        with self._lock:
            try:
                lines = self._read_lines()
            except Exception:
                logger.exception("History: failed to load entries")
                return []

        entries = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("History: skipping malformed line")
            if len(entries) >= limit:
                break
        return entries

    def delete(self, ts: str):
        """Remove the entry with the given ISO timestamp string."""
        with self._lock:
            try:
                lines = self._read_lines()
                new_lines = []
                for line in lines:
                    try:
                        entry = json.loads(line)
                        if entry.get("ts") == ts:
                            continue
                    except json.JSONDecodeError:
                        pass
                    new_lines.append(line)
                self._write_lines(new_lines)
                logger.debug("History: deleted entry ts=%s", ts)
            except Exception:
                logger.exception("History: failed to delete entry ts=%s", ts)

    def clear(self):
        """Delete all history entries."""
        with self._lock:
            try:
                self._write_lines([])
                logger.info("History: cleared all entries")
            except Exception:
                logger.exception("History: failed to clear")

    # --- Internal helpers (called under self._lock) ---

    def _read_lines(self) -> list:
        if not os.path.exists(_HISTORY_FILE):
            return []
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            return [line for line in f.read().splitlines() if line.strip()]

    def _write_lines(self, lines: list):
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
