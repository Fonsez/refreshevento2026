from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("app_config.json")


def load_config(config_path: str | None = None) -> dict:
    if config_path:
        path = Path(config_path)
    else:
        if getattr(sys, "frozen", False):
            external_path = Path(sys.executable).resolve().parent / DEFAULT_CONFIG_PATH
            if external_path.exists():
                path = external_path
            else:
                base_path = Path(sys._MEIPASS)
                path = base_path / DEFAULT_CONFIG_PATH
        else:
            base_path = Path(__file__).resolve().parent
            path = base_path / DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["_meta"] = {
        "config_path": str(path),
        "base_dir": str(path.parent),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    return config


def resolve_resource_path(config: dict, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None

    candidate = Path(relative_path)
    if candidate.is_absolute():
        return candidate

    meta = config.get("_meta", {})
    base_dir = Path(meta.get("base_dir", Path(__file__).resolve().parent))
    base_candidate = base_dir / candidate
    if base_candidate.exists():
        return base_candidate

    exe_candidate = Path(sys.executable).resolve().parent / candidate
    if exe_candidate.exists():
        return exe_candidate

    if getattr(sys, "frozen", False):
        meipass_candidate = Path(sys._MEIPASS) / candidate
        if meipass_candidate.exists():
            return meipass_candidate

    return base_candidate
