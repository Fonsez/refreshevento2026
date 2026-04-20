from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Evento2026Automator",
        "--add-data",
        "assets;assets",
        "--add-data",
        "app_config.json;.",
        "--hidden-import",
        "PIL._tkinter_finder",
        "main.py",
    ]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
