import os
import sys
from pathlib import Path

PATR_ROOT = Path(__file__).parent  # src/patr/
DATA_DIR = PATR_ROOT / "data"  # src/patr/data/
REPO_ROOT = Path.cwd()
CONTENT_DIR = REPO_ROOT / "content" / "newsletter"


def _local_app_data() -> Path:
    """Windows per-user, non-roaming app data directory (LOCALAPPDATA)."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def _default_config_dir() -> Path:
    """Credentials/token/config location — %LOCALAPPDATA%\\patr\\config on
    Windows (not roaming: an OAuth token is tied to one machine), or
    ~/.config/patr elsewhere."""
    if sys.platform == "win32":
        return _local_app_data() / "patr" / "config"
    return Path.home() / ".config" / "patr"


def _default_backups_dir() -> Path:
    """Timestamped edition backups location — %LOCALAPPDATA%\\patr\\backups
    on Windows, or ~/.local/share/patr/backups elsewhere."""
    if sys.platform == "win32":
        return _local_app_data() / "patr" / "backups"
    return Path.home() / ".local" / "share" / "patr" / "backups"


CONFIG_DIR = _default_config_dir()
BACKUPS_DIR = _default_backups_dir()
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
SENDER_EMAIL_FILE = CONFIG_DIR / "sender_email.txt"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",
]
