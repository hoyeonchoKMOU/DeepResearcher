"""Application settings using Pydantic Settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Security files base path
    security_dir: Path = Path("data/security")

    # Gemini CLI OAuth - Loaded from data/security/google_oauth.json
    google_client_id: str = ""
    google_client_secret: str = ""
    gcp_project_id: str = ""
    oauth_callback_port: int = 8085

    # Gemini Model Configuration
    gemini_model: str = "gemini-3-pro-preview"
    gemini_temperature: float = 0.7
    gemini_max_output_tokens: int = 8192
    gemini_thinking_level: str = "high"  # "low" or "high" for Gemini 3 models
    gemini_include_thoughts: bool = True

    # Semantic Scholar - Loaded from data/security/api_keys.json
    semantic_scholar_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/deep_researcher"

    # Application
    debug: bool = True
    log_level: str = "INFO"

    # Token storage (runtime-generated OAuth tokens)
    token_storage_path: str = "~/.deep-researcher/auth.json"

    def __init__(self, **kwargs):
        """Initialize settings and load credentials from security files."""
        super().__init__(**kwargs)
        self._load_security_credentials()

    def _load_security_credentials(self) -> None:
        """Load credentials from data/security folder."""
        # Load Google OAuth credentials
        google_oauth_file = self.security_dir / "google_oauth.json"
        if google_oauth_file.exists():
            try:
                with open(google_oauth_file, 'r', encoding='utf-8') as f:
                    oauth_data = json.load(f)
                    self.google_client_id = oauth_data.get("client_id", "")
                    self.google_client_secret = oauth_data.get("client_secret", "")
                    if oauth_data.get("project_id"):
                        self.gcp_project_id = oauth_data["project_id"]
                logger.info("Loaded Google OAuth credentials from security file")
            except Exception as e:
                logger.warning(f"Failed to load Google OAuth credentials: {e}")
        else:
            logger.warning(
                f"Google OAuth file not found: {google_oauth_file}. "
                "Copy data/security.example/google_oauth.json to data/security/"
            )

        # Load API keys
        api_keys_file = self.security_dir / "api_keys.json"
        if api_keys_file.exists():
            try:
                with open(api_keys_file, 'r', encoding='utf-8') as f:
                    api_keys = json.load(f)
                    self.semantic_scholar_api_key = api_keys.get("semantic_scholar_api_key", "")
                logger.info("Loaded API keys from security file")
            except Exception as e:
                logger.warning(f"Failed to load API keys: {e}")
        else:
            logger.warning(
                f"API keys file not found: {api_keys_file}. "
                "Copy data/security.example/api_keys.json to data/security/"
            )

    @property
    def token_storage_full_path(self) -> Path:
        """Get full path for token storage."""
        return Path(self.token_storage_path).expanduser()

    # OAuth URLs
    @property
    def oauth_authorize_url(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def oauth_token_url(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def oauth_redirect_uri(self) -> str:
        return "http://localhost:8000/api/auth/callback"

    @property
    def oauth_scopes(self) -> list[str]:
        # Gemini CLI scopes (simpler than Antigravity)
        return [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ]

    # Gemini Code Assist API endpoint
    @property
    def gemini_endpoint(self) -> str:
        return "https://cloudcode-pa.googleapis.com"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance for convenience
settings = get_settings()
