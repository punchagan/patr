from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from patr import state

OAUTH_CALLBACK = "/oauth/callback"

_oauth_state_store: dict[str, dict] = {}  # state -> {verifier, origin}


def oauth_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}{OAUTH_CALLBACK}"


def get_auth():
    """Return valid Gmail/Sheets credentials, refreshing the access token if
    needed.

    Raises RuntimeError with an already-user-facing message — not a sentinel
    to match on — for both "never connected" and "refresh token is dead"
    (expired after Google's 7-day limit for OAuth apps in Testing publishing
    status, or manually revoked): callers can just show str(e) as-is.
    """
    creds = None
    if state.TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(state.TOKEN_FILE, state.SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
            except RefreshError:
                raise RuntimeError(
                    "Your Gmail connection has expired — reconnect it in ⚙ Settings."
                )
            state.TOKEN_FILE.write_text(creds.to_json())
        else:
            raise RuntimeError("Gmail isn't connected — connect it in ⚙ Settings.")
    return creds


def auth_status() -> bool:
    """Whether Gmail/Sheets credentials exist and are (or can be refreshed
    to be) valid. The connected account's email is read separately from
    state.SENDER_EMAIL_FILE, written by the real userinfo API during the
    OAuth callback — not derivable from the token file itself."""
    if not state.TOKEN_FILE.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(state.TOKEN_FILE, state.SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            state.TOKEN_FILE.write_text(creds.to_json())
        return creds.valid
    except Exception:
        return False
