"""Research project API routes.

v3: Process-based parallel architecture with Research & Experiment,
Literature Review, and Paper Writing as independent processes.
"""
import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, List
from uuid import uuid4

import structlog
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from backend.agents.research_discussion import ResearchDiscussionAgent
from backend.agents.paper_writing import PaperWritingAgent
from backend.agents.literature_searcher import LiteratureSearcherAgent
from backend.utils.prompt_loader import (
    load_pw_initial_artifact,
    load_rd_initial_artifact,
    load_ed_initial_artifact,
)
from backend.auth.token_manager import TokenManager
from backend.llm.gemini import GeminiLLM
from backend.storage.project_store import (
    save_project,
    load_all_projects,
    delete_project_file,
    create_project as create_project_v3_model,
    project_to_dict,
    dict_to_project,
)
from backend.orchestrator.state import (
    ProjectState,
    ProcessPhase,
    ProcessStatus,
)
from backend.storage.paper_files import (
    save_research_definition,
    save_experiment_design,
    save_paper_draft,
    read_research_definition,
    read_experiment_design,
    read_paper_draft,
    sanitize_filename,
    get_project_files_summary,
)

logger = structlog.get_logger(__name__)


def save_artifact_to_file(project_id: str, phase: str, content: str) -> None:
    """Save artifact content to the appropriate markdown file.

    Args:
        project_id: Project ID.
        phase: Phase name (research_definition, experiment_design, paper_writing).
        content: Markdown content to save.
    """
    if not content:
        return

    try:
        if phase == "research_definition":
            save_research_definition(project_id, content)
        elif phase == "experiment_design":
            save_experiment_design(project_id, content)
        elif phase == "paper_writing":
            save_paper_draft(project_id, content)
        else:
            logger.warning("Unknown phase for artifact save", phase=phase)
    except Exception as e:
        logger.error("Failed to save artifact to file", project_id=project_id, phase=phase, error=str(e))

router = APIRouter(prefix="/api/research", tags=["research"])

# In-memory storage for projects - 서버 시작 시 파일에서 로드 (v3 format)
_projects: dict[str, dict] = load_all_projects()
logger.info("Projects loaded from storage", count=len(_projects))
_running_workflows: dict[str, asyncio.Task] = {}

# Message queues for SSE streaming (project_id -> process -> asyncio.Queue)
# New structure for v3: separate queues per process
_message_queues: dict[str, asyncio.Queue] = {}  # Legacy: project-level
_process_queues: dict[str, dict[str, asyncio.Queue]] = {}  # v3: process-level

# Research Discussion Agents per project
_discussion_agents: dict[str, ResearchDiscussionAgent] = {}

# Paper Writing Agents per project
_paper_writing_agents: dict[str, PaperWritingAgent] = {}


class CreateProjectRequest(BaseModel):
    """Request to create a new research project."""

    topic: str = Field(description="Research topic")
    target_journal: str = Field(default="", description="Target journal (optional)")


class ProjectResponse(BaseModel):
    """Response with project details."""

    project_id: str
    topic: str
    status: str
    current_phase: str
    created_at: str


class ProjectStatusResponse(BaseModel):
    """Detailed project status response."""

    project_id: str
    topic: str
    status: str
    current_phase: str
    state: dict
    messages: list[dict]
    research_artifact: str = ""  # Phase 1 연구 정의 아티팩트


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""

    content: str = Field(description="Message content")
    model: str | None = Field(default=None, description="Optional model override (e.g., gemini-3-pro-preview)")


# =============================================================================
# v3 API MODELS
# =============================================================================

class ProjectStatusResponseV3(BaseModel):
    """v3 project status response with process states."""

    project_id: str
    topic: str
    created_at: str
    updated_at: str
    research_definition_complete: bool
    experiment_design_complete: bool
    processes: dict


class ResearchExperimentStateResponse(BaseModel):
    """Response for Research & Experiment process state."""

    status: str
    current_phase: str
    messages: list[dict]
    artifact: str
    state: dict


class SwitchPhaseRequest(BaseModel):
    """Request to switch phase within Research & Experiment."""

    phase: str = Field(description="Target phase: research_definition or experiment_design")


class CompletePhaseResponse(BaseModel):
    """Response after completing a phase."""

    success: bool
    message: str
    unlocked_process: str | None = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_message_queue(project_id: str) -> asyncio.Queue:
    """Get or create message queue for a project."""
    if project_id not in _message_queues:
        _message_queues[project_id] = asyncio.Queue()
    return _message_queues[project_id]


def get_process_queue(project_id: str, process: str) -> asyncio.Queue:
    """Get or create message queue for a specific process (v3)."""
    if project_id not in _process_queues:
        _process_queues[project_id] = {}
    if process not in _process_queues[project_id]:
        _process_queues[project_id][process] = asyncio.Queue()
    return _process_queues[project_id][process]


def get_project_v3(project_id: str) -> ProjectState | None:
    """Get project as v3 ProjectState model."""
    if project_id not in _projects:
        return None
    project_data = _projects[project_id]
    # If already a ProjectState, return it directly
    if isinstance(project_data, ProjectState):
        return project_data
    # Otherwise convert from dict
    return dict_to_project(project_data)


def save_project_v3(project: ProjectState) -> None:
    """Save v3 project to storage."""
    project_dict = project_to_dict(project)
    _projects[project.id] = project_dict
    save_project(project_dict)


async def emit_process_message(
    project_id: str,
    process: str,
    agent: str,
    content: str,
    msg_type: str = "message"
) -> None:
    """Emit a message to a specific process's SSE stream (v3)."""
    print(f"[EMIT-v3] emit_process_message: process={process}, agent={agent}", flush=True)

    queue = get_process_queue(project_id, process)

    message = {
        "type": msg_type,
        "agent": agent,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Add to project's process messages
    project = get_project_v3(project_id)
    if project:
        if process == "research_experiment":
            project.processes.research_experiment.messages.append(message)
        elif process == "paper_writing":
            project.processes.paper_writing.messages.append(message)
        save_project_v3(project)
        # Update in-memory cache
        _projects[project_id] = project_to_dict(project)

    # Put in queue for SSE
    await queue.put(message)
    print(f"[EMIT-v3] Message put in process queue: {process}", flush=True)


async def emit_message(project_id: str, agent: str, content: str, msg_type: str = "message") -> None:
    """Emit a message to the project's SSE stream."""
    print(f"[EMIT] emit_message called: agent={agent}, project={project_id[:8]}", flush=True)

    if project_id not in _message_queues:
        print(f"[EMIT] Creating new queue for project", flush=True)
        get_message_queue(project_id)

    message = {
        "type": msg_type,
        "agent": agent,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Add to project messages
    if project_id in _projects:
        _projects[project_id]["messages"].append(message)
        print(f"[EMIT] Message added to project messages list", flush=True)
        # 파일에 자동 저장
        save_project(_projects[project_id])

    # Put in queue for SSE
    queue_size_before = _message_queues[project_id].qsize()
    await _message_queues[project_id].put(message)
    queue_size_after = _message_queues[project_id].qsize()
    print(f"[EMIT] Message put in queue: before={queue_size_before}, after={queue_size_after}", flush=True)

    logger.info("SSE message emitted",
               project_id=project_id[:8],
               agent=agent,
               msg_type=msg_type,
               content_length=len(content),
               queue_size_before=queue_size_before)


def get_discussion_agent(project_id: str, model: str | None = None) -> ResearchDiscussionAgent:
    """Get or create discussion agent for a project.

    Args:
        project_id: Project ID.
        model: Optional model override. If provided and agent exists with different model,
               the agent will be recreated with the new model.
    """
    # Check if we need to recreate the agent with a different model
    if project_id in _discussion_agents:
        existing_agent = _discussion_agents[project_id]
        # If model is specified and different from current, recreate
        if model and hasattr(existing_agent, 'llm') and existing_agent.llm.model != model:
            logger.info("Recreating agent with new model",
                       project_id=project_id[:8],
                       old_model=existing_agent.llm.model,
                       new_model=model)
            # Preserve the artifact and topic
            old_artifact = existing_agent.get_artifact()
            old_topic = existing_agent.topic
            # Create new agent with specified model
            new_agent = ResearchDiscussionAgent(model=model)
            if old_artifact:
                new_agent.set_artifact(old_artifact)
            if old_topic:
                new_agent.topic = old_topic
            _discussion_agents[project_id] = new_agent
            return new_agent

    if project_id not in _discussion_agents:
        # Create new agent with optional model
        agent = ResearchDiscussionAgent(model=model) if model else ResearchDiscussionAgent()
        _discussion_agents[project_id] = agent

        # Restore artifact and phase from project state based on current phase
        project = get_project_v3(project_id)
        if project:
            current_phase = project.processes.research_experiment.current_phase

            # Set agent phase to match project phase
            if current_phase == ProcessPhase.RESEARCH_DEFINITION:
                agent.set_phase(ResearchDiscussionAgent.PHASE_RESEARCH_DEFINITION)
                saved_artifact = project.processes.research_experiment.research_definition_artifact
            else:
                agent.set_phase(ResearchDiscussionAgent.PHASE_EXPERIMENT_DESIGN)
                saved_artifact = project.processes.research_experiment.experiment_design_artifact

            if saved_artifact:
                agent.set_artifact(saved_artifact)
                logger.info("Restored artifact from project state",
                           project_id=project_id[:8],
                           phase=current_phase.value)
            elif current_phase == ProcessPhase.EXPERIMENT_DESIGN:
                # Use experiment design initial artifact if no saved artifact exists
                agent.set_artifact(agent.INITIAL_EXPERIMENT_ARTIFACT)
                logger.info("Using initial experiment artifact",
                           project_id=project_id[:8])

            # Set topic from project
            if project.topic:
                agent.topic = project.topic
        # Fallback to legacy project structure
        elif project_id in _projects:
            legacy_project = _projects[project_id]
            saved_artifact = legacy_project.get("state", {}).get("research_artifact")
            if saved_artifact:
                agent.set_artifact(saved_artifact)
                logger.info("Restored artifact from legacy project state", project_id=project_id[:8])

    return _discussion_agents[project_id]


def get_paper_writing_agent(project_id: str, model: str | None = None) -> PaperWritingAgent:
    """Get or create Paper Writing agent for a project.

    Args:
        project_id: Project ID.
        model: Optional model override.

    Returns:
        PaperWritingAgent instance.
    """
    # Check if we need to recreate the agent with a different model
    if project_id in _paper_writing_agents:
        existing_agent = _paper_writing_agents[project_id]
        # If model is specified and different from current, recreate
        if model and hasattr(existing_agent, 'llm') and existing_agent.llm and existing_agent.llm.model != model:
            logger.info("Recreating paper writing agent with new model",
                       project_id=project_id[:8],
                       old_model=existing_agent.llm.model,
                       new_model=model)
            # Preserve the artifact and context
            old_artifact = existing_agent.get_artifact()
            old_history = existing_agent.conversation_history
            old_rd = existing_agent.research_definition
            old_ed = existing_agent.experiment_design
            # Create new agent with specified model
            new_agent = PaperWritingAgent(model=model)
            if old_artifact:
                new_agent.set_artifact(old_artifact)
            new_agent.conversation_history = old_history
            new_agent.research_definition = old_rd
            new_agent.experiment_design = old_ed
            _paper_writing_agents[project_id] = new_agent
            return new_agent

    if project_id not in _paper_writing_agents:
        # Create new agent with optional model
        agent = PaperWritingAgent(model=model) if model else PaperWritingAgent()
        _paper_writing_agents[project_id] = agent

        # Restore artifact from project state
        project = get_project_v3(project_id)
        if project:
            saved_artifact = project.processes.paper_writing.artifact
            if saved_artifact:
                agent.set_artifact(saved_artifact)
                logger.info("Restored paper writing artifact from project state",
                           project_id=project_id[:8],
                           artifact_length=len(saved_artifact))

            # Set research context
            rd_artifact = project.processes.research_experiment.research_definition_artifact
            ed_artifact = project.processes.research_experiment.experiment_design_artifact
            agent.set_context(rd_artifact or "", ed_artifact or "")

    return _paper_writing_agents[project_id]


# =============================================================================
# STATIC ROUTES (must come BEFORE dynamic /{project_id} routes)
# =============================================================================

@router.get("/")
async def list_projects() -> list[ProjectResponse]:
    """List all research projects."""
    return [
        ProjectResponse(
            project_id=p["id"],
            topic=p["topic"],
            status=p["status"],
            current_phase=p["current_phase"],
            created_at=p["created_at"],
        )
        for p in _projects.values()
    ]


@router.post("/create", response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest) -> ProjectResponse:
    """Create a new research project."""
    project_id = str(uuid4())

    _projects[project_id] = {
        "id": project_id,
        "topic": request.topic,
        "target_journal": request.target_journal,
        "status": "created",
        "current_phase": "init",
        "state": {},
        "messages": [],
        "created_at": datetime.utcnow().isoformat(),
    }

    # 파일에 저장
    save_project(_projects[project_id])

    logger.info("Project created", project_id=project_id, topic=request.topic[:50])

    return ProjectResponse(
        project_id=project_id,
        topic=request.topic,
        status="created",
        current_phase="init",
        created_at=_projects[project_id]["created_at"],
    )


@router.get("/debug/simple-test")
async def debug_simple_test() -> dict:
    """Simplest possible test endpoint."""
    print("[SIMPLE-TEST] This endpoint was called!", flush=True)
    return {"success": True, "message": "Simple test works!"}


@router.post("/debug/test-chat")
async def debug_test_chat() -> dict:
    """Debug endpoint to test chat flow without project."""
    import traceback
    try:
        print("[DEBUG-CHAT] Starting test...")

        from backend.agents.research_discussion import ResearchDiscussionAgent
        print("[DEBUG-CHAT] Imported agent")

        agent = ResearchDiscussionAgent()  # Uses settings.gemini_model
        print(f"[DEBUG-CHAT] Agent created, topic: '{agent.topic}'")

        print("[DEBUG-CHAT] Calling start_discussion...")
        response = await agent.start_discussion("Test topic")
        print(f"[DEBUG-CHAT] Got response: {len(response)} chars")

        return {
            "success": True,
            "response_length": len(response),
            "topic": agent.topic,
            "preview": response[:200]
        }
    except Exception as e:
        print(f"[DEBUG-CHAT] ERROR: {e}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


@router.get("/debug/test-llm")
async def debug_test_llm() -> dict:
    """Debug endpoint to test LLM connectivity directly."""
    import time
    start_time = time.time()

    try:
        from backend.llm.gemini import GeminiLLM

        logger.info("Debug: Creating LLM instance")
        llm = GeminiLLM()  # Uses settings.gemini_model

        logger.info("Debug: LLM created", project_id=llm.project_id)

        logger.info("Debug: Calling generate")
        response = await llm.generate(
            prompt="Say 'Hello' and nothing else.",
            max_tokens=50,
        )

        elapsed = time.time() - start_time
        logger.info("Debug: Got response", response=response[:100], elapsed=elapsed)

        return {
            "success": True,
            "response": response,
            "elapsed_seconds": elapsed,
            "project_id": llm.project_id,
        }

    except Exception as e:
        import traceback
        elapsed = time.time() - start_time
        logger.error("Debug: LLM test failed", error=str(e), traceback=traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": elapsed,
        }


@router.get("/debug/test-agent")
async def debug_test_agent() -> dict:
    """Debug endpoint to test Research Discussion Agent directly."""
    import time
    start_time = time.time()

    try:
        from backend.agents.research_discussion import ResearchDiscussionAgent

        logger.info("Debug: Creating agent")
        agent = ResearchDiscussionAgent()  # Uses settings.gemini_model

        logger.info("Debug: Starting discussion")
        response = await agent.start_discussion("Test research topic about AI")

        elapsed = time.time() - start_time
        logger.info("Debug: Got agent response", response_len=len(response), elapsed=elapsed)

        return {
            "success": True,
            "response": response[:500],
            "full_length": len(response),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        import traceback
        elapsed = time.time() - start_time
        logger.error("Debug: Agent test failed", error=str(e), traceback=traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": elapsed,
        }


# =============================================================================
# v3 API ROUTES - Process-based Architecture
# =============================================================================

@router.get("/v3")
@router.get("/v3/")
async def list_projects_v3() -> List[ProjectStatusResponseV3]:
    """List all v3 projects."""
    from backend.storage.project_store import load_all_projects

    # Load all projects from storage (returns dict[str, ProjectState])
    all_projects = load_all_projects()

    result = []
    for project_id, project in all_projects.items():
        try:
            result.append(ProjectStatusResponseV3(
                project_id=project.id,
                topic=project.topic,
                created_at=project.created_at,
                updated_at=project.updated_at,
                research_definition_complete=project.research_definition_complete,
                experiment_design_complete=project.experiment_design_complete,
                processes={
                    "research_experiment": {
                        "status": project.processes.research_experiment.status,
                        "current_phase": project.processes.research_experiment.current_phase.value,
                    },
                    "literature_organization": {
                        "status": project.processes.literature_organization.status.value,
                    },
                    "literature_search": {
                        "status": project.processes.literature_search.status.value,
                    },
                    "paper_writing": {
                        "status": project.processes.paper_writing.status.value,
                    },
                },
            ))
        except Exception as e:
            logger.warning("Failed to convert project to v3 format", project_id=project_id, error=str(e))
            continue

    return result


@router.post("/v3/create", response_model=ProjectStatusResponseV3)
async def create_project_v3(request: CreateProjectRequest) -> ProjectStatusResponseV3:
    """Create a new research project (v3 format with process architecture)."""
    # Generate unique project ID
    project_id = str(uuid4())

    # Use the v3 create_project function from project_store
    project = create_project_v3_model(project_id, request.topic)
    project_dict = project_to_dict(project)

    # Store in memory
    _projects[project.id] = project_dict

    # Save to file
    save_project(project_dict)

    logger.info("v3 Project created", project_id=project.id, topic=request.topic[:50])

    return ProjectStatusResponseV3(
        project_id=project.id,
        topic=project.topic,
        created_at=project.created_at,
        updated_at=project.updated_at,
        research_definition_complete=project.research_definition_complete,
        experiment_design_complete=project.experiment_design_complete,
        processes={
            "research_experiment": {
                "status": project.processes.research_experiment.status,
                "current_phase": project.processes.research_experiment.current_phase.value,
            },
            "literature_organization": {
                "status": project.processes.literature_organization.status.value,
            },
            "literature_search": {
                "status": project.processes.literature_search.status.value,
            },
            "paper_writing": {
                "status": project.processes.paper_writing.status.value,
            },
        },
    )


@router.get("/v3/{project_id}/status", response_model=ProjectStatusResponseV3)
async def get_project_status_v3(project_id: str) -> ProjectStatusResponseV3:
    """Get full project status (v3 format)."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectStatusResponseV3(
        project_id=project.id,
        topic=project.topic,
        created_at=project.created_at,
        updated_at=project.updated_at,
        research_definition_complete=project.research_definition_complete,
        experiment_design_complete=project.experiment_design_complete,
        processes={
            "research_experiment": {
                "status": project.processes.research_experiment.status,
                "current_phase": project.processes.research_experiment.current_phase.value,
                "messages_count": len(project.processes.research_experiment.messages),
                "has_artifact": bool(project.processes.research_experiment.get_current_artifact()),
            },
            "literature_organization": {
                "status": project.processes.literature_organization.status.value,
                "papers_count": len(project.processes.literature_organization.state.papers),
            },
            "literature_search": {
                "status": project.processes.literature_search.status.value,
                "searched_papers_count": len(project.processes.literature_search.state.searched_papers),
            },
            "paper_writing": {
                "status": project.processes.paper_writing.status.value,
                "messages_count": len(project.processes.paper_writing.messages),
                "has_artifact": bool(project.processes.paper_writing.artifact),
            },
        },
    )


class RenameProjectRequest(BaseModel):
    """Request to rename a project."""
    topic: str = Field(min_length=1, max_length=500, description="New project topic/name")


class RenameProjectResponse(BaseModel):
    """Response after renaming a project."""
    project_id: str
    topic: str
    message: str


@router.patch("/v3/{project_id}/rename", response_model=RenameProjectResponse)
async def rename_project(project_id: str, request: RenameProjectRequest) -> RenameProjectResponse:
    """Rename a project (change its topic).

    Args:
        project_id: Project ID.
        request: New topic/name for the project.

    Returns:
        Updated project info.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    old_topic = project.topic
    project.topic = request.topic.strip()

    # Also update research_topic in the research_experiment state
    project.processes.research_experiment.state.research_topic = project.topic

    save_project_v3(project)

    logger.info(
        "Project renamed",
        project_id=project_id[:8],
        old_topic=old_topic[:30] if old_topic else "",
        new_topic=project.topic[:30],
    )

    return RenameProjectResponse(
        project_id=project_id,
        topic=project.topic,
        message="프로젝트 이름이 변경되었습니다.",
    )


# =============================================================================
# v3 Research & Experiment Process Routes
# =============================================================================

@router.get("/v3/{project_id}/process/research-experiment", response_model=ResearchExperimentStateResponse)
async def get_research_experiment_process(project_id: str) -> ResearchExperimentStateResponse:
    """Get Research & Experiment process state."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    process = project.processes.research_experiment
    # Return the artifact for the current phase
    current_artifact = process.get_current_artifact()
    return ResearchExperimentStateResponse(
        status=process.status,
        current_phase=process.current_phase.value,
        messages=process.messages,
        artifact=current_artifact,
        state=process.state.model_dump(),
    )


@router.post("/v3/{project_id}/process/research-experiment/start")
async def start_research_experiment(project_id: str) -> dict:
    """Start the Research & Experiment process (shows welcome message)."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check authentication
    token_manager = TokenManager()
    access_token = await token_manager.get_valid_access_token()
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first.",
        )

    # Initialize message queue
    get_process_queue(project_id, "research_experiment")

    # Start welcome message in background
    asyncio.create_task(_start_research_experiment_v3(project_id))

    logger.info("v3 Research & Experiment started", project_id=project_id)

    return {
        "status": "started",
        "project_id": project_id,
        "process": "research_experiment",
        "message": "Research & Experiment process started",
    }


async def _start_research_experiment_v3(project_id: str) -> None:
    """Send welcome message for Research & Experiment process."""
    try:
        project = get_project_v3(project_id)
        if not project:
            return

        welcome_message = """## 연구 토론을 시작합니다! 🎓

안녕하세요! Research Advisor입니다.

**연구 주제를 입력해 주세요.**
다음과 같은 내용을 포함하면 더 좋은 피드백을 드릴 수 있습니다:

- 연구하고자 하는 분야/주제
- 해결하고자 하는 문제
- 예상되는 연구 방법 (있다면)

예시: "딥러닝을 활용한 의료 영상 진단 자동화 연구를 하고 싶습니다. 특히 CT 영상에서 폐암 조기 발견에 초점을 맞추고 있습니다."

---
*연구 주제를 입력하시면 비판적 평가와 함께 구체화를 도와드리겠습니다.*"""

        await emit_process_message(
            project_id,
            "research_experiment",
            "research_advisor",
            welcome_message,
        )

        logger.info("v3 Research & Experiment welcome message sent", project_id=project_id)

    except Exception as e:
        import traceback
        logger.error("v3 Research & Experiment start failed",
                    project_id=project_id,
                    error=str(e),
                    traceback=traceback.format_exc())


@router.post("/v3/{project_id}/process/research-experiment/chat")
async def chat_research_experiment(
    project_id: str,
    chat_request: ChatMessageRequest,
) -> dict:
    """Send a chat message in Research & Experiment process."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Add user message
    user_message = {
        "type": "message",
        "agent": "user",
        "content": chat_request.content,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Add to process messages
    project.processes.research_experiment.messages.append(user_message)
    save_project_v3(project)

    # Emit to SSE stream
    queue = get_process_queue(project_id, "research_experiment")
    await queue.put(user_message)

    # Process message with agent in background
    asyncio.create_task(_process_research_experiment_chat(project_id, chat_request.content, chat_request.model))

    return {"status": "sent", "message": user_message}


async def _process_research_experiment_chat(project_id: str, content: str, model: str | None = None) -> None:
    """Process chat message in Research & Experiment process.

    Args:
        project_id: Project ID.
        content: Message content.
        model: Optional model override from frontend.
    """
    import time
    start_time = time.time()

    try:
        logger.info("v3 Research Experiment chat processing", project_id=project_id, model=model)

        project = get_project_v3(project_id)
        if not project:
            return

        # Check authentication
        token_manager = TokenManager()
        access_token = await token_manager.get_valid_access_token()
        if not access_token:
            await emit_process_message(
                project_id,
                "research_experiment",
                "system",
                "Authentication required. Please login first.",
                "error",
            )
            return

        # Get discussion agent with optional model override
        agent = get_discussion_agent(project_id, model=model)

        # If this is the first message (no topic yet), treat it as the research topic
        if not agent.topic:
            logger.info("v3 First message - treating as research topic")
            response = await agent.start_discussion(content)

            # Save artifact to project state (for current phase)
            project = get_project_v3(project_id)
            if project:
                artifact_content = agent.get_artifact()
                project.processes.research_experiment.set_current_artifact(artifact_content)
                project.processes.research_experiment.state.research_topic = content
                save_project_v3(project)
                # Save to file
                current_phase = project.processes.research_experiment.current_phase.value
                save_artifact_to_file(project_id, current_phase, artifact_content)

            await emit_process_message(
                project_id,
                "research_experiment",
                "research_advisor",
                response,
            )
            return

        # Get response from agent
        response = await agent.chat(content)

        # Save artifact to project state (for current phase)
        project = get_project_v3(project_id)
        if project:
            artifact_content = agent.get_artifact()
            project.processes.research_experiment.set_current_artifact(artifact_content)
            save_project_v3(project)
            # Save to file
            current_phase = project.processes.research_experiment.current_phase.value
            save_artifact_to_file(project_id, current_phase, artifact_content)

        # Check if ready for next phase
        if agent.is_ready_for_next_phase:
            project = get_project_v3(project_id)
            if project:
                # Update state to indicate research definition is done (not complete flag yet)
                project.processes.research_experiment.state.refined_topic = agent.topic
                save_project_v3(project)

            await emit_process_message(
                project_id,
                "research_experiment",
                "research_advisor",
                response,
            )
            await emit_process_message(
                project_id,
                "research_experiment",
                "system",
                "Research Definition 준비 완료! '완료' 버튼을 클릭하여 Literature Review를 해금하거나, 계속 수정할 수 있습니다.",
                "phase_ready",
            )
        else:
            await emit_process_message(
                project_id,
                "research_experiment",
                "research_advisor",
                response,
            )

        logger.info("v3 Research Experiment chat processed",
                   project_id=project_id,
                   elapsed=f"{time.time() - start_time:.2f}s")

    except Exception as e:
        import traceback
        logger.error("v3 Research Experiment chat failed",
                    project_id=project_id,
                    error=str(e),
                    traceback=traceback.format_exc())
        await emit_process_message(
            project_id,
            "research_experiment",
            "system",
            f"Error processing message: {str(e)}",
            "error",
        )


@router.post("/v3/{project_id}/process/research-experiment/switch-phase")
async def switch_research_experiment_phase(
    project_id: str,
    request: SwitchPhaseRequest,
) -> dict:
    """Switch phase within Research & Experiment (research_definition ↔ experiment_design).

    This endpoint handles artifact switching:
    1. Saves the current agent's artifact to the OLD phase's field
    2. Loads the NEW phase's artifact into the agent
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate phase
    try:
        new_phase = ProcessPhase(request.phase)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase. Must be one of: {[p.value for p in ProcessPhase]}",
        )

    old_phase = project.processes.research_experiment.current_phase

    # If same phase, no need to switch
    if old_phase == new_phase:
        return {
            "status": "unchanged",
            "old_phase": old_phase.value,
            "new_phase": new_phase.value,
        }

    # Save current agent's artifact to the OLD phase before switching
    if project_id in _discussion_agents:
        agent = _discussion_agents[project_id]
        current_artifact = agent.get_artifact()
        if current_artifact:
            # Save to the appropriate phase field based on OLD phase
            if old_phase == ProcessPhase.RESEARCH_DEFINITION:
                project.processes.research_experiment.research_definition_artifact = current_artifact
                save_artifact_to_file(project_id, "research_definition", current_artifact)
            else:
                project.processes.research_experiment.experiment_design_artifact = current_artifact
                save_artifact_to_file(project_id, "experiment_design", current_artifact)
            logger.info("Saved artifact for old phase",
                       project_id=project_id[:8],
                       phase=old_phase.value,
                       artifact_len=len(current_artifact))

    # Switch phase
    project.switch_phase(new_phase)
    save_project_v3(project)

    # Load the NEW phase's artifact into the agent and update agent phase
    if project_id in _discussion_agents:
        agent = _discussion_agents[project_id]

        # CRITICAL: Set agent's phase to match the new project phase
        if new_phase == ProcessPhase.RESEARCH_DEFINITION:
            agent.set_phase(ResearchDiscussionAgent.PHASE_RESEARCH_DEFINITION)
            new_artifact = project.processes.research_experiment.research_definition_artifact
        else:
            agent.set_phase(ResearchDiscussionAgent.PHASE_EXPERIMENT_DESIGN)
            new_artifact = project.processes.research_experiment.experiment_design_artifact

        if new_artifact:
            agent.set_artifact(new_artifact)
            logger.info("Loaded artifact for new phase",
                       project_id=project_id[:8],
                       phase=new_phase.value,
                       artifact_len=len(new_artifact))
        else:
            # Initialize with default artifact for the new phase if none exists
            if new_phase == ProcessPhase.RESEARCH_DEFINITION:
                agent.set_artifact(agent._initial_artifact)
            else:
                # Use experiment design initial artifact
                agent.set_artifact(agent.INITIAL_EXPERIMENT_ARTIFACT)
            logger.info("Initialized default artifact for new phase",
                       project_id=project_id[:8],
                       phase=new_phase.value)

    logger.info("v3 Phase switched",
               project_id=project_id,
               old_phase=old_phase.value,
               new_phase=new_phase.value)

    return {
        "status": "switched",
        "old_phase": old_phase.value,
        "new_phase": new_phase.value,
    }


@router.post("/v3/{project_id}/process/research-experiment/complete", response_model=CompletePhaseResponse)
async def complete_research_experiment_phase(project_id: str) -> CompletePhaseResponse:
    """Complete the current phase (triggers unlock of downstream process).

    - Research Definition complete → Unlocks Literature Review
    - Experiment Design complete → Unlocks Paper Writing

    Note: This is ONE-WAY. Once completed, the flag stays true even if you modify the content.
    Research Definition remains accessible and editable even after completion.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = project.processes.research_experiment.current_phase
    unlocked_process = None
    message = ""

    if current_phase == ProcessPhase.RESEARCH_DEFINITION:
        if project.research_definition_complete:
            message = "Research Definition이 이미 완료되었습니다."
        else:
            project.complete_research_definition()
            if project.experiment_design_complete:
                # Both RD and ED are complete - unlock literature_search and paper_writing
                unlocked_process = "literature_search,paper_writing"
                message = "Research Definition 완료! Literature Search와 Paper Writing이 해금되었습니다."
                logger.info("v3 Research Definition completed, all processes unlocked",
                           project_id=project_id)
            else:
                message = "Research Definition 완료! Experiment Design을 완료하면 Literature Search와 Paper Writing이 해금됩니다."
                logger.info("v3 Research Definition completed, awaiting Experiment Design",
                           project_id=project_id)

    elif current_phase == ProcessPhase.EXPERIMENT_DESIGN:
        if project.experiment_design_complete:
            message = "Experiment Design이 이미 완료되었습니다."
        else:
            project.complete_experiment_design()
            if project.research_definition_complete:
                # Both RD and ED are complete - unlock literature_search and paper_writing
                unlocked_process = "literature_search,paper_writing"
                message = "Experiment Design 완료! Literature Search와 Paper Writing이 해금되었습니다."
                logger.info("v3 Experiment Design completed, all processes unlocked",
                           project_id=project_id)
            else:
                message = "Experiment Design 완료! Research Definition을 완료하면 Literature Search와 Paper Writing이 해금됩니다."
                logger.info("v3 Experiment Design completed, awaiting Research Definition",
                           project_id=project_id)

    save_project_v3(project)

    # Notify via SSE
    await emit_process_message(
        project_id,
        "research_experiment",
        "system",
        message,
        "phase_complete",
    )

    return CompletePhaseResponse(
        success=True,
        message=message,
        unlocked_process=unlocked_process,
    )


class ResetRequest(BaseModel):
    """Request to reset a process."""

    reset_messages: bool = Field(default=True, description="Reset chat messages")
    reset_artifact: bool = Field(default=True, description="Reset artifact/document")


class ResetResponse(BaseModel):
    """Response after resetting a process."""

    success: bool
    message: str
    reset_messages: bool
    reset_artifact: bool


@router.post("/v3/{project_id}/process/research-experiment/reset", response_model=ResetResponse)
async def reset_research_experiment(
    project_id: str,
    request: ResetRequest,
) -> ResetResponse:
    """Reset Research & Experiment process (clear messages and/or artifact).

    Args:
        project_id: Project ID.
        request: What to reset (messages, artifact, or both).

    Returns:
        Reset result.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = project.processes.research_experiment.current_phase
    reset_items = []

    if request.reset_messages:
        # Clear messages
        project.processes.research_experiment.messages = []
        reset_items.append("메시지")

        # Clear message queue
        if project_id in _process_queues and "research_experiment" in _process_queues[project_id]:
            # Create a new empty queue
            _process_queues[project_id]["research_experiment"] = asyncio.Queue()

    if request.reset_artifact:
        # Clear artifact for current phase
        if current_phase == ProcessPhase.RESEARCH_DEFINITION:
            project.processes.research_experiment.research_definition_artifact = ""
            reset_items.append("연구 정의 문서")
        else:
            project.processes.research_experiment.experiment_design_artifact = ""
            reset_items.append("실험 설계 문서")

        # Also reset agent's artifact if exists
        if project_id in _discussion_agents:
            agent = _discussion_agents[project_id]
            if current_phase == ProcessPhase.RESEARCH_DEFINITION:
                agent.set_artifact(agent._initial_artifact)
            else:
                agent.set_artifact(agent.INITIAL_EXPERIMENT_ARTIFACT)
            # Also reset topic if resetting research definition
            if current_phase == ProcessPhase.RESEARCH_DEFINITION:
                agent.topic = ""

    save_project_v3(project)

    message = f"{', '.join(reset_items)}이(가) 초기화되었습니다." if reset_items else "초기화할 항목이 없습니다."

    logger.info(
        "Research & Experiment reset",
        project_id=project_id[:8],
        phase=current_phase.value,
        reset_messages=request.reset_messages,
        reset_artifact=request.reset_artifact,
    )

    return ResetResponse(
        success=True,
        message=message,
        reset_messages=request.reset_messages,
        reset_artifact=request.reset_artifact,
    )


@router.get("/v3/{project_id}/process/research-experiment/stream")
async def stream_research_experiment(project_id: str, request: Request):
    """SSE endpoint for streaming messages from Research & Experiment process."""
    print(f"[SSE-v3] Stream connection for research_experiment: {project_id}", flush=True)

    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get or create process queue
    queue = get_process_queue(project_id, "research_experiment")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'project_id': project_id, 'process': 'research_experiment'})}\n\n"

            # Send existing messages
            current_project = get_project_v3(project_id)
            if current_project:
                existing_msgs = current_project.processes.research_experiment.messages
                print(f"[SSE-v3] Sending {len(existing_msgs)} existing messages", flush=True)
                for msg in existing_msgs:
                    yield f"data: {json.dumps(msg)}\n\n"

            # Stream new messages
            while True:
                if await request.is_disconnected():
                    print(f"[SSE-v3] Client disconnected", flush=True)
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    print(f"[SSE-v3] Got message from queue: {message.get('agent', 'unknown')}", flush=True)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        except asyncio.CancelledError:
            logger.info("v3 SSE stream cancelled", project_id=project_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "http://localhost:3000",
        },
    )


# =============================================================================
# v3 Paper Writing Process Routes
# =============================================================================

class PaperWritingStateResponse(BaseModel):
    """Response for Paper Writing process state."""

    status: str
    is_locked: bool
    messages: list[dict]
    artifact: str
    state: dict


@router.get("/v3/{project_id}/process/paper-writing", response_model=PaperWritingStateResponse)
async def get_paper_writing_process(project_id: str) -> PaperWritingStateResponse:
    """Get Paper Writing process state.

    Returns lock status - Paper Writing is locked until Experiment Design is complete.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    process = project.processes.paper_writing
    is_locked = process.status == ProcessStatus.LOCKED

    return PaperWritingStateResponse(
        status=process.status.value if hasattr(process.status, 'value') else process.status,
        is_locked=is_locked,
        messages=process.messages,
        artifact=process.artifact,
        state=process.state.model_dump(),
    )


@router.post("/v3/{project_id}/process/paper-writing/start")
async def start_paper_writing(project_id: str) -> dict:
    """Start the Paper Writing process.

    Requires Experiment Design to be complete (experiment_design_complete = true).
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Paper Writing is unlocked
    if not project.experiment_design_complete:
        raise HTTPException(
            status_code=403,
            detail="Paper Writing is locked. Complete Experiment Design first.",
        )

    # Check authentication
    token_manager = TokenManager()
    access_token = await token_manager.get_valid_access_token()
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first.",
        )

    # Initialize message queue
    get_process_queue(project_id, "paper_writing")

    # Start welcome message in background
    asyncio.create_task(_start_paper_writing_v3(project_id))

    logger.info("v3 Paper Writing started", project_id=project_id)

    return {
        "status": "started",
        "project_id": project_id,
        "process": "paper_writing",
        "message": "Paper Writing process started",
    }


async def _start_paper_writing_v3(project_id: str) -> None:
    """Send welcome message for Paper Writing process."""
    try:
        project = get_project_v3(project_id)
        if not project:
            return

        welcome_message = """## 논문 작성 도우미

안녕하세요! Research Definition과 Experiment Design을 기반으로 논문 작성을 도와드리겠습니다.

### 제공 기능

이 도우미는 다음 **3가지 기능만** 지원합니다:

1. **제목 생성** - 5개의 학술 논문 제목 후보를 제안합니다
2. **구조 설계** - IMRAD 형식의 논문 구조(2수준 절까지)를 설계합니다
3. **서론 작성** - 4단락 구조의 Introduction을 작성합니다

### 사용 방법

원하시는 작업을 말씀해주세요:
- "제목을 만들어주세요"
- "논문 구조를 잡아주세요"
- "서론을 써주세요"

또는 순서대로 진행하시려면 **"제목 생성"**부터 시작하세요.

---
*참고: Methods, Results, Discussion 등 다른 섹션 작성은 지원하지 않습니다.*"""

        await emit_process_message(
            project_id,
            "paper_writing",
            "paper_advisor",
            welcome_message,
        )

        logger.info("v3 Paper Writing welcome message sent", project_id=project_id)

    except Exception as e:
        import traceback
        logger.error("v3 Paper Writing start failed",
                    project_id=project_id,
                    error=str(e),
                    traceback=traceback.format_exc())


@router.post("/v3/{project_id}/process/paper-writing/chat")
async def chat_paper_writing(
    project_id: str,
    chat_request: ChatMessageRequest,
) -> dict:
    """Send a chat message in Paper Writing process.

    Requires Paper Writing to be unlocked.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Paper Writing is unlocked
    if not project.experiment_design_complete:
        raise HTTPException(
            status_code=403,
            detail="Paper Writing is locked. Complete Experiment Design first.",
        )

    # Add user message
    user_message = {
        "type": "message",
        "agent": "user",
        "content": chat_request.content,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Add to process messages
    project.processes.paper_writing.messages.append(user_message)
    save_project_v3(project)

    # Emit to SSE stream
    queue = get_process_queue(project_id, "paper_writing")
    await queue.put(user_message)

    # Process message with agent in background
    asyncio.create_task(_process_paper_writing_chat(project_id, chat_request.content, chat_request.model))

    return {"status": "sent", "message": user_message}


async def _process_paper_writing_chat(project_id: str, content: str, model: str | None = None) -> None:
    """Process chat message in Paper Writing process.

    Uses PaperWritingAgent (cached per project) to:
    1. Generate title candidates
    2. Create paper structure (IMRAD)
    3. Write Introduction only

    The agent maintains conversation history for natural dialogue flow.

    Args:
        project_id: Project ID.
        content: Message content.
        model: Optional model override from frontend.
    """
    import time

    start_time = time.time()

    try:
        logger.info("v3 Paper Writing chat processing", project_id=project_id)

        project = get_project_v3(project_id)
        if not project:
            return

        # Check authentication
        token_manager = TokenManager()
        access_token = await token_manager.get_valid_access_token()
        if not access_token:
            await emit_process_message(
                project_id,
                "paper_writing",
                "system",
                "Authentication required. Please login first.",
                "error",
            )
            return

        # Get Research Definition and Experiment Design content
        rd_content = project.processes.research_experiment.research_definition_artifact or ""
        ed_content = project.processes.research_experiment.experiment_design_artifact or ""

        if not rd_content and not ed_content:
            await emit_process_message(
                project_id,
                "paper_writing",
                "system",
                "Research Definition과 Experiment Design 내용이 없습니다. 먼저 연구 & 실험 단계를 완료해주세요.",
                "error",
            )
            return

        # Get cached Paper Writing Agent (maintains conversation history)
        agent = get_paper_writing_agent(project_id, model)

        # Update context (in case RD/ED was updated)
        agent.set_context(rd_content, ed_content)

        # Restore artifact from project if agent's artifact is empty
        saved_artifact = project.processes.paper_writing.artifact or ""
        initial_artifact = load_pw_initial_artifact() or ""
        if saved_artifact and agent.get_artifact() == initial_artifact:
            agent.set_artifact(saved_artifact)

        # Process the message using conversational chat
        response = await agent.chat(content)
        updated_artifact = agent.get_artifact()

        # Update artifact
        project = get_project_v3(project_id)
        if project and updated_artifact:
            project.processes.paper_writing.artifact = updated_artifact
            save_project_v3(project)
            # Save to file
            save_artifact_to_file(project_id, "paper_writing", updated_artifact)

        await emit_process_message(
            project_id,
            "paper_writing",
            "paper_advisor",
            response,
        )

        logger.info("v3 Paper Writing chat processed",
                   project_id=project_id,
                   elapsed=f"{time.time() - start_time:.2f}s")

    except Exception as e:
        import traceback
        logger.error("v3 Paper Writing chat failed",
                    project_id=project_id,
                    error=str(e),
                    traceback=traceback.format_exc())
        await emit_process_message(
            project_id,
            "paper_writing",
            "system",
            f"오류가 발생했습니다: {str(e)}",
            "error",
        )


@router.post("/v3/{project_id}/process/paper-writing/reset", response_model=ResetResponse)
async def reset_paper_writing(
    project_id: str,
    request: ResetRequest,
) -> ResetResponse:
    """Reset Paper Writing process (clear messages and/or artifact).

    Args:
        project_id: Project ID.
        request: What to reset (messages, artifact, or both).

    Returns:
        Reset result.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    reset_items = []

    if request.reset_messages:
        # Clear messages
        project.processes.paper_writing.messages = []
        reset_items.append("메시지")

        # Clear message queue
        if project_id in _process_queues and "paper_writing" in _process_queues[project_id]:
            # Create a new empty queue
            _process_queues[project_id]["paper_writing"] = asyncio.Queue()

        # Reset agent's conversation history
        if project_id in _paper_writing_agents:
            _paper_writing_agents[project_id].conversation_history = []

    if request.reset_artifact:
        # Clear artifact
        project.processes.paper_writing.artifact = ""
        reset_items.append("논문 초안")

        # Reset agent's artifact
        if project_id in _paper_writing_agents:
            initial_artifact = load_pw_initial_artifact() or "# [논문 제목 미정]"
            _paper_writing_agents[project_id].set_artifact(initial_artifact)

    save_project_v3(project)

    message = f"{', '.join(reset_items)}이(가) 초기화되었습니다." if reset_items else "초기화할 항목이 없습니다."

    logger.info(
        "Paper Writing reset",
        project_id=project_id[:8],
        reset_messages=request.reset_messages,
        reset_artifact=request.reset_artifact,
    )

    return ResetResponse(
        success=True,
        message=message,
        reset_messages=request.reset_messages,
        reset_artifact=request.reset_artifact,
    )


@router.get("/v3/{project_id}/process/paper-writing/stream")
async def stream_paper_writing(project_id: str, request: Request):
    """SSE endpoint for streaming messages from Paper Writing process."""
    print(f"[SSE-v3] Stream connection for paper_writing: {project_id}", flush=True)

    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Paper Writing is unlocked (allow stream even if locked for state updates)

    # Get or create process queue
    queue = get_process_queue(project_id, "paper_writing")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'project_id': project_id, 'process': 'paper_writing'})}\n\n"

            # Send existing messages
            current_project = get_project_v3(project_id)
            if current_project:
                existing_msgs = current_project.processes.paper_writing.messages
                print(f"[SSE-v3] Paper Writing: Sending {len(existing_msgs)} existing messages", flush=True)
                for msg in existing_msgs:
                    yield f"data: {json.dumps(msg)}\n\n"

            # Stream new messages
            while True:
                if await request.is_disconnected():
                    print(f"[SSE-v3] Paper Writing client disconnected", flush=True)
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    print(f"[SSE-v3] Paper Writing got message: {message.get('agent', 'unknown')}", flush=True)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        except asyncio.CancelledError:
            logger.info("v3 Paper Writing SSE stream cancelled", project_id=project_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "http://localhost:3000",
        },
    )


# =============================================================================
# v3 Document Download API (Secure)
# =============================================================================

# Allowed document types for security
ALLOWED_DOCUMENT_TYPES = frozenset(["research_definition", "experiment_design", "paper_draft"])

# UUID regex for project ID validation
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def _validate_project_id(project_id: str) -> bool:
    """Validate project ID is a valid UUID format.

    Security: Prevents path traversal and injection attacks.
    """
    return bool(UUID_PATTERN.match(project_id))


def _validate_document_type(doc_type: str) -> bool:
    """Validate document type is in allowed list.

    Security: Prevents arbitrary file access.
    """
    return doc_type in ALLOWED_DOCUMENT_TYPES


def _has_meaningful_content(artifact: str) -> bool:
    """Check if artifact has meaningful content beyond initial template.

    Args:
        artifact: Artifact content to check.

    Returns:
        True if artifact has meaningful content, False if it's just a template.
    """
    if not artifact or len(artifact.strip()) < 100:
        return False

    # Check if it has a real title (not the default placeholder)
    has_real_title = (
        "[논문 제목 미정]" not in artifact and
        "[제목 미정]" not in artifact and
        artifact.count("#") > 3  # Has multiple sections beyond just the title
    )

    # If it has a real title and multiple sections, it's meaningful
    if has_real_title:
        return True

    # Check for placeholder patterns that indicate template-only content
    placeholders = [
        "[작성 대기]",
        "[서론 작성 대기]",
        "[구조 설계 후 작성]",
        "[논문 완성 후 작성]",
    ]

    # Count how many placeholders are present
    placeholder_count = sum(1 for ph in placeholders if ph in artifact)

    # If 4 or fewer placeholders and has reasonable length, it's meaningful
    # (This covers cases where Introduction is written but other sections are pending)
    if placeholder_count <= 4 and len(artifact) > 500:
        return True

    # If more than 5 placeholders, likely just a template
    if placeholder_count > 5:
        return False

    return True


def _get_document_content(project_id: str, doc_type: str) -> tuple[str | None, str]:
    """Get document content securely.

    Args:
        project_id: Validated project ID.
        doc_type: Validated document type.

    Returns:
        Tuple of (content, filename). Content is None if not found.
    """
    if doc_type == "research_definition":
        content = read_research_definition(project_id)
        filename = "Research Definition.md"
        # Sync from project state if file doesn't exist
        if not content:
            project = get_project_v3(project_id)
            if project and project.processes.research_experiment.research_definition_artifact:
                artifact = project.processes.research_experiment.research_definition_artifact
                # Check if artifact has meaningful content
                if _has_meaningful_content(artifact):
                    content = artifact
                    save_research_definition(project_id, content)
                    logger.info("Synced research_definition from project state", project_id=project_id)
    elif doc_type == "experiment_design":
        content = read_experiment_design(project_id)
        filename = "Experiment Design.md"
        # Sync from project state if file doesn't exist
        if not content:
            project = get_project_v3(project_id)
            if project and project.processes.research_experiment.experiment_design_artifact:
                artifact = project.processes.research_experiment.experiment_design_artifact
                # Check if artifact has meaningful content
                if _has_meaningful_content(artifact):
                    content = artifact
                    save_experiment_design(project_id, content)
                    logger.info("Synced experiment_design from project state", project_id=project_id)
    elif doc_type == "paper_draft":
        content = read_paper_draft(project_id)
        filename = "Paper.md"
        logger.info("read_paper_draft result",
                   project_id=project_id,
                   content_exists=bool(content),
                   content_length=len(content) if content else 0)
        # Sync from project state if file doesn't exist
        if not content:
            logger.info("No file content, checking project state", project_id=project_id)
            project = get_project_v3(project_id)
            if project and project.processes.paper_writing.artifact:
                artifact = project.processes.paper_writing.artifact
                has_meaningful = _has_meaningful_content(artifact)
                logger.info("Project state check",
                           project_id=project_id,
                           artifact_length=len(artifact),
                           has_meaningful=has_meaningful)
                # Check if artifact has meaningful content
                if has_meaningful:
                    content = artifact
                    save_paper_draft(project_id, content)
                    logger.info("Synced paper_draft from project state", project_id=project_id)
                else:
                    logger.warning("Artifact has no meaningful content", project_id=project_id)
            else:
                logger.warning("No project or artifact found", project_id=project_id)
    else:
        return None, ""

    logger.info("Returning document content",
               doc_type=doc_type,
               has_content=bool(content),
               content_length=len(content) if content else 0)
    return content, filename


class DocumentListResponse(BaseModel):
    """Response for document list."""

    project_id: str
    documents: dict


class DocumentDownloadInfo(BaseModel):
    """Info about a downloadable document."""

    type: str
    name: str
    available: bool
    download_url: str | None = None


@router.get("/v3/{project_id}/documents")
async def list_project_documents(project_id: str) -> DocumentListResponse:
    """List all available documents for a project.

    Security: Validates project ID format before processing.
    """
    # Security: Validate project ID format
    if not _validate_project_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    # Check project exists
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get file summary securely
    summary = get_project_files_summary(project_id)

    documents = {}

    # Research Definition - check both file and project state
    rd_file_exists = summary["files"]["research_definition"]["exists"]
    rd_artifact = project.processes.research_experiment.research_definition_artifact or ""
    rd_available = rd_file_exists or _has_meaningful_content(rd_artifact)
    documents["research_definition"] = {
        "name": "Research Definition.md",
        "available": rd_available,
        "download_url": f"/api/research/v3/{project_id}/documents/research_definition/download" if rd_available else None,
    }

    # Experiment Design - check both file and project state
    ed_file_exists = summary["files"]["experiment_design"]["exists"]
    ed_artifact = project.processes.research_experiment.experiment_design_artifact or ""
    ed_available = ed_file_exists or _has_meaningful_content(ed_artifact)
    documents["experiment_design"] = {
        "name": "Experiment Design.md",
        "available": ed_available,
        "download_url": f"/api/research/v3/{project_id}/documents/experiment_design/download" if ed_available else None,
    }

    # Paper Draft - check both file and project state
    pd_file_exists = summary["files"]["paper_draft"]["exists"]
    pd_artifact = project.processes.paper_writing.artifact or ""
    pd_available = pd_file_exists or _has_meaningful_content(pd_artifact)
    documents["paper_draft"] = {
        "name": "Paper.md",
        "available": pd_available,
        "download_url": f"/api/research/v3/{project_id}/documents/paper_draft/download" if pd_available else None,
    }

    return DocumentListResponse(
        project_id=project_id,
        documents=documents,
    )


@router.get("/v3/{project_id}/documents/{doc_type}/download")
async def download_document(project_id: str, doc_type: str) -> Response:
    """Download a document as MD file.

    Security measures:
    1. Project ID validation (UUID format)
    2. Document type validation (whitelist)
    3. Project existence check
    4. Path traversal prevention (predefined paths only)
    5. Sanitized filename in Content-Disposition

    Args:
        project_id: Project UUID.
        doc_type: Document type (research_definition, experiment_design, paper_draft).

    Returns:
        MD file download response.
    """
    # Security: Validate project ID format
    if not _validate_project_id(project_id):
        logger.warning(
            "Invalid project ID format in download request",
            project_id=project_id[:50] if project_id else "None",
        )
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    # Security: Validate document type (whitelist)
    if not _validate_document_type(doc_type):
        logger.warning(
            "Invalid document type in download request",
            doc_type=doc_type[:50] if doc_type else "None",
        )
        raise HTTPException(status_code=400, detail="Invalid document type")

    # Security: Check project exists
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get document content securely (no user-controlled path construction)
    content, filename = _get_document_content(project_id, doc_type)

    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {doc_type}. Generate it first.",
        )

    # Security: Sanitize filename for Content-Disposition header
    safe_filename = sanitize_filename(filename, max_length=100)
    if not safe_filename.endswith(".md"):
        safe_filename += ".md"

    # Log successful download
    logger.info(
        "Document download",
        project_id=project_id,
        doc_type=doc_type,
        content_length=len(content),
    )

    # Return as downloadable file
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Content-Length": str(len(content.encode("utf-8"))),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/v3/{project_id}/documents/{doc_type}/preview")
async def preview_document(project_id: str, doc_type: str) -> dict:
    """Preview a document content without downloading.

    Same security measures as download endpoint.

    Returns:
        Dict with document content and metadata.
    """
    # Security: Validate project ID format
    if not _validate_project_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    # Security: Validate document type (whitelist)
    if not _validate_document_type(doc_type):
        raise HTTPException(status_code=400, detail="Invalid document type")

    # Security: Check project exists
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get document content securely
    content, filename = _get_document_content(project_id, doc_type)

    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {doc_type}. Generate it first.",
        )

    return {
        "project_id": project_id,
        "document_type": doc_type,
        "filename": filename,
        "content": content,
        "content_length": len(content),
    }


# =============================================================================
# DYNAMIC ROUTES (with {project_id} path parameter) - Legacy API
# =============================================================================

@router.get("/{project_id}", response_model=ProjectStatusResponse)
async def get_project(project_id: str) -> ProjectStatusResponse:
    """Get project details and status."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _projects[project_id]

    # Get artifact from agent or project state
    artifact = ""
    if project_id in _discussion_agents:
        artifact = _discussion_agents[project_id].get_artifact()
    elif "research_artifact" in project.get("state", {}):
        artifact = project["state"]["research_artifact"]

    return ProjectStatusResponse(
        project_id=project_id,
        topic=project["topic"],
        status=project["status"],
        current_phase=project["current_phase"],
        state=project["state"],
        messages=project["messages"],
        research_artifact=artifact,
    )


@router.post("/{project_id}/start")
async def start_workflow(
    project_id: str,
) -> dict:
    """Start the research workflow for a project (Phase 1: Discussion)."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _projects[project_id]

    if project["status"] == "running":
        raise HTTPException(status_code=400, detail="Workflow already running")

    # Check authentication - try to get valid token (will refresh if needed)
    token_manager = TokenManager()
    access_token = await token_manager.get_valid_access_token()
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first.",
        )

    # Update status
    project["status"] = "running"
    project["current_phase"] = "phase_1"

    # 파일에 저장
    save_project(project)

    # Initialize message queue
    get_message_queue(project_id)

    # Start Phase 1 in background using asyncio.create_task
    asyncio.create_task(_start_phase1_discussion(project_id, project["topic"]))

    logger.info("Workflow started", project_id=project_id)

    return {
        "status": "started",
        "project_id": project_id,
        "message": "Phase 1: Research Discussion started",
    }


async def _start_phase1_discussion(project_id: str, project_name: str) -> None:
    """Start Phase 1: Research Discussion.

    Shows welcome message and waits for user to input their research topic.
    """
    try:
        logger.info("=" * 50)
        logger.info("Phase 1 STARTING", project_id=project_id, project_name=project_name[:100])

        # Send welcome message - ask user to input their research topic
        welcome_message = """## 연구 토론을 시작합니다! 🎓

안녕하세요! Research Advisor입니다.

**연구 주제를 입력해 주세요.**
다음과 같은 내용을 포함하면 더 좋은 피드백을 드릴 수 있습니다:

- 연구하고자 하는 분야/주제
- 해결하고자 하는 문제
- 예상되는 연구 방법 (있다면)

예시: "딥러닝을 활용한 의료 영상 진단 자동화 연구를 하고 싶습니다. 특히 CT 영상에서 폐암 조기 발견에 초점을 맞추고 있습니다."

---
*연구 주제를 입력하시면 비판적 평가와 함께 구체화를 도와드리겠습니다.*"""

        await emit_message(
            project_id,
            "research_discussion",
            welcome_message,
        )

        logger.info("Phase 1 welcome message sent", project_id=project_id)
        logger.info("=" * 50)

    except Exception as e:
        import traceback
        logger.error("=" * 50)
        logger.error("Phase 1 FAILED",
                    project_id=project_id,
                    error=str(e),
                    traceback=traceback.format_exc())
        logger.error("=" * 50)
        _projects[project_id]["status"] = "failed"
        await emit_message(
            project_id,
            "system",
            f"Error starting discussion: {str(e)}",
            "error",
        )


@router.post("/{project_id}/chat")
async def send_chat_message(
    project_id: str,
    chat_request: ChatMessageRequest,  # Renamed from 'request' to avoid conflict
) -> dict:
    """Send a chat message to the research agent."""
    import traceback
    import sys

    # Force flush output - v3
    print(f"\n[CHAT-v3] ===== CHAT ENDPOINT CALLED =====", flush=True)
    sys.stdout.flush()

    try:
        print(f"[CHAT-v3] project_id: {project_id}", flush=True)
        print(f"[CHAT-v3] content: {chat_request.content[:100]}", flush=True)

        if project_id not in _projects:
            print(f"[CHAT] ERROR: Project not found")
            raise HTTPException(status_code=404, detail="Project not found")

        project = _projects[project_id]
        print(f"[CHAT] Project found, status: {project['status']}")

        # Add user message
        user_message = {
            "type": "message",
            "agent": "user",
            "content": chat_request.content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        project["messages"].append(user_message)
        print(f"[CHAT] User message added to project")

        # Emit to SSE stream
        if project_id in _message_queues:
            await _message_queues[project_id].put(user_message)
            print(f"[CHAT] User message added to SSE queue")
        else:
            print(f"[CHAT] WARNING: No message queue for project")

        # Process message with agent in background using asyncio.create_task
        print(f"[CHAT] Creating background task for chat processing...")
        task = asyncio.create_task(_process_chat_message(project_id, chat_request.content))
        print(f"[CHAT] Background task created: {task}")

        return {"status": "sent", "message": user_message}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] EXCEPTION: {str(e)}")
        print(f"[CHAT] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


async def _process_chat_message(project_id: str, content: str) -> None:
    """Process a chat message with the Research Discussion Agent."""
    import time
    start_time = time.time()

    # DEBUG: Use print for immediate output
    print(f"\n{'='*50}")
    print(f"[DEBUG] CHAT MESSAGE PROCESSING START")
    print(f"[DEBUG] project_id: {project_id}")
    print(f"[DEBUG] content: {content[:100]}")
    print(f"{'='*50}\n")

    try:
        logger.info("=" * 50)
        logger.info("CHAT MESSAGE PROCESSING START",
                   project_id=project_id,
                   content_preview=content[:50])

        project = _projects.get(project_id)
        if not project:
            logger.error("Project not found in _process_chat_message", project_id=project_id)
            return

        # Check authentication - try to get valid token (will refresh if needed)
        logger.info("Checking authentication...")
        token_manager = TokenManager()
        access_token = await token_manager.get_valid_access_token()
        if not access_token:
            logger.warning("Failed to get valid token during chat processing", project_id=project_id)
            await emit_message(
                project_id,
                "system",
                "Authentication required. Please login first.",
                "error",
            )
            return
        logger.info("Authentication OK", elapsed=f"{time.time() - start_time:.2f}s")

        # Get discussion agent
        logger.info("Getting discussion agent...")
        agent = get_discussion_agent(project_id)
        logger.info("Got discussion agent",
                   project_id=project_id,
                   topic=agent.topic[:30] if agent.topic else "No topic",
                   elapsed=f"{time.time() - start_time:.2f}s")

        # If this is the first message (no topic yet), treat it as the research topic
        if not agent.topic:
            print(f"[DEBUG] First message - treating as research topic")
            print(f"[DEBUG] Calling agent.start_discussion()...")
            logger.info("First message - treating as research topic")
            llm_start = time.time()
            response = await agent.start_discussion(content)  # content = user's research topic
            llm_elapsed = time.time() - llm_start
            print(f"[DEBUG] agent.start_discussion() completed in {llm_elapsed:.2f}s")
            print(f"[DEBUG] Response length: {len(response)}")
            logger.info("Agent evaluated research topic",
                       response_length=len(response),
                       llm_elapsed=f"{llm_elapsed:.2f}s")

            # Save artifact to project state
            project["state"]["research_artifact"] = agent.get_artifact()
            save_project(project)
            print(f"[DEBUG] Artifact saved to project state")

            print(f"[DEBUG] Emitting response to SSE...")
            await emit_message(project_id, "research_discussion", response)
            print(f"[DEBUG] Response emitted!")
            logger.info("RESEARCH TOPIC EVALUATED",
                       project_id=project_id,
                       total_elapsed=f"{time.time() - start_time:.2f}s")
            logger.info("=" * 50)
            return  # Don't continue to agent.chat()

        # Get response from agent
        logger.info("Calling agent.chat()... (this may take a while)")
        llm_start = time.time()
        response = await agent.chat(content)
        llm_elapsed = time.time() - llm_start
        logger.info("Agent response received",
                   response_length=len(response),
                   llm_elapsed=f"{llm_elapsed:.2f}s",
                   total_elapsed=f"{time.time() - start_time:.2f}s")

        # Save artifact to project state
        project["state"]["research_artifact"] = agent.get_artifact()
        save_project(project)
        logger.info("Artifact saved to project state", project_id=project_id[:8])

        # Check if ready for next phase
        if agent.is_ready_for_next_phase:
            logger.info("Agent ready for next phase, emitting messages...")
            _projects[project_id]["state"]["phase_1_complete"] = True
            await emit_message(project_id, "research_discussion", response)
            await emit_message(
                project_id,
                "system",
                "Phase 1 complete! You can now proceed to Phase 2: Literature Review.",
                "phase_complete",
            )
        else:
            logger.info("Emitting agent response to SSE...")
            await emit_message(project_id, "research_discussion", response)

        logger.info("CHAT MESSAGE PROCESSED SUCCESSFULLY",
                   project_id=project_id,
                   total_elapsed=f"{time.time() - start_time:.2f}s")
        logger.info("=" * 50)

    except Exception as e:
        import traceback
        elapsed = time.time() - start_time
        print(f"\n{'='*50}")
        print(f"[ERROR] CHAT PROCESSING FAILED!")
        print(f"[ERROR] project_id: {project_id}")
        print(f"[ERROR] error: {str(e)}")
        print(f"[ERROR] elapsed: {elapsed:.2f}s")
        print(f"[ERROR] traceback:")
        print(traceback.format_exc())
        print(f"{'='*50}\n")
        logger.error("=" * 50)
        logger.error(
            "CHAT PROCESSING FAILED",
            project_id=project_id,
            error=str(e),
            elapsed=f"{elapsed:.2f}s",
            traceback=traceback.format_exc(),
        )
        logger.error("=" * 50)
        await emit_message(
            project_id,
            "system",
            f"Error processing message: {str(e)}",
            "error",
        )


@router.post("/{project_id}/proceed")
async def proceed_to_next_phase(
    project_id: str,
) -> dict:
    """Proceed to the next phase of research."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _projects[project_id]
    current_phase = project["current_phase"]

    if current_phase == "phase_1":
        # Extract research definition before proceeding
        agent = get_discussion_agent(project_id)
        research_def = await agent.extract_research_definition()

        if research_def:
            project["state"]["research_definition"] = research_def.model_dump()

        # Move to Phase 2
        project["current_phase"] = "phase_2"
        await emit_message(
            project_id,
            "system",
            "Proceeding to Phase 2: Literature Review. Searching for relevant papers...",
            "phase_change",
        )

        # Start Phase 2 (Literature Search) in background using asyncio.create_task
        asyncio.create_task(_start_phase2_literature_review(project_id))

        return {"status": "proceeding", "next_phase": "phase_2"}

    elif current_phase == "phase_2":
        project["current_phase"] = "phase_3"
        await emit_message(
            project_id,
            "system",
            "Proceeding to Phase 3: Experiment Design...",
            "phase_change",
        )
        return {"status": "proceeding", "next_phase": "phase_3"}

    elif current_phase == "phase_3":
        project["current_phase"] = "phase_4"
        await emit_message(
            project_id,
            "system",
            "Proceeding to Phase 4: Paper Writing...",
            "phase_change",
        )
        return {"status": "proceeding", "next_phase": "phase_4"}

    else:
        return {"status": "complete", "message": "Research workflow complete"}


async def _start_phase2_literature_review(project_id: str) -> None:
    """Start Phase 2: Literature Review."""
    try:
        project = _projects.get(project_id)
        if not project:
            return

        research_def = project["state"].get("research_definition", {})
        keywords = research_def.get("suggested_keywords", [])
        topic = project["topic"]

        await emit_message(
            project_id,
            "literature_searcher",
            f"Starting literature search with keywords: {', '.join(keywords) if keywords else topic}",
        )

        # Initialize Literature Searcher Agent
        searcher = LiteratureSearcherAgent(
            use_semantic_scholar=True,
            use_arxiv=True,
            use_google_scholar=True,
        )

        # Perform search
        search_query = topic
        if keywords:
            search_query = f"{topic} {' '.join(keywords[:3])}"  # Use first 3 keywords

        await emit_message(
            project_id,
            "literature_searcher",
            f"Searching across Semantic Scholar, arXiv, and Google Scholar...",
        )

        result = await searcher.search(
            query=search_query,
            keywords=keywords,
            year_start=2022,  # Last 3 years
            year_end=2026,
            limit_per_source=15,
            min_citations=0,
        )

        # Store search results in project state
        papers_data = [paper.model_dump() for paper in result.papers]
        project["state"]["literature_search"] = {
            "query": result.query,
            "total_found": result.total_found,
            "sources_searched": result.sources_searched,
            "papers_count": len(result.papers),
        }
        project["state"]["papers"] = papers_data

        # Format and emit results
        if result.papers:
            await emit_message(
                project_id,
                "literature_searcher",
                f"Found {len(result.papers)} papers from {', '.join(result.sources_searched)}.",
            )

            # Show top 5 papers
            top_papers = result.papers[:5]
            papers_summary = "**Top Papers Found:**\n\n"
            for i, paper in enumerate(top_papers, 1):
                papers_summary += f"{i}. **{paper.title}**\n"
                papers_summary += f"   - Authors: {', '.join(paper.authors[:3])}"
                if len(paper.authors) > 3:
                    papers_summary += "..."
                papers_summary += f"\n   - Year: {paper.year or 'N/A'} | Citations: {paper.citations}\n"
                papers_summary += f"   - Source: {paper.source}\n\n"

            await emit_message(
                project_id,
                "literature_searcher",
                papers_summary,
            )

            # Mark phase as complete
            project["state"]["phase_2_complete"] = True
            await emit_message(
                project_id,
                "system",
                "Literature search complete. Review the papers above. You can proceed to Phase 3: Experiment Design when ready.",
                "phase_complete",
            )
        else:
            await emit_message(
                project_id,
                "literature_searcher",
                "No papers found matching your search criteria. Try broadening your search terms.",
            )

    except Exception as e:
        logger.error("Phase 2 failed", project_id=project_id, error=str(e))
        await emit_message(
            project_id,
            "system",
            f"Error in literature review: {str(e)}",
            "error",
        )


@router.get("/{project_id}/stream")
async def stream_messages(project_id: str, request: Request):
    """SSE endpoint for streaming messages from a project."""
    print(f"[SSE] Stream connection requested for project: {project_id}", flush=True)

    # Get origin for CORS
    origin = request.headers.get("origin", "http://localhost:3000")
    print(f"[SSE] Request origin: {origin}", flush=True)

    if project_id not in _projects:
        print(f"[SSE] Project not found: {project_id}", flush=True)
        raise HTTPException(status_code=404, detail="Project not found")

    # Create/get message queue for this project
    queue = get_message_queue(project_id)
    print(f"[SSE] Queue obtained, current size: {queue.qsize()}", flush=True)

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from message queue."""
        try:
            # Send initial connection event
            print(f"[SSE] Sending connection event", flush=True)
            yield f"data: {json.dumps({'type': 'connected', 'project_id': project_id})}\n\n"

            # Send existing messages
            existing_msgs = _projects[project_id].get("messages", [])
            print(f"[SSE] Sending {len(existing_msgs)} existing messages", flush=True)
            for msg in existing_msgs:
                yield f"data: {json.dumps(msg)}\n\n"

            # Stream new messages
            print(f"[SSE] Starting message loop...", flush=True)
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    print(f"[SSE] Client disconnected", flush=True)
                    break

                try:
                    # Wait for new messages with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    print(f"[SSE] Got message from queue: {message.get('agent', 'unknown')}", flush=True)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    print(f"[SSE] Sending ping (keepalive)", flush=True)
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        except asyncio.CancelledError:
            print(f"[SSE] Stream cancelled", flush=True)
            logger.info("SSE stream cancelled", project_id=project_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # Explicit CORS headers for SSE
            "Access-Control-Allow-Origin": "http://localhost:3000",
        },
    )


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict:
    """Delete a research project."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    # Clean up resources
    if project_id in _running_workflows:
        _running_workflows[project_id].cancel()
        del _running_workflows[project_id]

    if project_id in _discussion_agents:
        del _discussion_agents[project_id]

    if project_id in _message_queues:
        del _message_queues[project_id]

    del _projects[project_id]

    # 파일도 삭제
    delete_project_file(project_id)

    logger.info("Project deleted", project_id=project_id)

    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/research-definition")
async def get_research_definition(project_id: str) -> dict:
    """Get the extracted research definition from Phase 1."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _projects[project_id]
    research_def = project["state"].get("research_definition")

    if not research_def:
        # Try to extract from agent
        if project_id in _discussion_agents:
            agent = _discussion_agents[project_id]
            extracted = await agent.extract_research_definition()
            if extracted:
                research_def = extracted.model_dump()
                project["state"]["research_definition"] = research_def

    if not research_def:
        raise HTTPException(
            status_code=404,
            detail="Research definition not yet available. Complete Phase 1 discussion first.",
        )

    return {"research_definition": research_def}


@router.get("/{project_id}/papers")
async def get_papers(project_id: str) -> dict:
    """Get the papers found in Phase 2 literature search."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _projects[project_id]
    papers = project["state"].get("papers", [])
    search_info = project["state"].get("literature_search", {})

    if not papers:
        raise HTTPException(
            status_code=404,
            detail="No papers found yet. Complete Phase 2 literature search first.",
        )

    return {
        "search_info": search_info,
        "papers": papers,
        "total": len(papers),
    }
