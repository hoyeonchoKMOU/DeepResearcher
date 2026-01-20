"""OAuth 2.0 + PKCE authentication for Gemini CLI."""

import asyncio
import base64
import hashlib
import secrets
import time
import webbrowser
from typing import Optional
from urllib.parse import urlencode

import httpx
import structlog
from aiohttp import web

from backend.auth.token_manager import TokenData, TokenManager
from backend.config import get_settings

logger = structlog.get_logger(__name__)


class GeminiOAuth:
    """Handle OAuth 2.0 + PKCE authentication flow for Google Gemini CLI."""

    def __init__(self, token_manager: Optional[TokenManager] = None):
        """Initialize OAuth handler.

        Args:
            token_manager: Token manager instance. Creates new one if not provided.
        """
        self.settings = get_settings()
        self.token_manager = token_manager or TokenManager()
        self._code_verifier: Optional[str] = None
        self._state: Optional[str] = None

    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier.

        Returns:
            Random code verifier string.
        """
        # Generate 32 random bytes and encode as base64url
        random_bytes = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")

    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier.

        Args:
            verifier: Code verifier string.

        Returns:
            SHA256 hash of verifier as base64url string.
        """
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def _generate_state(self) -> str:
        """Generate random state for CSRF protection.

        Returns:
            Random state string.
        """
        return secrets.token_urlsafe(32)

    def get_authorization_url(self) -> str:
        """Generate OAuth authorization URL.

        Returns:
            Full authorization URL with all parameters.
        """
        self._code_verifier = self._generate_code_verifier()
        self._state = self._generate_state()
        code_challenge = self._generate_code_challenge(self._code_verifier)

        params = {
            "client_id": self.settings.google_client_id,
            "response_type": "code",
            "redirect_uri": self.settings.oauth_redirect_uri,
            "scope": " ".join(self.settings.oauth_scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": self._state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Always show consent to get refresh token
        }

        return f"{self.settings.oauth_authorize_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, authorization_code: str) -> TokenData:
        """Exchange authorization code for tokens.

        Args:
            authorization_code: Code received from OAuth callback.

        Returns:
            Token data with access and refresh tokens.

        Raises:
            httpx.HTTPError: If token exchange fails.
        """
        if not self._code_verifier:
            raise ValueError("Code verifier not set. Call get_authorization_url first.")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.settings.oauth_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "redirect_uri": self.settings.oauth_redirect_uri,
                    "code_verifier": self._code_verifier,
                },
            )
            response.raise_for_status()
            data = response.json()

        # Get user info
        user_email = await self._get_user_email(data["access_token"])

        token_data = TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + data.get("expires_in", 3600),
            token_type=data.get("token_type", "Bearer"),
            email=user_email,
            project_id=self.settings.gcp_project_id,
            scopes=data.get("scope", "").split(),
        )

        self.token_manager.save_tokens(token_data)
        logger.info("OAuth tokens obtained", email=user_email)

        return token_data

    async def _get_user_email(self, access_token: str) -> Optional[str]:
        """Get user email from access token.

        Args:
            access_token: Valid access token.

        Returns:
            User email or None if request fails.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                return response.json().get("email")
            except httpx.HTTPError:
                return None

    async def login_interactive(self) -> TokenData:
        """Perform interactive OAuth login flow.

        Opens browser for user authentication and waits for callback.

        Returns:
            Token data after successful authentication.
        """
        auth_url = self.get_authorization_url()
        expected_state = self._state

        # Event to signal when we receive the callback
        code_received = asyncio.Event()
        received_code: dict = {}

        async def handle_callback(request: web.Request) -> web.Response:
            """Handle OAuth callback."""
            # Verify state
            state = request.query.get("state")
            if state != expected_state:
                return web.Response(
                    text="Invalid state parameter. Authentication failed.",
                    status=400,
                )

            # Check for error
            error = request.query.get("error")
            if error:
                error_desc = request.query.get("error_description", "Unknown error")
                return web.Response(
                    text=f"Authentication error: {error_desc}",
                    status=400,
                )

            # Get authorization code
            code = request.query.get("code")
            if not code:
                return web.Response(
                    text="No authorization code received.",
                    status=400,
                )

            received_code["code"] = code
            code_received.set()

            return web.Response(
                text="""
                <html>
                <head><title>DeepResearcher - Authentication Successful</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        # Create local server
        app = web.Application()
        app.router.add_get("/oauth2callback", handle_callback)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "localhost", self.settings.oauth_callback_port)
        await site.start()

        logger.info(
            "OAuth callback server started",
            port=self.settings.oauth_callback_port,
        )

        # Open browser
        logger.info("Opening browser for authentication")
        webbrowser.open(auth_url)

        # Wait for callback (with timeout)
        try:
            await asyncio.wait_for(code_received.wait(), timeout=300)  # 5 min timeout
        except asyncio.TimeoutError:
            await runner.cleanup()
            raise TimeoutError("Authentication timed out")

        await runner.cleanup()

        # Exchange code for tokens
        return await self.exchange_code_for_tokens(received_code["code"])

    def is_authenticated(self) -> bool:
        """Check if user is authenticated with valid tokens.

        Returns:
            True if valid tokens exist.
        """
        token_data = self.token_manager.load_tokens()
        if not token_data:
            return False

        # Check if token is expired (with 60s buffer)
        return not self.token_manager.is_token_expired(buffer_seconds=60)

    async def ensure_authenticated(self) -> TokenData:
        """Ensure user is authenticated, prompting login if needed.

        Returns:
            Valid token data.
        """
        token_data = self.token_manager.load_tokens()

        if token_data and not self.token_manager.is_token_expired():
            return token_data

        if token_data and self.token_manager.is_token_expired():
            # Try to refresh
            refreshed = await self.token_manager.refresh_access_token()
            if refreshed:
                return refreshed

        # Need to login
        return await self.login_interactive()

    def logout(self) -> None:
        """Clear stored tokens (logout)."""
        self.token_manager.clear_tokens()
        logger.info("User logged out")
