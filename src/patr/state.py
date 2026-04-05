from pathlib import Path

PATR_ROOT = Path(__file__).parent  # src/patr/
DATA_DIR = PATR_ROOT / "data"  # src/patr/data/
REPO_ROOT = Path.cwd()
CONTENT_DIR = REPO_ROOT / "content" / "newsletter"
CONFIG_DIR = Path.home() / ".config" / "patr"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
SENDER_EMAIL_FILE = CONFIG_DIR / "sender_email.txt"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",
]
