import json
import os
from typing import Any, Dict


DEFAULT_CONFIG_NAME = "config.json"


class ConfigError(RuntimeError):
    """Custom error for config-related problems."""
    pass


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """
    Load JSON config file with required and optional fields.

    By default, looks for config.json in the project root
    (one directory above src/).
    """
    if config_path:
        path = config_path
    else:
        # project root (one level above src)
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, DEFAULT_CONFIG_NAME)

    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Required fields
    sa_path = cfg.get("SA_JSON_PATH")
    ww_key_path = cfg.get("WW_KEY_PATH")
    if not sa_path:
        raise ConfigError("SA_JSON_PATH is required in config.json")
    if not ww_key_path:
        raise ConfigError("WW_KEY_PATH is required in config.json")

    # Defaults for optional fields
    cfg.setdefault("CALENDAR_ID", "primary")
    cfg.setdefault("WW_LOCATION_ID", None)
    cfg.setdefault("WW_DAYS", 7)
    cfg.setdefault("CSV_PATH", None)

    return cfg


def load_text_secret(path: str) -> str:
    """Read a text file (like ww_key.txt) and return stripped contents."""
    if not os.path.exists(path):
        raise ConfigError(f"Secret file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()