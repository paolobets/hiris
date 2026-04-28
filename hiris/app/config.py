import os

EUR_RATE: float = 0.92  # approximate USD→EUR conversion rate


class Config:
    claude_api_key: str = os.environ.get("CLAUDE_API_KEY", "")
    log_level: str = os.environ.get("LOG_LEVEL", "info")
    ha_url: str = os.environ.get("HA_URL", "http://supervisor/core")
    supervisor_token: str = os.environ.get("SUPERVISOR_TOKEN", "")
