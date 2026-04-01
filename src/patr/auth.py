import base64
import hashlib
import json
import secrets

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from patr import state

OAUTH_CALLBACK = "/oauth/callback"

_oauth_state_store: dict[str, dict] = {}  # state -> {verifier, origin}


def oauth_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}{OAUTH_CALLBACK}"


def get_auth():
    creds = None
    if state.TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(state.TOKEN_FILE, state.SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            state.TOKEN_FILE.write_text(creds.to_json())
        else:
            raise RuntimeError("not_authenticated")
    return creds


def auth_status():
    """Returns (connected: bool, email: str|None)"""
    if not state.TOKEN_FILE.exists():
        return False, None
    try:
        creds = Credentials.from_authorized_user_file(state.TOKEN_FILE, state.SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            state.TOKEN_FILE.write_text(creds.to_json())
        if creds.valid:
            # Extract email from token file
            data = json.loads(state.TOKEN_FILE.read_text())
            return True, data.get("client_id", "").split("-")[0] or None
    except Exception:
        pass
    return False, None
