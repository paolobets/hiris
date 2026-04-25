# hiris/app/version.py
"""Single source of truth for the HIRIS version.

Reads the version field from hiris/config.yaml at import time using a
lightweight regex — no YAML parser dependency required.
"""
import logging
import re
import pathlib

logger = logging.getLogger(__name__)

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"
_VERSION: str | None = None


def read_version() -> str:
    """Return the version string from config.yaml, e.g. '0.5.0'.

    Result is cached after the first successful read.
    Returns 'unknown' if the file cannot be read or the field is missing,
    and logs a warning so the failure is visible in the add-on log.
    """
    global _VERSION
    if _VERSION is not None:
        return _VERSION
    try:
        text = _CONFIG_PATH.read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            _VERSION = m.group(1)
            return _VERSION
        logger.warning("version field not found in %s — returning 'unknown'", _CONFIG_PATH)
        return "unknown"
    except Exception as exc:
        logger.warning("Cannot read version from %s: %s — returning 'unknown'", _CONFIG_PATH, exc)
        return "unknown"
