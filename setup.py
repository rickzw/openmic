"""py2app build configuration for OpenMic.app"""

from setuptools import setup

try:
    from py2app.build_app import py2app as _py2app

    class py2app(_py2app):
        """Subclass to clear install_requires before py2app 0.28+ rejects it.

        setuptools populates distribution.install_requires from pyproject.toml,
        but py2app 0.28+ raises an error if it is set (deps must already be installed).
        """

        def finalize_options(self):
            self.distribution.install_requires = []
            super().finalize_options()

    extra_setup = {"cmdclass": {"py2app": py2app}}
except ImportError:
    extra_setup = {}

APP = ["src/openmic/__main__.py"]
DATA_FILES = [
    ("resources", [
        "resources/icon.icns",
        "resources/icon_recording.icns",
        "resources/icon_processing.icns",
    ]),
]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "resources/icon.icns",
    "semi_standalone": True,  # Extract native libs (.dylib) from ZIP for dlopen()
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "OpenMic",
        "CFBundleDisplayName": "OpenMic",
        "CFBundleIdentifier": "com.openmic.voicetotext",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSMicrophoneUsageDescription": (
            "OpenMic needs microphone access to record your voice for transcription."
        ),
        "NSAppleEventsUsageDescription": (
            "OpenMic needs accessibility access to paste transcribed text into other applications."
        ),
    },
    "packages": ["openmic", "rumps", "sounddevice", "soundfile", "openai", "anthropic", "_sounddevice_data", "_soundfile_data"],
    "includes": ["AppKit", "Quartz", "AVFoundation"],
}

setup(
    app=APP,
    name="OpenMic",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    **extra_setup,
)
