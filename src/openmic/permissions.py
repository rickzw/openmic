"""macOS permission checks for Accessibility and Microphone."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def check_accessibility() -> bool:
    """Check if the app has Accessibility permissions (needed for CGEvent tap + paste)."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        trusted = AXIsProcessTrusted()
        logger.info("Accessibility permission: %s", "granted" if trusted else "not granted")
        return trusted
    except ImportError:
        logger.warning("Could not import AXIsProcessTrusted, assuming not granted")
        return False


def request_accessibility() -> bool:
    """Check accessibility permission and trigger the macOS system prompt if not granted.

    Using AXIsProcessTrustedWithOptions with kAXTrustedCheckOptionPrompt=True
    registers the app in System Settings > Accessibility and shows the system dialog.
    Returns True if already trusted.
    """
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        return AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
    except (ImportError, Exception):
        logger.warning("Could not call AXIsProcessTrustedWithOptions")
        return False


def prompt_accessibility():
    """Open System Settings to the Accessibility pane."""
    subprocess.run([
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    ])


def check_microphone() -> bool:
    """Check if the app has Microphone permissions.

    On macOS, the system automatically prompts when the app first tries to
    access the microphone. This function checks the current authorization status.
    """
    try:
        from AVFoundation import (
            AVCaptureDevice,
            AVMediaTypeAudio,
        )
        # AVAuthorizationStatusAuthorized = 3
        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        granted = status == 3
        logger.info("Microphone permission: %s (status=%d)", "granted" if granted else "not granted", status)
        return granted
    except ImportError:
        logger.warning("Could not import AVFoundation, assuming microphone access")
        return True


def prompt_microphone():
    """Open System Settings to the Microphone pane."""
    subprocess.run([
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    ])
