import json
import os
import sys
from pathlib import Path

if os.name == "nt":
    APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "JARVIS"
else:
    APP_DATA_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jarvis"

CONFIG_PATH = APP_DATA_DIR / "api_keys.json"


def _legacy_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "api_keys.json"
    return Path(__file__).resolve().parent / "api_keys.json"


def _read_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(data: dict) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_config() -> dict:
    data = _read_config(CONFIG_PATH)
    if data:
        return data

    legacy = _read_config(_legacy_config_path())
    if legacy:
        _write_config(legacy)
    return legacy


def update_config(values: dict) -> dict:
    data = _read_config(CONFIG_PATH)
    if not data:
        data = _read_config(_legacy_config_path())
    data.update(values)
    _write_config(data)
    return data


def get_gemini_key() -> str | None:
    return get_config().get("gemini_api_key")

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    return get_config().get("os_system", "windows").lower()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"

# Ensure legacy config is migrated to APP_DATA_DIR on import
get_config()
