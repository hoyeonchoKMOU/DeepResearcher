"""Tests for v3 API endpoints - Process-based architecture."""

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


@pytest.fixture
def mock_token_manager():
    """Mock TokenManager for authentication."""
    with patch("backend.api.routes.research.TokenManager") as mock:
        instance = MagicMock()
        instance.get_valid_access_token = AsyncMock(return_value="test_token")
        mock.return_value = instance
        yield mock


class TestV3ProjectCreation:
    """Tests for v3 project creation."""

    def test_create_project_v3(self, client):
        """Test creating a new v3 project."""
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Test Research Topic"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "project_id" in data
        assert data["topic"] == "Test Research Topic"
        assert data["research_definition_complete"] is False
        assert data["experiment_design_complete"] is False
        assert "processes" in data
        assert data["processes"]["research_experiment"]["status"] == "active"
        assert data["processes"]["literature_review"]["status"] == "locked"
        assert data["processes"]["paper_writing"]["status"] == "locked"

    def test_get_project_status_v3(self, client):
        """Test getting v3 project status."""
        # Create a project first
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Status Test Topic"}
        )
        project_id = create_response.json()["project_id"]

        # Get status
        response = client.get(f"/api/research/v3/{project_id}/status")

        assert response.status_code == 200
        data = response.json()

        assert data["project_id"] == project_id
        assert data["topic"] == "Status Test Topic"
        assert "processes" in data

    def test_get_project_status_v3_not_found(self, client):
        """Test getting status for non-existent project."""
        response = client.get("/api/research/v3/nonexistent-id/status")

        assert response.status_code == 404


class TestResearchExperimentProcess:
    """Tests for Research & Experiment process endpoints."""

    def test_get_research_experiment_process(self, client):
        """Test getting Research & Experiment process state."""
        # Create a project first
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "R&E Test Topic"}
        )
        project_id = create_response.json()["project_id"]

        # Get process state
        response = client.get(
            f"/api/research/v3/{project_id}/process/research-experiment"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "active"
        assert data["current_phase"] == "research_definition"
        assert data["messages"] == []
        assert data["artifact"] == ""
        assert "state" in data

    def test_switch_phase(self, client):
        """Test switching phase within Research & Experiment."""
        # Create a project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Phase Switch Test"}
        )
        project_id = create_response.json()["project_id"]

        # Switch to experiment_design
        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "experiment_design"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "switched"
        assert data["old_phase"] == "research_definition"
        assert data["new_phase"] == "experiment_design"

        # Verify the phase was switched
        status_response = client.get(
            f"/api/research/v3/{project_id}/process/research-experiment"
        )
        assert status_response.json()["current_phase"] == "experiment_design"

    def test_switch_phase_invalid(self, client):
        """Test switching to invalid phase."""
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Invalid Phase Test"}
        )
        project_id = create_response.json()["project_id"]

        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "invalid_phase"}
        )

        assert response.status_code == 400

    def test_complete_research_definition(self, client):
        """Test completing Research Definition phase."""
        # Create a project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Complete RD Test"}
        )
        project_id = create_response.json()["project_id"]

        # Verify Literature Review is initially locked
        status_before = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status_before["processes"]["literature_review"]["status"] == "locked"

        # Complete Research Definition
        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["unlocked_process"] == "literature_review"
        assert "Literature Review is now unlocked" in data["message"]

        # Verify Literature Review is now unlocked
        status_after = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status_after["research_definition_complete"] is True
        assert status_after["processes"]["literature_review"]["status"] == "unlocked"

    def test_complete_experiment_design(self, client):
        """Test completing Experiment Design phase."""
        # Create a project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Complete ED Test"}
        )
        project_id = create_response.json()["project_id"]

        # Switch to experiment_design phase
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "experiment_design"}
        )

        # Verify Paper Writing is initially locked
        status_before = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status_before["processes"]["paper_writing"]["status"] == "locked"

        # Complete Experiment Design
        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["unlocked_process"] == "paper_writing"
        assert "Paper Writing is now unlocked" in data["message"]

        # Verify Paper Writing is now unlocked
        status_after = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status_after["experiment_design_complete"] is True
        assert status_after["processes"]["paper_writing"]["status"] == "unlocked"

    def test_complete_already_completed(self, client):
        """Test completing a phase that was already completed."""
        # Create a project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Already Complete Test"}
        )
        project_id = create_response.json()["project_id"]

        # Complete Research Definition first time
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # Try to complete again
        response = client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["unlocked_process"] is None  # Nothing new was unlocked
        assert "already completed" in data["message"]

    def test_one_way_unlock_after_modification(self, client):
        """Test that unlock is one-way - modifying after completion doesn't re-lock."""
        # Create a project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "One-way Unlock Test"}
        )
        project_id = create_response.json()["project_id"]

        # Complete Research Definition
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # Verify Literature Review is unlocked
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["research_definition_complete"] is True
        assert status["processes"]["literature_review"]["status"] == "unlocked"

        # Switch phases (simulate going back to modify)
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "experiment_design"}
        )

        # Switch back to research_definition
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "research_definition"}
        )

        # Verify Literature Review is STILL unlocked (one-way)
        status_after = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status_after["research_definition_complete"] is True
        assert status_after["processes"]["literature_review"]["status"] == "unlocked"


class TestResearchExperimentChat:
    """Tests for Research & Experiment chat functionality."""

    def test_chat_endpoint_exists(self, client):
        """Test that chat endpoint exists and requires project."""
        response = client.post(
            "/api/research/v3/nonexistent/process/research-experiment/chat",
            json={"content": "Test message"}
        )

        assert response.status_code == 404


class TestProcessAccessibility:
    """Tests for process accessibility based on unlock status."""

    def test_research_experiment_always_accessible(self, client):
        """Test that Research & Experiment is always accessible."""
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Accessibility Test"}
        )
        project_id = create_response.json()["project_id"]

        # Should be accessible immediately
        response = client.get(
            f"/api/research/v3/{project_id}/process/research-experiment"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_unlock_flow(self, client):
        """Test the complete unlock flow."""
        # Create project
        create_response = client.post(
            "/api/research/v3/create",
            json={"topic": "Full Unlock Flow Test"}
        )
        project_id = create_response.json()["project_id"]

        # Initial state: only R&E accessible
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["processes"]["research_experiment"]["status"] == "active"
        assert status["processes"]["literature_review"]["status"] == "locked"
        assert status["processes"]["paper_writing"]["status"] == "locked"

        # Complete Research Definition
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # After RD complete: Literature Review unlocked
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["processes"]["literature_review"]["status"] == "unlocked"
        assert status["processes"]["paper_writing"]["status"] == "locked"

        # Switch to Experiment Design and complete it
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/switch-phase",
            json={"phase": "experiment_design"}
        )
        client.post(
            f"/api/research/v3/{project_id}/process/research-experiment/complete"
        )

        # After ED complete: Paper Writing also unlocked
        status = client.get(f"/api/research/v3/{project_id}/status").json()
        assert status["processes"]["literature_review"]["status"] == "unlocked"
        assert status["processes"]["paper_writing"]["status"] == "unlocked"
