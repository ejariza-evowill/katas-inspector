from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

GOOGLE_AUTH_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class GoogleOAuthClient:
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str


def resolve_google_access_token(
    *,
    explicit_access_token: str | None,
    credentials_file: str | None,
    token_cache_file: str | None,
    timeout_seconds: int,
) -> str | None:
    if explicit_access_token:
        return explicit_access_token
    if not credentials_file:
        return None

    credentials_path = Path(credentials_file)
    cache_path = Path(token_cache_file) if token_cache_file else default_token_cache_path(credentials_path)
    return get_google_access_token(
        credentials_path,
        token_cache_path=cache_path,
        timeout_seconds=timeout_seconds,
    )


def default_token_cache_path(credentials_path: Path) -> Path:
    return credentials_path.with_name(f"{credentials_path.stem}.token.json")


def get_google_access_token(
    credentials_path: Path,
    *,
    token_cache_path: Path,
    timeout_seconds: int,
) -> str:
    credentials = load_json_file(credentials_path)

    if is_authorized_user_credentials(credentials):
        access_token, _ = refresh_authorized_user(
            credentials,
            timeout_seconds=timeout_seconds,
        )
        return access_token

    client = parse_google_oauth_client(credentials)
    cached_credentials = load_json_file(token_cache_path) if token_cache_path.exists() else None
    if cached_credentials and is_authorized_user_credentials(cached_credentials):
        if cached_credentials.get("client_id") == client.client_id:
            try:
                access_token, refreshed_credentials = refresh_authorized_user(
                    cached_credentials,
                    timeout_seconds=timeout_seconds,
                )
                write_json_file(token_cache_path, refreshed_credentials)
                return access_token
            except RuntimeError:
                pass

    authorization = run_installed_app_flow(client)
    token_response = exchange_authorization_code(
        client,
        code=authorization["code"],
        code_verifier=authorization["code_verifier"],
        redirect_uri=authorization["redirect_uri"],
        timeout_seconds=timeout_seconds,
    )
    refresh_token = token_response.get("refresh_token")
    access_token = token_response.get("access_token")
    if not isinstance(refresh_token, str) or not isinstance(access_token, str):
        raise RuntimeError("Google OAuth token response did not include refresh_token and access_token.")

    authorized_user_credentials = {
        "type": "authorized_user",
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        "refresh_token": refresh_token,
        "token_uri": client.token_uri,
        "scopes": list(GOOGLE_AUTH_SCOPES),
    }
    write_json_file(token_cache_path, authorized_user_credentials)
    return access_token


def parse_google_oauth_client(credentials: dict[str, object]) -> GoogleOAuthClient:
    if "installed" in credentials and isinstance(credentials["installed"], dict):
        payload = credentials["installed"]
    elif "web" in credentials and isinstance(credentials["web"], dict):
        raise ValueError(
            "Google credentials file must be a Desktop app OAuth client. "
            "Web application credentials do not work with this loopback redirect flow."
        )
    else:
        raise ValueError(
            "Google credentials file must contain a Desktop app OAuth client configuration."
        )

    client_id = payload.get("client_id")
    client_secret = payload.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise ValueError("Google credentials file is missing client_id or client_secret.")

    auth_uri = payload.get("auth_uri", DEFAULT_AUTH_URI)
    token_uri = payload.get("token_uri", DEFAULT_TOKEN_URI)
    if not isinstance(auth_uri, str) or not isinstance(token_uri, str):
        raise ValueError("Google credentials file contains invalid auth_uri or token_uri.")

    return GoogleOAuthClient(
        client_id=client_id,
        client_secret=client_secret,
        auth_uri=auth_uri,
        token_uri=token_uri,
    )


def is_authorized_user_credentials(payload: dict[str, object]) -> bool:
    return (
        payload.get("type") == "authorized_user"
        and isinstance(payload.get("client_id"), str)
        and isinstance(payload.get("client_secret"), str)
        and isinstance(payload.get("refresh_token"), str)
    )


def refresh_authorized_user(
    credentials: dict[str, object],
    *,
    timeout_seconds: int,
) -> tuple[str, dict[str, object]]:
    token_uri = credentials.get("token_uri", DEFAULT_TOKEN_URI)
    if not isinstance(token_uri, str):
        raise ValueError("Authorized user credentials contain an invalid token_uri.")

    token_response = post_form_for_json(
        token_uri,
        {
            "client_id": str(credentials["client_id"]),
            "client_secret": str(credentials["client_secret"]),
            "refresh_token": str(credentials["refresh_token"]),
            "grant_type": "refresh_token",
        },
        timeout_seconds=timeout_seconds,
    )
    access_token = token_response.get("access_token")
    if not isinstance(access_token, str):
        raise RuntimeError("Google OAuth refresh response did not include an access_token.")
    refreshed_credentials = dict(credentials)
    refreshed_credentials["access_token"] = access_token
    return access_token, refreshed_credentials


def run_installed_app_flow(client: GoogleOAuthClient) -> dict[str, str]:
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = build_code_challenge(code_verifier)
    result: dict[str, str] = {}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if params.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid OAuth state.")
                result["error"] = "invalid_state"
                return

            if "error" in params:
                result["error"] = params["error"][0]
            elif "code" in params:
                result["code"] = params["code"][0]
            else:
                result["error"] = "missing_code"

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorization complete. You can close this window.")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), OAuthCallbackHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    auth_url = client.auth_uri + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(GOOGLE_AUTH_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )

    print("Open this URL to authorize Google access:", file=sys.stderr)
    print(auth_url, file=sys.stderr)
    webbrowser.open(auth_url, new=1, autoraise=True)

    server.timeout = 300
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=305)
    server.server_close()

    if "error" in result:
        raise RuntimeError(f"Google OAuth authorization failed: {result['error']}.")
    if "code" not in result:
        raise RuntimeError(
            "Timed out waiting for Google OAuth authorization. Open the URL above in a browser "
            "running on this machine and try again."
        )

    return {
        "code": result["code"],
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }


def exchange_authorization_code(
    client: GoogleOAuthClient,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    timeout_seconds: int,
) -> dict[str, object]:
    return post_form_for_json(
        client.token_uri,
        {
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout_seconds=timeout_seconds,
    )


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def post_form_for_json(
    url: str,
    form_data: dict[str, str],
    *,
    timeout_seconds: int,
) -> dict[str, object]:
    encoded_form = urlencode(form_data).encode("utf-8")
    request = Request(
        url,
        data=encoded_form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "katas-evaluator/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google OAuth returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Google OAuth endpoint ({exc.reason}).") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Google OAuth returned an unexpected JSON payload.")
    return payload


def load_json_file(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object.")
    return payload


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
