"""Unit tests for v3 state schema and project store."""

import pytest
from datetime import datetime

from backend.orchestrator.state import (
    ProjectState,
    ProjectProcesses,
    ResearchExperimentProcess,
    ResearchExperimentState,
    LiteratureReviewProcess,
    LiteratureReviewState,
    PaperWritingProcess,
    PaperWritingState,
    ProcessStatus,
    ProcessPhase,
    PaperEntry,
    PaperType,
    PaperSource,
    PaperStatus,
    SearchHistoryEntry,
)
from backend.storage.project_store import (
    is_legacy_project,
    migrate_legacy_project,
    project_to_dict,
    dict_to_project,
    create_project,
)


class TestProcessStatus:
    """Tests for ProcessStatus enum."""

    def test_locked_value(self):
        assert ProcessStatus.LOCKED.value == "locked"

    def test_unlocked_value(self):
        assert ProcessStatus.UNLOCKED.value == "unlocked"


class TestProcessPhase:
    """Tests for ProcessPhase enum."""

    def test_research_definition_value(self):
        assert ProcessPhase.RESEARCH_DEFINITION.value == "research_definition"

    def test_experiment_design_value(self):
        assert ProcessPhase.EXPERIMENT_DESIGN.value == "experiment_design"


class TestProjectState:
    """Tests for ProjectState model."""

    def test_create_default_project(self):
        """Test creating a project with default values."""
        project = ProjectState(id="test-123", topic="Test Topic")

        assert project.id == "test-123"
        assert project.topic == "Test Topic"
        assert project.research_definition_complete is False
        assert project.experiment_design_complete is False
        assert project.processes.research_experiment.status == "active"
        assert project.processes.literature_review.status == ProcessStatus.LOCKED
        assert project.processes.paper_writing.status == ProcessStatus.LOCKED

    def test_complete_research_definition(self):
        """Test marking Research Definition as complete."""
        project = ProjectState(id="test-123", topic="Test Topic")

        # Initially locked
        assert project.research_definition_complete is False
        assert project.processes.literature_review.status == ProcessStatus.LOCKED

        # Complete Research Definition
        project.complete_research_definition()

        # Now unlocked
        assert project.research_definition_complete is True
        assert project.processes.literature_review.status == ProcessStatus.UNLOCKED

    def test_complete_research_definition_is_one_way(self):
        """Test that completion cannot be undone."""
        project = ProjectState(id="test-123", topic="Test Topic")

        # Complete it
        project.complete_research_definition()
        assert project.research_definition_complete is True

        # Try to set it back to False directly
        project.research_definition_complete = False

        # Call complete again - should set it back to True
        project.complete_research_definition()
        assert project.research_definition_complete is True

    def test_complete_experiment_design(self):
        """Test marking Experiment Design as complete."""
        project = ProjectState(id="test-123", topic="Test Topic")

        # Initially locked
        assert project.experiment_design_complete is False
        assert project.processes.paper_writing.status == ProcessStatus.LOCKED

        # Complete Experiment Design
        project.complete_experiment_design()

        # Now unlocked
        assert project.experiment_design_complete is True
        assert project.processes.paper_writing.status == ProcessStatus.UNLOCKED

    def test_switch_phase(self):
        """Test switching phases within Research & Experiment."""
        project = ProjectState(id="test-123", topic="Test Topic")

        # Default phase
        assert project.processes.research_experiment.current_phase == ProcessPhase.RESEARCH_DEFINITION

        # Switch to Experiment Design
        project.switch_phase(ProcessPhase.EXPERIMENT_DESIGN)
        assert project.processes.research_experiment.current_phase == ProcessPhase.EXPERIMENT_DESIGN

        # Switch back to Research Definition
        project.switch_phase(ProcessPhase.RESEARCH_DEFINITION)
        assert project.processes.research_experiment.current_phase == ProcessPhase.RESEARCH_DEFINITION

    def test_is_literature_review_accessible(self):
        """Test Literature Review accessibility check."""
        project = ProjectState(id="test-123", topic="Test Topic")

        assert project.is_literature_review_accessible() is False

        project.complete_research_definition()

        assert project.is_literature_review_accessible() is True

    def test_is_paper_writing_accessible(self):
        """Test Paper Writing accessibility check."""
        project = ProjectState(id="test-123", topic="Test Topic")

        assert project.is_paper_writing_accessible() is False

        project.complete_experiment_design()

        assert project.is_paper_writing_accessible() is True


class TestPaperEntry:
    """Tests for PaperEntry model."""

    def test_create_search_paper(self):
        """Test creating a paper from search."""
        paper = PaperEntry(
            id="paper_001",
            type=PaperType.SEARCH,
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            year=2024,
            source=PaperSource.ARXIV,
        )

        assert paper.id == "paper_001"
        assert paper.type == PaperType.SEARCH
        assert paper.source == PaperSource.ARXIV
        assert paper.status == PaperStatus.PENDING

    def test_create_upload_paper(self):
        """Test creating a paper from upload."""
        paper = PaperEntry(
            id="uploaded_001",
            type=PaperType.UPLOAD,
            title="Uploaded Paper",
        )

        assert paper.id == "uploaded_001"
        assert paper.type == PaperType.UPLOAD
        assert paper.source == PaperSource.UPLOAD


class TestMigration:
    """Tests for legacy project migration."""

    def test_is_legacy_project_true(self):
        """Test detecting legacy project."""
        legacy = {
            "id": "test-123",
            "topic": "Test",
            "current_phase": "phase_1",
            "messages": [],
        }
        assert is_legacy_project(legacy) is True

    def test_is_legacy_project_false(self):
        """Test detecting v3 project."""
        v3 = {
            "id": "test-123",
            "topic": "Test",
            "processes": {},
        }
        assert is_legacy_project(v3) is False

    def test_migrate_phase_1(self):
        """Test migrating phase_1 project."""
        legacy = {
            "id": "test-123",
            "topic": "Test Topic",
            "current_phase": "phase_1",
            "messages": [{"role": "user", "content": "test"}],
            "state": {
                "research_topic": "Test Topic",
                "research_questions": ["Q1", "Q2"],
            },
        }

        migrated = migrate_legacy_project(legacy)

        assert migrated["id"] == "test-123"
        assert migrated["research_definition_complete"] is False
        assert migrated["experiment_design_complete"] is False
        assert migrated["processes"]["research_experiment"]["current_phase"] == "research_definition"
        assert migrated["processes"]["literature_review"]["status"] == "locked"
        assert migrated["processes"]["paper_writing"]["status"] == "locked"
        assert len(migrated["processes"]["research_experiment"]["messages"]) == 1

    def test_migrate_phase_2(self):
        """Test migrating phase_2 project."""
        legacy = {
            "id": "test-123",
            "topic": "Test Topic",
            "current_phase": "phase_2",
            "messages": [],
            "state": {},
        }

        migrated = migrate_legacy_project(legacy)

        assert migrated["research_definition_complete"] is True
        assert migrated["experiment_design_complete"] is False
        assert migrated["processes"]["literature_review"]["status"] == "unlocked"
        assert migrated["processes"]["paper_writing"]["status"] == "locked"

    def test_migrate_phase_3(self):
        """Test migrating phase_3 project."""
        legacy = {
            "id": "test-123",
            "topic": "Test Topic",
            "current_phase": "phase_3",
            "messages": [],
            "state": {},
        }

        migrated = migrate_legacy_project(legacy)

        assert migrated["research_definition_complete"] is True
        assert migrated["experiment_design_complete"] is False
        assert migrated["processes"]["research_experiment"]["current_phase"] == "experiment_design"
        assert migrated["processes"]["literature_review"]["status"] == "unlocked"

    def test_migrate_phase_4(self):
        """Test migrating phase_4 project."""
        legacy = {
            "id": "test-123",
            "topic": "Test Topic",
            "current_phase": "phase_4",
            "messages": [],
            "state": {
                "imrad_structure": {"intro": "test"},
            },
        }

        migrated = migrate_legacy_project(legacy)

        assert migrated["research_definition_complete"] is True
        assert migrated["experiment_design_complete"] is True
        assert migrated["processes"]["literature_review"]["status"] == "unlocked"
        assert migrated["processes"]["paper_writing"]["status"] == "unlocked"
        assert migrated["processes"]["paper_writing"]["state"]["imrad_structure"] == {"intro": "test"}


class TestSerialization:
    """Tests for project serialization/deserialization."""

    def test_project_to_dict(self):
        """Test converting ProjectState to dict."""
        project = ProjectState(
            id="test-123",
            topic="Test Topic",
        )
        project.complete_research_definition()

        data = project_to_dict(project)

        assert data["id"] == "test-123"
        assert data["topic"] == "Test Topic"
        assert data["research_definition_complete"] is True
        assert data["processes"]["literature_review"]["status"] == "unlocked"

    def test_dict_to_project(self):
        """Test converting dict to ProjectState."""
        data = {
            "id": "test-123",
            "topic": "Test Topic",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "research_definition_complete": True,
            "experiment_design_complete": False,
            "processes": {
                "research_experiment": {
                    "status": "active",
                    "current_phase": "experiment_design",
                    "messages": [],
                    "artifact": "",
                    "state": {},
                },
                "literature_review": {
                    "status": "unlocked",
                    "papers_folder": "papers/test-123/",
                    "state": {},
                },
                "paper_writing": {
                    "status": "locked",
                    "messages": [],
                    "artifact": "",
                    "state": {},
                },
            },
        }

        project = dict_to_project(data)

        assert project.id == "test-123"
        assert project.research_definition_complete is True
        assert project.processes.research_experiment.current_phase == ProcessPhase.EXPERIMENT_DESIGN
        assert project.processes.literature_review.status == ProcessStatus.UNLOCKED
        assert project.processes.paper_writing.status == ProcessStatus.LOCKED

    def test_roundtrip_serialization(self):
        """Test that project survives serialization roundtrip."""
        # Create project
        project = ProjectState(id="test-123", topic="Test Topic")
        project.complete_research_definition()
        project.switch_phase(ProcessPhase.EXPERIMENT_DESIGN)
        project.processes.research_experiment.messages.append(
            {"role": "user", "content": "test message"}
        )

        # Convert to dict and back
        data = project_to_dict(project)
        restored = dict_to_project(data)

        # Verify
        assert restored.id == project.id
        assert restored.topic == project.topic
        assert restored.research_definition_complete == project.research_definition_complete
        assert restored.processes.research_experiment.current_phase == project.processes.research_experiment.current_phase
        assert len(restored.processes.research_experiment.messages) == 1


class TestCreateProject:
    """Tests for project creation."""

    def test_create_project(self, tmp_path, monkeypatch):
        """Test creating a new project."""
        # Mock data directories
        from backend.storage import project_store
        monkeypatch.setattr(project_store, "DATA_DIR", tmp_path / "projects")
        monkeypatch.setattr(project_store, "PAPERS_DIR", tmp_path / "papers")

        project = create_project("test-123", "Test Topic")

        assert project.id == "test-123"
        assert project.topic == "Test Topic"
        assert project.research_definition_complete is False
        assert project.processes.research_experiment.state.research_topic == "Test Topic"
        assert project.processes.literature_review.papers_folder == "papers/test-123/"

        # Verify file was created
        assert (tmp_path / "projects" / "test-123.json").exists()

        # Verify papers folder was created
        assert (tmp_path / "papers" / "test-123").exists()
