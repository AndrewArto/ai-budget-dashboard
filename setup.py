"""Setup for py2app bundling."""

from setuptools import setup

APP = ["main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,  # Hide dock icon (menu bar app)
        "CFBundleName": "AI Budget Dashboard",
        "CFBundleShortVersionString": "0.1.0",
    },
    "packages": ["rumps", "requests", "keyring"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
