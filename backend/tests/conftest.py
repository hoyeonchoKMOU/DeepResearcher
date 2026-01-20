"""Pytest configuration and fixtures for backend tests."""

import pytest
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path.parent))


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Mock settings for all tests."""
    from unittest.mock import MagicMock

    mock_settings_obj = MagicMock()
    mock_settings_obj.semantic_scholar_api_key = None
    mock_settings_obj.gemini_api_key = None

    def get_mock_settings():
        return mock_settings_obj

    monkeypatch.setattr("backend.config.get_settings", get_mock_settings)
    return mock_settings_obj


@pytest.fixture
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
