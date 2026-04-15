"""OpenMicApp — menu bar application and state machine."""

import logging
import queue
import threading

import rumps

from AppKit import NSSound

from openmic.config import Config
from openmic.constants import HOTKEY_MODE_HOLD, HOTKEY_MODE_TOGGLE
from openmic.context import get_app_context
from openmic.errors import InvalidAPIKeyError, NetworkError, OpenMicError
from openmic.history import History
from openmic.hotkey import HotkeyManager
from openmic.permissions import check_accessibility, prompt_accessibility, request_accessibility
from openmic.pipeline import CancelledError, Pipeline
from openmic.ui.overlay import RecordingOverlay, _run_on_main_thread

logger = logging.getLogger(__name__)


class OpenMicApp(rumps.App):
    """macOS menu bar app for voice-to-text with AI polish."""

    def __init__(self):
        super().__init__(
            name="OpenMic",
            title="\U0001f399",  # 🎙 menu bar title
            quit_button="Quit OpenMic",
        )
        self.config = Config()
        self.state = "idle"  # idle | recording | processing

        self._pipeline = Pipeline(self.config)
        self._history = History()
        self._hotkey_queue = queue.Queue()
        self._overlay = RecordingOverlay(config=self.config)

        # Build hotkey manager with both press and release callbacks
        vk = self.config.get("hotkey_vk")
        raw_mods = self.config.get("hotkey_modifiers")
        mods = raw_mods if raw_mods is not None else 0
        self._hotkey_manager = HotkeyManager(
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
            hotkey_vk=vk,
            hotkey_mods=mods,
        )

        self._build_menu()
        logger.info("OpenMicApp initialized")

    def _build_menu(self):
        self.status_item = rumps.MenuItem("Status: Ready")
        self.status_item.set_callback(None)

        self.menu = [
            self.status_item,
            None,  # separator
            rumps.MenuItem("History\u2026", callback=self._on_history),
            rumps.MenuItem("Settings...", callback=self._on_settings),
            rumps.MenuItem("Personal Dictionary...", callback=self._on_dictionary),
            None,  # separator
        ]

    @rumps.timer(1)
    def _setup(self, timer):
        """Run once shortly after the event loop starts."""
        timer.stop()

        if not self.config.get("first_run_complete"):
            from openmic.ui.onboarding import run_onboarding
            run_onboarding(self.config)

        if not check_accessibility():
            logger.warning("Accessibility permission not granted")
            # Register app in Accessibility list and trigger the system prompt
            request_accessibility()
            # Show blocking dialog (not a notification — can't be missed)
            from openmic.ui.native_dialogs import show_alert
            btn = show_alert(
                title="Accessibility Permission Required",
                message=(
                    "OpenMic needs Accessibility permission to detect the global hotkey.\n\n"
                    "1. Open System Settings → Privacy & Security → Accessibility\n"
                    "2. Enable the toggle next to 'OpenMic'\n"
                    "3. Quit and relaunch OpenMic\n\n"
                    "Click 'Open System Settings' then relaunch OpenMic after enabling access."
                ),
                buttons=["Open System Settings", "Quit OpenMic"],
            )
            if btn == 0:
                prompt_accessibility()
            rumps.quit_application()
            return

        success = self._hotkey_manager.start()
        if not success:
            from openmic.ui.native_dialogs import show_alert
            show_alert(
                title="Hotkey Registration Failed",
                message=(
                    "OpenMic could not register the global hotkey even though Accessibility "
                    "permission appears to be granted.\n\n"
                    "Try removing OpenMic from System Settings → Privacy & Security → "
                    "Accessibility, re-adding it, then relaunching."
                ),
                buttons=["Quit OpenMic"],
            )
            rumps.quit_application()
            return

        self._overlay.show_idle()

        # Pre-warm local whisper models in background
        threading.Thread(target=self._pipeline.warm_up, daemon=True).start()

    def _on_history(self, _):
        """Open history window."""
        from openmic.ui.history_window import show_history
        show_history(self._history)

    def _on_settings(self, _):
        """Open settings window."""
        from openmic.ui.settings_window import show_settings
        show_settings(self.config, self._hotkey_manager)

    def _on_dictionary(self, _):
        """Open personal dictionary editor."""
        from openmic.ui.settings_window import show_dictionary_editor
        show_dictionary_editor(self.config)

    # -- Hotkey handling --

    def _on_hotkey_press(self):
        """Called from CGEvent tap on system thread when hotkey is pressed down."""
        self._hotkey_queue.put("press")

    def _on_hotkey_release(self):
        """Called from CGEvent tap on system thread when hotkey is released."""
        self._hotkey_queue.put("release")

    @rumps.timer(0.05)
    def _process_hotkey_queue(self, timer):
        """Process queued hotkey events on the main thread (runs at 20Hz).

        In hold mode, press+release can arrive in the same 50ms batch before
        any state change has been applied. We drain the full queue first, then
        apply the net effect so a quick tap still records + processes correctly.
        """
        # Drain all pending messages in one go
        messages = []
        try:
            while True:
                messages.append(self._hotkey_queue.get_nowait())
        except queue.Empty:
            pass

        if not messages:
            return

        mode = self.config.get("hotkey_mode")

        if mode == HOTKEY_MODE_HOLD:
            # Count press and release events in this batch
            presses = messages.count("press")
            releases = messages.count("release")

            if presses > 0 and self.state == "idle":
                self._start_recording()
            elif presses > 0 and self.state == "processing":
                self._cancel_processing()

            if releases > 0 and self.state == "recording":
                self._stop_recording()

        else:
            # Toggle mode: each press toggles
            for msg in messages:
                if msg == "press":
                    if self.state == "idle":
                        self._start_recording()
                    elif self.state == "recording":
                        self._stop_recording()
                    elif self.state == "processing":
                        self._cancel_processing()

    def _play_sound(self, name: str):
        """Play a named macOS system sound if sound feedback is enabled."""
        if not self.config.get("sound_feedback_enabled", True):
            return
        sound = NSSound.soundNamed_(name)
        if sound:
            sound.play()

    def _start_recording(self):
        """Transition: IDLE → RECORDING."""
        self.state = "recording"
        self.title = "\U0001f534"  # 🔴
        self.status_item.title = "Status: Recording..."
        self._play_sound("Tink")
        self._pipeline.start_recording()
        self._overlay.set_level_source(self._pipeline.recorder.get_level)
        self._overlay.show_recording()
        logger.info("Recording started")

    def _stop_recording(self):
        """Transition: RECORDING → PROCESSING."""
        self.state = "processing"
        self.title = "\U0001f7e1"  # 🟡
        self.status_item.title = "Status: Processing..."
        self._play_sound("Glass")
        self._overlay.show_processing()
        logger.info("Recording stopped, processing...")

        app_context = get_app_context()  # capture here on main thread
        thread = threading.Thread(
            target=self._run_pipeline, args=(app_context,), daemon=True
        )
        thread.start()

    def _cancel_processing(self):
        """Cancel the running pipeline and return to idle."""
        logger.info("Cancelling processing...")
        self._pipeline.cancel()
        self._play_sound("Funk")

    def _run_pipeline(self, app_context: dict):
        """Run transcribe → polish → paste on a background thread."""
        success = False
        try:
            audio_data = self._pipeline.stop_recording_and_get_audio()
            transcript = self._pipeline.transcribe(audio_data)
            if not transcript:
                logger.info("No transcript (recording too short or empty)")
                return
            polished = self._pipeline.polish(transcript, app_context=app_context)
            self._pipeline.paste(polished)
            self._history.append(polished)
            success = True
            logger.info("Pipeline complete: pasted %d chars", len(polished))
        except CancelledError:
            logger.info("Pipeline cancelled by user")
        except OpenMicError as e:
            logger.error("Pipeline error: %s", e)
            err = e
            _run_on_main_thread(lambda: self._show_pipeline_error(err))
        except Exception:
            logger.exception("Pipeline error")
            rumps.notification("OpenMic", "Error", "Something went wrong. Check logs.")
        finally:
            self._reset_to_idle(show_done=success)

    def _show_pipeline_error(self, error: OpenMicError):
        """Show a context-specific error dialog for pipeline errors. Must run on main thread."""
        from openmic.ui.native_dialogs import show_alert
        if isinstance(error, InvalidAPIKeyError):
            btn = show_alert(
                title="Invalid API Key",
                message=str(error),
                buttons=["Open Settings", "Dismiss"],
            )
            if btn == 0:
                self._on_settings(None)
        elif isinstance(error, NetworkError):
            show_alert(
                title="Network Error",
                message=str(error),
                buttons=["OK"],
            )
        else:
            show_alert(
                title="OpenMic Error",
                message=str(error),
                buttons=["OK"],
            )

    def _reset_to_idle(self, show_done=False):
        """Transition: PROCESSING → IDLE."""
        self.state = "idle"
        self.title = "\U0001f399"  # 🎙
        self.status_item.title = "Status: Ready"
        if show_done:
            self._overlay.show_done()  # shows "Done" for 0.5s, then auto-transitions to idle
        else:
            self._overlay.show_idle()
