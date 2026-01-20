"""Authentication API routes."""

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from backend.auth.oauth import GeminiOAuth
from backend.auth.token_manager import TokenManager
from backend.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Singleton instances
_oauth: GeminiOAuth | None = None
_token_manager: TokenManager | None = None

# File-based pending auth storage (persists across server restarts)
_PENDING_AUTH_FILE = Path(tempfile.gettempdir()) / "deep_researcher_pending_auth.json"


def _save_pending_auth(data: dict) -> None:
    """Save pending auth state to file."""
    _PENDING_AUTH_FILE.write_text(json.dumps(data))


def _load_pending_auth() -> dict:
    """Load pending auth state from file."""
    try:
        if _PENDING_AUTH_FILE.exists():
            return json.loads(_PENDING_AUTH_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _clear_pending_auth() -> None:
    """Clear pending auth state file."""
    try:
        if _PENDING_AUTH_FILE.exists():
            _PENDING_AUTH_FILE.unlink()
    except IOError:
        pass


def get_oauth() -> GeminiOAuth:
    """Get or create OAuth instance."""
    global _oauth, _token_manager
    if _oauth is None:
        _token_manager = TokenManager()
        _oauth = GeminiOAuth(token_manager=_token_manager)
    return _oauth


def get_token_manager() -> TokenManager:
    """Get or create token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


class AuthStatus(BaseModel):
    """Authentication status response."""

    authenticated: bool
    email: str | None = None
    project_id: str | None = None
    expires_at: float | None = None
    model: str = ""  # Will be set from settings

    def __init__(self, **data):
        if "model" not in data or not data["model"]:
            data["model"] = get_settings().gemini_model
        super().__init__(**data)


class AuthUrlResponse(BaseModel):
    """Authorization URL response."""

    auth_url: str
    message: str


class TokenExchangeRequest(BaseModel):
    """Token exchange request."""

    authorization_code: str


class TokenResponse(BaseModel):
    """Token response."""

    success: bool
    email: str | None = None
    message: str


@router.get("/status", response_model=AuthStatus)
async def get_auth_status() -> AuthStatus:
    """Check current authentication status."""
    oauth = get_oauth()

    if oauth.is_authenticated():
        token_data = oauth.token_manager.load_tokens()
        return AuthStatus(
            authenticated=True,
            email=token_data.email if token_data else None,
            project_id=token_data.project_id if token_data else None,
            expires_at=token_data.expires_at if token_data else None,
        )

    return AuthStatus(authenticated=False)


@router.get("/login-url", response_model=AuthUrlResponse)
async def get_login_url(redirect: str = Query("/", description="URL to redirect after login")) -> AuthUrlResponse:
    """Get the OAuth authorization URL.

    The frontend should redirect the user to this URL.
    After successful authentication, user will be redirected to the 'redirect' URL.
    """
    oauth = get_oauth()
    auth_url = oauth.get_authorization_url()

    # Store the pending auth state to file (persists across server restarts)
    _save_pending_auth({
        "code_verifier": oauth._code_verifier,
        "state": oauth._state,
        "redirect_url": redirect,  # Store redirect URL for after login
    })

    return AuthUrlResponse(
        auth_url=auth_url,
        message="Redirect user to this URL for authentication",
    )


@router.get("/callback", response_class=HTMLResponse)
async def handle_callback_get(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
) -> HTMLResponse:
    """Handle OAuth callback from browser redirect (GET request)."""
    # Load pending auth from file
    pending_auth = _load_pending_auth()

    # Check for error from OAuth provider
    if error:
        error_msg = error_description or error
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Failed</h1>
                <p>{error_msg}</p>
                <p><a href="http://localhost:3000/">Return to Home</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Verify we have pending auth state
    if not pending_auth:
        return HTMLResponse(
            content="""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Error</h1>
                <p>No pending authentication request. Please try logging in again.</p>
                <p><a href="http://localhost:3000/">Return to Home</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Verify state parameter (CSRF protection)
    expected_state = pending_auth.get("state")
    if state != expected_state:
        return HTMLResponse(
            content="""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Error</h1>
                <p>Invalid state parameter. This might be a security issue.</p>
                <p><a href="http://localhost:3000/">Return to Home</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            content="""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Error</h1>
                <p>No authorization code received.</p>
                <p><a href="http://localhost:3000/">Return to Home</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Restore code_verifier to OAuth instance
    oauth = get_oauth()
    oauth._code_verifier = pending_auth.get("code_verifier")
    oauth._state = pending_auth.get("state")

    # Clear pending auth file
    _clear_pending_auth()

    try:
        token_data = await oauth.exchange_code_for_tokens(code)

        # Get redirect URL from pending auth (default to home)
        redirect_url = pending_auth.get("redirect_url", "/")

        # Redirect to frontend after successful auth
        return HTMLResponse(
            content=f"""
            <html>
            <head>
                <title>Authentication Successful</title>
                <script>
                    // Redirect to frontend after short delay
                    setTimeout(function() {{
                        window.location.href = 'http://localhost:3000{redirect_url}';
                    }}, 1000);
                </script>
            </head>
            <body style="font-family: system-ui, sans-serif; text-align: center; padding: 50px; background: #0f172a; color: white;">
                <div style="max-width: 400px; margin: 0 auto;">
                    <div style="font-size: 48px; margin-bottom: 20px;">✓</div>
                    <h1 style="color: #22c55e; margin-bottom: 10px;">로그인 성공!</h1>
                    <p style="color: #94a3b8; margin-bottom: 20px;">환영합니다, {token_data.email}!</p>
                    <p style="color: #64748b; font-size: 14px;">애플리케이션으로 이동 중...</p>
                </div>
            </body>
            </html>
            """,
            status_code=200,
        )
    except Exception as e:
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Error</h1>
                <p>{str(e)}</p>
                <p><a href="http://localhost:3000/">Return to Home</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )


@router.post("/callback", response_model=TokenResponse)
async def handle_callback_post(request: TokenExchangeRequest) -> TokenResponse:
    """Handle OAuth callback (POST request for API usage)."""
    oauth = get_oauth()

    try:
        token_data = await oauth.exchange_code_for_tokens(request.authorization_code)
        return TokenResponse(
            success=True,
            email=token_data.email,
            message="Authentication successful",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login-interactive")
async def login_interactive() -> TokenResponse:
    """Perform interactive login (opens browser).

    This endpoint is for CLI/desktop use.
    """
    oauth = get_oauth()

    try:
        token_data = await oauth.login_interactive()
        return TokenResponse(
            success=True,
            email=token_data.email,
            message="Authentication successful",
        )
    except TimeoutError:
        raise HTTPException(status_code=408, detail="Authentication timed out")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refresh")
async def refresh_token() -> TokenResponse:
    """Refresh the access token."""
    token_manager = get_token_manager()

    token_data = await token_manager.refresh_access_token()
    if token_data:
        return TokenResponse(
            success=True,
            email=token_data.email,
            message="Token refreshed successfully",
        )

    raise HTTPException(status_code=401, detail="Failed to refresh token")


@router.post("/logout")
async def logout() -> dict:
    """Clear stored tokens (logout)."""
    oauth = get_oauth()
    oauth.logout()
    return {"success": True, "message": "Logged out successfully"}
