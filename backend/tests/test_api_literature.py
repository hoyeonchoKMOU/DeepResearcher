"""Tests for Literature Review API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Import the router modules
from backend.api.routes import research, literature


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(research.router)
    app.include_router(literature.router)

    # Clear in-memory storage before each test
    research._projects.clear()
    research._message_queues.clear()
    research._process_queues.clear()
    research._discussion_agents.clear()

    # Set shared reference for literature router
    literature.set_projects_reference(research._projects)

    return TestClient(app)


def create_project_and_unlock(client) -> str:
    """Helper to create a project and unlock Literature Review."""
    # Create project
    response = client.post(
        "/api/research/v3/create",
        json={"topic": "Test Topic for Literature Review"}
    )
    project_id = response.json()["project_id"]

    # Complete Research Definition to unlock Literature Review
    client.post(
        f"/api/research/v3/{project_id}/process/research-experiment/complete"
    )

    return project_id


class TestLiteratureReviewState:
    """Tests for Literature Review state endpoints."""

    def test_get_state_locked(self, client):
        """Test getting state when Literature Review is locked."""
        # Create project (Literature Review starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Get Literature Review state
        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "locked"
        assert data["is_locked"] is True
        assert data["papers"] == []
        assert data["search_history"] == []

    def test_get_state_unlocked(self, client):
        """Test getting state when Literature Review is unlocked."""
        project_id = create_project_and_unlock(client)

        # Get Literature Review state
        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "unlocked"
        assert data["is_locked"] is False


class TestPaperManagement:
    """Tests for paper management endpoints."""

    def test_add_paper_when_locked(self, client):
        """Test that adding paper fails when Literature Review is locked."""
        # Create project (Literature Review starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Locked Add Test"}
        )
        project_id = response.json()["project_id"]

        # Try to add paper - should fail
        response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={
                "title": "Test Paper",
                "authors": ["Author 1", "Author 2"],
                "year": 2024,
            }
        )

        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()

    def test_add_paper_when_unlocked(self, client):
        """Test adding paper when Literature Review is unlocked."""
        project_id = create_project_and_unlock(client)

        # Add paper
        response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={
                "title": "Test Paper",
                "authors": ["Author 1", "Author 2"],
                "year": 2024,
                "abstract": "Test abstract",
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["title"] == "Test Paper"
        assert data["authors"] == ["Author 1", "Author 2"]
        assert data["year"] == 2024
        assert data["type"] == "upload"
        assert data["status"] == "pending"
        assert "paper_" in data["id"]

    def test_list_papers(self, client):
        """Test listing all papers."""
        project_id = create_project_and_unlock(client)

        # Add some papers
        client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Paper 1", "year": 2023}
        )
        client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Paper 2", "year": 2024}
        )

        # List papers
        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/papers"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert len(data["papers"]) == 2

    def test_get_paper(self, client):
        """Test getting a specific paper."""
        project_id = create_project_and_unlock(client)

        # Add a paper
        add_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Specific Paper", "year": 2024}
        )
        paper_id = add_response.json()["id"]

        # Get paper
        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/papers/{paper_id}"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == paper_id
        assert data["title"] == "Specific Paper"

    def test_get_paper_not_found(self, client):
        """Test getting non-existent paper."""
        project_id = create_project_and_unlock(client)

        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/papers/nonexistent"
        )

        assert response.status_code == 404

    def test_delete_paper(self, client):
        """Test deleting a paper."""
        project_id = create_project_and_unlock(client)

        # Add a paper
        add_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "To Delete", "year": 2024}
        )
        paper_id = add_response.json()["id"]

        # Delete paper
        response = client.delete(
            f"/api/research/v3/{project_id}/process/literature-review/papers/{paper_id}"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify deletion
        list_response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/papers"
        )
        assert list_response.json()["total"] == 0

    def test_delete_paper_when_locked(self, client):
        """Test that deleting fails when Literature Review is locked."""
        # Create project (Literature Review starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Delete Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Try to delete - should fail
        response = client.delete(
            f"/api/research/v3/{project_id}/process/literature-review/papers/some_id"
        )

        assert response.status_code == 403


class TestPaperProcessing:
    """Tests for paper processing endpoints."""

    def test_process_paper(self, client):
        """Test processing a paper (PDF→MD)."""
        project_id = create_project_and_unlock(client)

        # Add a paper
        add_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "To Process", "year": 2024}
        )
        paper_id = add_response.json()["id"]

        # Process paper
        response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/process/{paper_id}"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["paper_id"] == paper_id
        assert data["status"] == "completed"

    def test_process_paper_not_found(self, client):
        """Test processing non-existent paper."""
        project_id = create_project_and_unlock(client)

        response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/process/nonexistent"
        )

        assert response.status_code == 404


class TestMasterMD:
    """Tests for master MD generation."""

    def test_get_master_md_empty(self, client):
        """Test getting master MD with no papers."""
        project_id = create_project_and_unlock(client)

        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/master"
        )

        assert response.status_code == 200
        data = response.json()

        assert "content" in data
        assert "Literature Reference List" in data["content"]
        assert data["total_papers"] == 0

    def test_get_master_md_with_papers(self, client):
        """Test getting master MD with papers."""
        project_id = create_project_and_unlock(client)

        # Add some papers
        client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Paper 1", "authors": ["Author A"], "year": 2023}
        )
        client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Paper 2", "authors": ["Author B"], "year": 2024}
        )

        response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/master"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_papers"] == 2
        assert "Paper 1" in data["content"] or "Paper" in data["content"]


class TestSearchPapers:
    """Tests for paper search endpoint."""

    def test_search_when_locked(self, client):
        """Test that search fails when Literature Review is locked."""
        # Create project (Literature Review starts locked)
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Search Locked Test"}
        )
        project_id = response.json()["project_id"]

        # Try to search - should fail
        response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/search",
            json={"query": "test query"}
        )

        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()


class TestAccessControl:
    """Tests for access control based on lock status."""

    def test_operations_blocked_when_locked(self, client):
        """Test that all operations are blocked when locked."""
        response = client.post(
            "/api/research/v3/create",
            json={"topic": "Access Control Test"}
        )
        project_id = response.json()["project_id"]

        # Search - blocked
        search_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/search",
            json={"query": "test"}
        )
        assert search_response.status_code == 403

        # Add paper - blocked
        add_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Test"}
        )
        assert add_response.status_code == 403

        # Delete paper - blocked
        delete_response = client.delete(
            f"/api/research/v3/{project_id}/process/literature-review/papers/test"
        )
        assert delete_response.status_code == 403

        # Process paper - blocked
        process_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/process/test"
        )
        assert process_response.status_code == 403

    def test_operations_allowed_when_unlocked(self, client):
        """Test that operations work when unlocked."""
        project_id = create_project_and_unlock(client)

        # Add paper - allowed
        add_response = client.post(
            f"/api/research/v3/{project_id}/process/literature-review/papers",
            json={"title": "Test Paper"}
        )
        assert add_response.status_code == 200

        # Get state - allowed (even when locked, read is ok)
        state_response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review"
        )
        assert state_response.status_code == 200

        # Master MD - allowed
        master_response = client.get(
            f"/api/research/v3/{project_id}/process/literature-review/master"
        )
        assert master_response.status_code == 200
