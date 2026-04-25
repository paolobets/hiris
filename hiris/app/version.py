# hiris/app/version.py
"""Single source of truth for the HIRIS version.

Reads the version field from hiris/config.yaml at import time using a
lightweight regex — no YAML parser dependency required.
"""
import re
import pathlib

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"


def read_version() -> str:
    """Return the version string from config.yaml, e.g. '0.5.0'.

    Returns 'unknown' if the file cannot be read or the field is missing.
    This function is safe to call at module import time.
    """
    try:
        text = _CONFIG_PATH.read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"
