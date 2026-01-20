"""Token Manager for storing and refreshing OAuth tokens."""

import json
import time
from pathlib import Path
from typing import Optional

import httpx
import structlog
from pydantic import BaseModel

from backend.config import get_settings

logger = structlog.get_logger(__name__)


class TokenData(BaseModel):
    """OAuth token data model."""

    access_token: str = ""  # Will be obtained via refresh
    refresh_token: str
    expires_at: float = 0  # Unix timestamp, 0 means needs refresh
    token_type: str = "Bearer"
    email: Optional[str] = None
    project_id: Optional[str] = None
    scopes: list[str] = []


class TokenManager:
    """Manages OAuth token storage, retrieval, and refresh.

    This is a standalone implementation that does not depend on any external
    tools. Tokens are stored in ~/.deep-researcher/auth.json.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize token manager.

        Args:
            storage_path: Path to store tokens. Defaults to settings value.
        """
        settings = get_settings()
        self.storage_path = storage_path or settings.token_storage_full_path
        self.settings = settings
        self._token_data: Optional[TokenData] = None

    def _ensure_storage_dir(self) -> None:
        """Ensure token storage directory exists."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def save_tokens(self, token_data: TokenData) -> None:
        """Save tokens to storage.

        Args:
            token_data: Token data to save.
        """
        self._ensure_storage_dir()
        self._token_data = token_data

        data = {
            "google": {
                "type": "oauth",
                "accounts": [token_data.model_dump()],
            }
        }

        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Tokens saved", path=str(self.storage_path))

    def _load_from_storage(self) -> Optional[TokenData]:
        """Load tokens from storage file.

        Returns:
            Token data if exists, None otherwise.
        """
        if not self.storage_path.exists():
            logger.debug("No token file found", path=str(self.storage_path))
            return None

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            accounts = data.get("google", {}).get("accounts", [])
            if not accounts:
                return None

            return TokenData(**accounts[0])

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("Failed to load tokens from storage", error=str(e))
            return None

    def load_tokens(self) -> Optional[TokenData]:
        """Load tokens from storage.

        Returns:
            Token data if exists, None otherwise.
        """
        if self._token_data:
            return self._token_data

        self._token_data = self._load_from_storage()
        return self._token_data

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if access token is expired or about to expire.

        Args:
            buffer_seconds: Buffer time before actual expiry.

        Returns:
            True if token is expired or will expire within buffer time.
        """
        token_data = self.load_tokens()
        if not token_data:
            return True

        # If no access token or expires_at is 0, need refresh
        if not token_data.access_token or token_data.expires_at == 0:
            return True

        return time.time() >= (token_data.expires_at - buffer_seconds)

    async def refresh_access_token(self) -> Optional[TokenData]:
        """Refresh the access token using refresh token.

        Returns:
            Updated token data if successful, None otherwise.
        """
        token_data = self.load_tokens()
        if not token_data or not token_data.refresh_token:
            logger.error("No refresh token available")
            return None

        logger.info("Refreshing access token")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.settings.oauth_token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token_data.refresh_token,
                        "client_id": self.settings.google_client_id,
                        "client_secret": self.settings.google_client_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Update token data
                token_data.access_token = data["access_token"]
                token_data.expires_at = time.time() + data.get("expires_in", 3600)

                # Refresh token might be rotated
                if "refresh_token" in data:
                    token_data.refresh_token = data["refresh_token"]

                self.save_tokens(token_data)
                logger.info("Access token refreshed successfully")
                return token_data

            except httpx.HTTPError as e:
                logger.error("Failed to refresh token", error=str(e))
                return None

    async def get_valid_access_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token or None if unavailable.
        """
        if self.is_token_expired():
            token_data = await self.refresh_access_token()
            if not token_data:
                return None
            return token_data.access_token

        token_data = self.load_tokens()
        return token_data.access_token if token_data else None

    def clear_tokens(self) -> None:
        """Clear stored tokens."""
        self._token_data = None
        if self.storage_path.exists():
            self.storage_path.unlink()
            logger.info("Tokens cleared")
