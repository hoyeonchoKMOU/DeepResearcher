"""Tests for Paper Writing API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Import the router module
from backend.api.routes import research


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(research.router)

    # Clear in-memory storage before each test
    research._projects.clear()
    research._message_queues.clear()
    research._process_queues.clear()
    research._discussion_agents.clear()

    return TestClient(app)


def create_project_and_unlock_paper_writing(client) -> str:
    """Helper to create a project and unlock Paper Writing.

    This requires completing both Research Definition AND Experiment Design.
    """
    # Create project
    response = client.post(
        "/api/research/v3/create",
        json={"topic": "Test Topic for Paper Writing"}
    )
    project_id = response.json()["project_id"]

    # Complete Research Definition (unlocks Literature Review)
    client.post(
        f"/api/research/v3/{project_id}/process/research-experiment/complete"
    )

    # Switch to Experiment Design phase
    client.post(
        f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
        json={"phase": "experiment_design"}
    )

    # Complete Experiment Design (unlocks Paper Writing)
    client.post(
        f"/api/research/v3/{project_id}/process/research-experiment/complete"
    )

    return project_id


class TestPaperWritingState:
    """Tests for Paper Writing state endpoint."""

    def test_get_state_locked(self, client):
        """Test getting state when Paper Writing is locked."""
        # Create project (Paper Writing starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Get Paper Writing state
        response = client.get(
            f"/api/research/v3/{project_id}/process/paper-writing"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "locked"
        assert data["is_locked"] is True
        assert data["messages"] == []
        assert data["artifact"] == ""

    def test_get_state_locked_after_rd_only(self, client):
        """Test Paper Writing is still locked after only Research Definition complete."""
        # Create project
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "RD Only Test"}
        )
        project_id = response.json()["project_id"]

        # Complete only Research Definition
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # Paper Writing should still be locked
        response = client.get(
            f"/api/research/v3/{project_id}/process/paper-writing"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_locked"] is True

    def test_get_state_unlocked(self, client):
        """Test getting state when Paper Writing is unlocked."""
        project_id = create_project_and_unlock_paper_writing(client)

        # Get Paper Writing state
        response = client.get(
            f"/api/research/v3/{project_id}/process/paper-writing"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "unlocked"
        assert data["is_locked"] is False


class TestPaperWritingStart:
    """Tests for Paper Writing start endpoint."""

    def test_start_when_locked(self, client):
        """Test that starting fails when Paper Writing is locked."""
        # Create project (Paper Writing starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Start Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Try to start - should fail
        response = client.post(
            f"/api/research/v3/{project_id}/process/paper-writing/start"
        )

        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()


class TestPaperWritingChat:
    """Tests for Paper Writing chat endpoint."""

    def test_chat_when_locked(self, client):
        """Test that chat fails when Paper Writing is locked."""
        # Create project (Paper Writing starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Chat Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Try to chat - should fail
        response = client.post(
            f"/api/research/v3/{project_id}/process/paper-writing/chat",
            json={"content": "Test message"}
        )

        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()

    def test_chat_not_found(self, client):
        """Test chat with non-existent project."""
        response = client.post(
            "/api/research/v3/nonexistent/process/paper-writing/chat",
            json={"content": "Test message"}
        )

        assert response.status_code == 404


class TestUnlockFlow:
    """Tests for the complete unlock flow to Paper Writing."""

    def test_complete_unlock_sequence(self, client):
        """Test the complete sequence to unlock Paper Writing."""
        # Create project
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Full Flow Test"}
        )
        project_id = response.json()["project_id"]

        # Initial state: all locked except Research & Experiment
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["processes"]["research_experiment"]["status"] == "active"
        assert status["processes"]["literature_review"]["status"] == "locked"
        assert status["processes"]["paper_writing"]["status"] == "locked"

        # Step 1: Complete Research Definition
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # After RD: Literature Review unlocked, Paper Writing still locked
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["research_definition_complete"] is True
        assert status["processes"]["literature_review"]["status"] == "unlocked"
        assert status["processes"]["paper_writing"]["status"] == "locked"

        # Step 2: Switch to Experiment Design
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "experiment_design"}
        )

        # Step 3: Complete Experiment Design
        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )
        assert response.json()["unlocked_process"] == "paper_writing"

        # Final state: all unlocked
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["research_definition_complete"] is True
        assert status["experiment_design_complete"] is True
        assert status["processes"]["literature_review"]["status"] == "unlocked"
        assert status["processes"]["paper_writing"]["status"] == "unlocked"

    def test_paper_writing_accessible_after_unlock(self, client):
        """Test that Paper Writing is accessible after unlock."""
        project_id = create_project_and_unlock_paper_writing(client)

        # Get state should work
        response = client.get(
            f"/api/research/v3/{project_id}/process/paper-writing"
        )
        assert response.status_code == 200
        assert response.json()["is_locked"] is False


class TestAccessControl:
    """Tests for Paper Writing access control."""

    def test_all_operations_blocked_when_locked(self, client):
        """Test that all write operations are blocked when locked."""
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Access Control Test"}
        )
        project_id = response.json()["project_id"]

        # Start - blocked
        start_response = client.post(
            f"/api/research/v3/{project_id}/process/paper-writing/start"
        )
        assert start_response.status_code == 403

        # Chat - blocked
        chat_response = client.post(
            f"/api/research/v3/{project_id}/process/paper-writing/chat",
            json={"content": "Test"}
        )
        assert chat_response.status_code == 403

    def test_read_operations_allowed_when_locked(self, client):
        """Test that read operations work even when locked."""
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Read Access Test"}
        )
        project_id = response.json()["project_id"]

        # Get state - allowed
        state_response = client.get(
            f"/api/research/v3/{project_id}/process/paper-writing"
        )
        assert state_response.status_code == 200
