"""State schema for research orchestration workflow.

v3: Process-based parallel architecture with unlock triggers.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# === Enums ===

class ProcessStatus(str, Enum):
    """Status for processes that can be locked/unlocked."""
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class ProcessPhase(str, Enum):
    """Phases within Research & Experiment process."""
    RESEARCH_DEFINITION = "research_definition"
    EXPERIMENT_DESIGN = "experiment_design"


class PaperStatus(str, Enum):
    """Status for paper processing in Literature Review."""
    PENDING = "pending"
    PENDING_DOWNLOAD = "pending_download"  # PDF 다운로드 대기/진행 중
    DOWNLOADING = "downloading"  # PDF 다운로드 중
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaperType(str, Enum):
    """Type of paper in Literature Review."""
    SEARCH = "search"
    UPLOAD = "upload"


class PaperSource(str, Enum):
    """Source of searched paper."""
    ARXIV = "arXiv"
    SEMANTIC_SCHOLAR = "S2"
    GOOGLE_SCHOLAR = "GS"
    UPLOAD = "upload"


# === Helper Functions ===

def merge_lists(left: list, right: list) -> list:
    """Merge two lists by concatenation."""
    return left + right


def update_dict(left: dict, right: dict) -> dict:
    """Update dict with new values."""
    result = left.copy()
    result.update(right)
    return result


# === Research & Experiment Process State ===

class ResearchExperimentState(BaseModel):
    """State for Research & Experiment process.

    Contains data from both Research Definition and Experiment Design phases.
    """
    # Research Definition
    research_topic: str = Field(default="", description="Initial research topic from user")
    refined_topic: str = Field(default="", description="Refined research topic")
    research_questions: list[str] = Field(
        default_factory=list,
        description="Specific research questions"
    )
    novelty_assessment: dict = Field(
        default_factory=dict,
        description="Novelty evaluation results"
    )
    research_scope: dict = Field(
        default_factory=dict,
        description="Defined research scope"
    )
    potential_contributions: list[str] = Field(
        default_factory=list,
        description="Expected contributions"
    )
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for literature search"
    )

    # Experiment Design
    experiment_design: dict = Field(
        default_factory=dict,
        description="Experiment design details"
    )
    variables: dict = Field(
        default_factory=dict,
        description="Variable definitions (independent, dependent, control)"
    )
    hypotheses: list[dict] = Field(
        default_factory=list,
        description="Research hypotheses"
    )
    methodology: dict = Field(
        default_factory=dict,
        description="Methodology details"
    )


class ResearchExperimentProcess(BaseModel):
    """Research & Experiment process container."""
    status: str = Field(default="active", description="Always active (never locked)")
    current_phase: ProcessPhase = Field(
        default=ProcessPhase.RESEARCH_DEFINITION,
        description="Current phase within this process"
    )
    messages: list[dict] = Field(
        default_factory=list,
        description="Chat message history"
    )
    # Separate artifacts for each phase
    research_definition_artifact: str = Field(
        default="",
        description="Research Definition document (markdown)"
    )
    experiment_design_artifact: str = Field(
        default="",
        description="Experiment Design document (markdown)"
    )
    # Legacy field for backwards compatibility
    artifact: str = Field(
        default="",
        description="Deprecated: Use research_definition_artifact or experiment_design_artifact"
    )
    state: ResearchExperimentState = Field(
        default_factory=ResearchExperimentState,
        description="Process-specific state"
    )

    def get_current_artifact(self) -> str:
        """Get the artifact for the current phase."""
        if self.current_phase == ProcessPhase.RESEARCH_DEFINITION:
            return self.research_definition_artifact or self.artifact
        else:
            return self.experiment_design_artifact

    def set_current_artifact(self, content: str) -> None:
        """Set the artifact for the current phase."""
        if self.current_phase == ProcessPhase.RESEARCH_DEFINITION:
            self.research_definition_artifact = content
        else:
            self.experiment_design_artifact = content


# === Literature Organization Process State (Always Unlocked) ===

class PaperEntry(BaseModel):
    """Entry for a paper in Literature Organization."""
    id: str = Field(description="Unique paper ID (e.g., paper_001)")
    type: PaperType = Field(description="search or upload")
    title: str = Field(default="", description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author list")
    year: Optional[int] = Field(default=None, description="Publication year")
    source: PaperSource = Field(default=PaperSource.UPLOAD, description="Paper source")
    pdf_url: Optional[str] = Field(default=None, description="PDF URL if available")
    doi: Optional[str] = Field(default=None, description="DOI if available")
    url: Optional[str] = Field(default=None, description="Paper URL (e.g., arXiv page)")
    venue: Optional[str] = Field(default=None, description="Publication venue/journal")
    citations: int = Field(default=0, description="Citation count")
    categories: list[str] = Field(default_factory=list, description="Paper categories/fields")
    abstract: str = Field(default="", description="Paper abstract")
    full_text: Optional[str] = Field(default=None, description="Full paper text for summarization")
    md_file: str = Field(default="", description="Generated MD filename")
    md_content: str = Field(default="", description="Generated MD content (full summary)")
    status: PaperStatus = Field(default=PaperStatus.PENDING, description="Processing status")
    added_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When this paper was added"
    )


class LiteratureOrganizationState(BaseModel):
    """State for Literature Organization process (PDF → MD conversion).

    Always unlocked from project creation.
    """
    papers: list[PaperEntry] = Field(
        default_factory=list,
        description="List of uploaded papers"
    )
    master_md: str = Field(
        default="master.md",
        description="Master reference list filename"
    )


class LiteratureOrganizationProcess(BaseModel):
    """Literature Organization process container (non-conversational).

    Always unlocked - handles PDF upload and MD conversion.
    """
    status: ProcessStatus = Field(
        default=ProcessStatus.UNLOCKED,  # Always unlocked!
        description="Always unlocked from project creation"
    )
    papers_folder: str = Field(
        default="",
        description="Folder path for paper MD files"
    )
    state: LiteratureOrganizationState = Field(
        default_factory=LiteratureOrganizationState,
        description="Process-specific state"
    )
    # No messages - this is non-conversational


# === Literature Search Process State (Locked until RD+ED complete) ===

class SearchHistoryEntry(BaseModel):
    """Entry for search history in Literature Search."""
    query: str = Field(description="Search query")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When search was performed"
    )
    result_count: int = Field(default=0, description="Number of results found")
    sources: list[str] = Field(
        default_factory=list,
        description="Sources searched (arXiv, S2, GS)"
    )


class LiteratureSearchState(BaseModel):
    """State for Literature Search process (web search).

    Locked until both research_definition_complete AND experiment_design_complete.
    """
    search_history: list[SearchHistoryEntry] = Field(
        default_factory=list,
        description="History of searches performed"
    )
    searched_papers: list[PaperEntry] = Field(
        default_factory=list,
        description="List of papers found via search"
    )


class LiteratureSearchProcess(BaseModel):
    """Literature Search process container (non-conversational).

    Locked until both RD and ED are complete.
    """
    status: ProcessStatus = Field(
        default=ProcessStatus.LOCKED,
        description="Locked until both research_definition_complete AND experiment_design_complete"
    )
    state: LiteratureSearchState = Field(
        default_factory=LiteratureSearchState,
        description="Process-specific state"
    )
    # No messages - this is non-conversational


# === Legacy: Literature Review (for backwards compatibility) ===

class LiteratureReviewState(BaseModel):
    """Legacy state for Literature Review process.

    Deprecated: Use LiteratureOrganizationState and LiteratureSearchState instead.
    """
    search_history: list[SearchHistoryEntry] = Field(
        default_factory=list,
        description="History of searches performed"
    )
    papers: list[PaperEntry] = Field(
        default_factory=list,
        description="List of papers (searched + uploaded)"
    )
    master_md: str = Field(
        default="master.md",
        description="Master reference list filename"
    )


class LiteratureReviewProcess(BaseModel):
    """Legacy Literature Review process container.

    Deprecated: Use LiteratureOrganizationProcess and LiteratureSearchProcess instead.
    """
    status: ProcessStatus = Field(
        default=ProcessStatus.LOCKED,
        description="locked until research_definition_complete"
    )
    papers_folder: str = Field(
        default="",
        description="Folder path for paper MD files"
    )
    state: LiteratureReviewState = Field(
        default_factory=LiteratureReviewState,
        description="Process-specific state"
    )
    # No messages - this is non-conversational


# === Paper Writing Process State ===

class PaperWritingState(BaseModel):
    """State for Paper Writing process."""
    imrad_structure: dict = Field(
        default_factory=dict,
        description="IMRAD paper structure outline"
    )
    draft_sections: dict = Field(
        default_factory=dict,
        description="Draft content by section (intro, methods, results, discussion)"
    )
    target_journal: str = Field(
        default="",
        description="Target journal for submission"
    )
    journal_guidelines: dict = Field(
        default_factory=dict,
        description="Journal formatting guidelines"
    )
    final_paper: str = Field(
        default="",
        description="Final formatted paper content"
    )
    cover_letter: str = Field(
        default="",
        description="Cover letter for submission"
    )


class PaperWritingProcess(BaseModel):
    """Paper Writing process container."""
    status: ProcessStatus = Field(
        default=ProcessStatus.LOCKED,
        description="locked until experiment_design_complete"
    )
    messages: list[dict] = Field(
        default_factory=list,
        description="Chat message history"
    )
    artifact: str = Field(
        default="",
        description="Current artifact content (markdown)"
    )
    state: PaperWritingState = Field(
        default_factory=PaperWritingState,
        description="Process-specific state"
    )


# === Project Processes Container ===

class ProjectProcesses(BaseModel):
    """Container for all project processes.

    v3.1 Architecture (4 processes):
    - Research & Experiment: Always accessible
    - Literature Organization: Always accessible (PDF → MD)
    - Literature Search: Locked until RD + ED complete (Web search)
    - Paper Writing: Locked until RD + ED complete
    """
    research_experiment: ResearchExperimentProcess = Field(
        default_factory=ResearchExperimentProcess,
        description="Research & Experiment process"
    )
    literature_organization: LiteratureOrganizationProcess = Field(
        default_factory=LiteratureOrganizationProcess,
        description="Literature Organization process (always unlocked)"
    )
    literature_search: LiteratureSearchProcess = Field(
        default_factory=LiteratureSearchProcess,
        description="Literature Search process (locked until RD+ED complete)"
    )
    paper_writing: PaperWritingProcess = Field(
        default_factory=PaperWritingProcess,
        description="Paper Writing process"
    )

    # Legacy field for backwards compatibility
    literature_review: Optional[LiteratureReviewProcess] = Field(
        default=None,
        description="Deprecated: Use literature_organization and literature_search"
    )


# === Main Project State ===

class ProjectState(BaseModel):
    """Complete project state with parallel processes.

    v3.1 Architecture (4 processes):
    - Research & Experiment: Always accessible, contains Research Definition + Experiment Design
    - Literature Organization: Always accessible (PDF → MD conversion)
    - Literature Search: Unlocked when BOTH research_definition_complete AND experiment_design_complete = True
    - Paper Writing: Unlocked when BOTH research_definition_complete AND experiment_design_complete = True

    Key Principles:
    1. Research Definition is always editable even after completion
    2. Unlock triggers are one-way (false → true only)
    3. Processes are independent - modifying upstream doesn't affect downstream
    4. Literature Organization is always accessible from project creation
    """
    id: str = Field(description="Unique project ID")
    topic: str = Field(description="Project topic/title")
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Creation timestamp"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp"
    )

    # Unlock triggers (one-way: false → true, never back to false)
    research_definition_complete: bool = Field(
        default=False,
        description="Contributes to Literature Search and Paper Writing unlock"
    )
    experiment_design_complete: bool = Field(
        default=False,
        description="Contributes to Literature Search and Paper Writing unlock"
    )

    # Process containers
    processes: ProjectProcesses = Field(
        default_factory=ProjectProcesses,
        description="All process states"
    )

    class Config:
        arbitrary_types_allowed = True

    def complete_research_definition(self) -> None:
        """Mark Research Definition as complete (one-way).

        Unlocks Literature Search and Paper Writing if Experiment Design is also complete.
        """
        if not self.research_definition_complete:
            self.research_definition_complete = True
            # Unlock Literature Search and Paper Writing if Experiment Design is already complete
            if self.experiment_design_complete:
                self.processes.literature_search.status = ProcessStatus.UNLOCKED
                self.processes.paper_writing.status = ProcessStatus.UNLOCKED
            self.updated_at = datetime.utcnow().isoformat()

    def complete_experiment_design(self) -> None:
        """Mark Experiment Design as complete (one-way).

        Unlocks Literature Search and Paper Writing if Research Definition is also complete.
        """
        if not self.experiment_design_complete:
            self.experiment_design_complete = True
            # Unlock Literature Search and Paper Writing if Research Definition is also complete
            if self.research_definition_complete:
                self.processes.literature_search.status = ProcessStatus.UNLOCKED
                self.processes.paper_writing.status = ProcessStatus.UNLOCKED
            self.updated_at = datetime.utcnow().isoformat()

    def switch_phase(self, phase: ProcessPhase) -> None:
        """Switch current phase within Research & Experiment."""
        self.processes.research_experiment.current_phase = phase
        self.updated_at = datetime.utcnow().isoformat()

    def is_literature_organization_accessible(self) -> bool:
        """Check if Literature Organization is accessible.

        Always returns True - this process is never locked.
        """
        return True

    def is_literature_search_accessible(self) -> bool:
        """Check if Literature Search is accessible.

        Requires BOTH research_definition_complete AND experiment_design_complete.
        """
        return self.research_definition_complete and self.experiment_design_complete

    def is_paper_writing_accessible(self) -> bool:
        """Check if Paper Writing is accessible.

        Requires BOTH research_definition_complete AND experiment_design_complete.
        """
        return self.research_definition_complete and self.experiment_design_complete

    # Legacy compatibility
    def is_literature_review_accessible(self) -> bool:
        """Legacy method - maps to is_literature_organization_accessible."""
        return self.is_literature_organization_accessible()


# === Legacy Support ===

class ResearchState(BaseModel):
    """Legacy state for backwards compatibility.

    This class is kept for reference during migration.
    New code should use ProjectState instead.
    """
    # Phase 1: Research Definition
    research_topic: str = Field(default="")
    refined_topic: str = Field(default="")
    research_questions: list[str] = Field(default_factory=list)
    novelty_assessment: dict = Field(default_factory=dict)
    research_scope: dict = Field(default_factory=dict)
    potential_contributions: list[str] = Field(default_factory=list)

    # Phase 2: Literature Review
    search_keywords: list[str] = Field(default_factory=list)
    found_papers: list[dict] = Field(default_factory=list)
    paper_summaries: list[dict] = Field(default_factory=list)
    literature_evaluation: dict = Field(default_factory=dict)
    research_gaps: list[dict] = Field(default_factory=list)
    research_trends: list[dict] = Field(default_factory=list)

    # Phase 3: Research Design
    experiment_design: dict = Field(default_factory=dict)
    variables: dict = Field(default_factory=dict)
    hypotheses: list[dict] = Field(default_factory=list)
    methodology: dict = Field(default_factory=dict)

    # Phase 4: Paper Writing
    imrad_structure: dict = Field(default_factory=dict)
    draft_sections: dict = Field(default_factory=dict)
    target_journal: str = Field(default="")
    journal_guidelines: dict = Field(default_factory=dict)
    final_paper: str = Field(default="")
    cover_letter: str = Field(default="")

    # Workflow Control
    current_phase: str = Field(default="init")
    messages: list[dict] = Field(default_factory=list)
    human_feedback: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# === Other Models (unchanged) ===

class PhaseResult(BaseModel):
    """Result from a workflow phase."""
    phase: str = Field(description="Phase name")
    status: str = Field(description="Status: success, needs_revision, failed")
    agent_name: str = Field(description="Agent that produced this result")
    output: Any = Field(description="Agent output")
    message: str = Field(default="", description="Status message")
    next_action: str = Field(default="continue", description="Next action to take")


class HumanReviewRequest(BaseModel):
    """Request for human review."""
    phase: str = Field(description="Current phase")
    content: dict = Field(description="Content to review")
    questions: list[str] = Field(default_factory=list, description="Questions for the reviewer")
    options: list[str] = Field(default_factory=list, description="Available options")


class WorkflowConfig(BaseModel):
    """Configuration for the workflow."""
    # Search settings
    year_start: int = Field(default=2023, description="Start year for literature search")
    year_end: int = Field(default=2026, description="End year for literature search")
    max_papers: int = Field(default=30, description="Maximum papers to retrieve")
    min_citations: int = Field(default=0, description="Minimum citation filter")

    # Agent settings (defaults loaded from settings if not specified)
    model: Optional[str] = Field(default=None, description="LLM model to use (defaults to settings.gemini_model)")
    temperature: Optional[float] = Field(default=None, description="LLM temperature (defaults to settings.gemini_temperature)")

    # Workflow settings
    require_human_approval: bool = Field(default=True, description="Require human approval between phases")
    max_iterations: int = Field(default=5, description="Maximum iterations per phase")

    # Output settings
    output_dir: str = Field(default="./output", description="Directory for output files")
    save_intermediate: bool = Field(default=True, description="Save intermediate results")
