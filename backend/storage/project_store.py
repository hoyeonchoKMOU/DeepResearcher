"""File-based project persistence with v3 process architecture support."""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

import structlog

from backend.orchestrator.state import (
    ProjectState,
    ProjectProcesses,
    ResearchExperimentProcess,
    ResearchExperimentState,
    LiteratureOrganizationProcess,
    LiteratureOrganizationState,
    LiteratureSearchProcess,
    LiteratureSearchState,
    LiteratureReviewProcess,
    LiteratureReviewState,
    PaperWritingProcess,
    PaperWritingState,
    ProcessStatus,
    ProcessPhase,
)

logger = structlog.get_logger(__name__)

# 프로젝트 데이터 저장 경로
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "projects"
PAPERS_DIR = Path(__file__).parent.parent.parent / "data" / "papers"


def ensure_data_dir() -> None:
    """데이터 디렉토리가 없으면 생성."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_papers_dir(project_id: str) -> Path:
    """프로젝트별 논문 디렉토리 생성 및 반환."""
    papers_path = PAPERS_DIR / project_id
    papers_path.mkdir(parents=True, exist_ok=True)
    return papers_path


def get_project_path(project_id: str) -> Path:
    """프로젝트 파일 경로 반환."""
    return DATA_DIR / f"{project_id}.json"


def is_legacy_project(data: dict) -> bool:
    """기존 v2 프로젝트인지 확인."""
    # v3는 'processes' 키가 있음
    return "processes" not in data and "current_phase" in data


def migrate_legacy_project(old_project: dict) -> dict:
    """기존 v2 프로젝트를 v3 구조로 마이그레이션.

    Args:
        old_project: 기존 프로젝트 데이터

    Returns:
        v3 구조의 프로젝트 데이터
    """
    # Phase 매핑: (current_phase, rd_complete, ed_complete)
    phase_mapping = {
        "init": (ProcessPhase.RESEARCH_DEFINITION.value, False, False),
        "phase_1": (ProcessPhase.RESEARCH_DEFINITION.value, False, False),
        "research_definition": (ProcessPhase.RESEARCH_DEFINITION.value, False, False),
        "phase_2": (ProcessPhase.RESEARCH_DEFINITION.value, True, False),
        "literature_review": (ProcessPhase.RESEARCH_DEFINITION.value, True, False),
        "phase_3": (ProcessPhase.EXPERIMENT_DESIGN.value, True, False),
        "experiment_design": (ProcessPhase.EXPERIMENT_DESIGN.value, True, False),
        "phase_4": (ProcessPhase.EXPERIMENT_DESIGN.value, True, True),
        "paper_writing": (ProcessPhase.EXPERIMENT_DESIGN.value, True, True),
    }

    old_phase = old_project.get("current_phase", "phase_1")
    current_phase, rd_complete, ed_complete = phase_mapping.get(
        old_phase,
        (ProcessPhase.RESEARCH_DEFINITION.value, False, False)
    )

    # 기존 state에서 데이터 추출
    old_state = old_project.get("state", {})

    # v3 프로젝트 구조 생성
    project_id = old_project.get("id", "")
    papers_folder = f"papers/{project_id}/" if project_id else ""

    migrated = {
        "id": project_id,
        "topic": old_project.get("topic", ""),
        "created_at": old_project.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
        "research_definition_complete": rd_complete,
        "experiment_design_complete": ed_complete,
        "processes": {
            "research_experiment": {
                "status": "active",
                "current_phase": current_phase,
                "messages": old_project.get("messages", []),
                "artifact": old_project.get("research_artifact", ""),
                "state": {
                    "research_topic": old_state.get("research_topic", old_project.get("topic", "")),
                    "refined_topic": old_state.get("refined_topic", ""),
                    "research_questions": old_state.get("research_questions", []),
                    "novelty_assessment": old_state.get("novelty_assessment", {}),
                    "research_scope": old_state.get("research_scope", {}),
                    "potential_contributions": old_state.get("potential_contributions", []),
                    "search_keywords": old_state.get("search_keywords", []),
                    "experiment_design": old_state.get("experiment_design", {}),
                    "variables": old_state.get("variables", {}),
                    "hypotheses": old_state.get("hypotheses", []),
                    "methodology": old_state.get("methodology", {}),
                }
            },
            "literature_organization": {
                "status": ProcessStatus.UNLOCKED.value,  # Always unlocked
                "papers_folder": papers_folder,
                "state": {
                    "papers": [],
                    "master_md": "master.md"
                }
            },
            "literature_search": {
                "status": ProcessStatus.UNLOCKED.value if (rd_complete and ed_complete) else ProcessStatus.LOCKED.value,
                "state": {
                    "search_history": [],
                    "searched_papers": []
                }
            },
            "paper_writing": {
                "status": ProcessStatus.UNLOCKED.value if (rd_complete and ed_complete) else ProcessStatus.LOCKED.value,
                "messages": [],
                "artifact": "",
                "state": {
                    "imrad_structure": old_state.get("imrad_structure", {}),
                    "draft_sections": old_state.get("draft_sections", {}),
                    "target_journal": old_state.get("target_journal", old_project.get("target_journal", "")),
                    "journal_guidelines": old_state.get("journal_guidelines", {}),
                    "final_paper": old_state.get("final_paper", ""),
                    "cover_letter": old_state.get("cover_letter", ""),
                }
            }
        }
    }

    logger.info(
        "Project migrated to v3",
        project_id=project_id[:8] if project_id else "unknown",
        old_phase=old_phase,
        new_phase=current_phase,
        rd_complete=rd_complete,
        ed_complete=ed_complete
    )

    return migrated


def project_to_dict(project: ProjectState) -> dict:
    """ProjectState를 저장 가능한 딕셔너리로 변환."""
    return {
        "id": project.id,
        "topic": project.topic,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "research_definition_complete": project.research_definition_complete,
        "experiment_design_complete": project.experiment_design_complete,
        "processes": {
            "research_experiment": {
                "status": project.processes.research_experiment.status,
                "current_phase": project.processes.research_experiment.current_phase.value
                    if isinstance(project.processes.research_experiment.current_phase, ProcessPhase)
                    else project.processes.research_experiment.current_phase,
                "messages": project.processes.research_experiment.messages,
                "research_definition_artifact": project.processes.research_experiment.research_definition_artifact,
                "experiment_design_artifact": project.processes.research_experiment.experiment_design_artifact,
                "artifact": project.processes.research_experiment.artifact,  # Legacy
                "state": project.processes.research_experiment.state.model_dump()
            },
            "literature_organization": {
                "status": project.processes.literature_organization.status.value
                    if isinstance(project.processes.literature_organization.status, ProcessStatus)
                    else project.processes.literature_organization.status,
                "papers_folder": project.processes.literature_organization.papers_folder,
                "state": {
                    "papers": [
                        paper.model_dump() if hasattr(paper, 'model_dump') else paper
                        for paper in project.processes.literature_organization.state.papers
                    ],
                    "master_md": project.processes.literature_organization.state.master_md
                }
            },
            "literature_search": {
                "status": project.processes.literature_search.status.value
                    if isinstance(project.processes.literature_search.status, ProcessStatus)
                    else project.processes.literature_search.status,
                "state": {
                    "search_history": [
                        entry.model_dump() if hasattr(entry, 'model_dump') else entry
                        for entry in project.processes.literature_search.state.search_history
                    ],
                    "searched_papers": [
                        paper.model_dump() if hasattr(paper, 'model_dump') else paper
                        for paper in project.processes.literature_search.state.searched_papers
                    ]
                }
            },
            "paper_writing": {
                "status": project.processes.paper_writing.status.value
                    if isinstance(project.processes.paper_writing.status, ProcessStatus)
                    else project.processes.paper_writing.status,
                "messages": project.processes.paper_writing.messages,
                "artifact": project.processes.paper_writing.artifact,
                "state": project.processes.paper_writing.state.model_dump()
            }
        }
    }


def dict_to_project(data: dict) -> ProjectState:
    """딕셔너리를 ProjectState로 변환."""
    # 마이그레이션 필요 여부 확인
    if is_legacy_project(data):
        data = migrate_legacy_project(data)

    processes_data = data.get("processes", {})

    # Research & Experiment process
    re_data = processes_data.get("research_experiment", {})
    re_state = ResearchExperimentState(**re_data.get("state", {}))
    research_experiment = ResearchExperimentProcess(
        status=re_data.get("status", "active"),
        current_phase=ProcessPhase(re_data.get("current_phase", "research_definition")),
        messages=re_data.get("messages", []),
        research_definition_artifact=re_data.get("research_definition_artifact", ""),
        experiment_design_artifact=re_data.get("experiment_design_artifact", ""),
        artifact=re_data.get("artifact", ""),  # Legacy field
        state=re_state
    )

    # Literature Organization process (always unlocked)
    lo_data = processes_data.get("literature_organization", {})
    # Handle migration from old literature_review structure
    if not lo_data and "literature_review" in processes_data:
        old_lr = processes_data["literature_review"]
        lo_data = {
            "status": ProcessStatus.UNLOCKED.value,  # Always unlocked
            "papers_folder": old_lr.get("papers_folder", ""),
            "state": {
                "papers": old_lr.get("state", {}).get("papers", []),
                "master_md": old_lr.get("state", {}).get("master_md", "master.md")
            }
        }
    lo_state = LiteratureOrganizationState(**lo_data.get("state", {}))
    literature_organization = LiteratureOrganizationProcess(
        status=ProcessStatus(lo_data.get("status", "unlocked")),
        papers_folder=lo_data.get("papers_folder", ""),
        state=lo_state
    )

    # Literature Search process (locked until RD+ED complete)
    ls_data = processes_data.get("literature_search", {})
    # Handle migration from old literature_review structure
    if not ls_data and "literature_review" in processes_data:
        old_lr = processes_data["literature_review"]
        ls_data = {
            "status": old_lr.get("status", "locked"),
            "state": {
                "search_history": old_lr.get("state", {}).get("search_history", []),
                "searched_papers": []
            }
        }

    # Debug: log state data being loaded
    ls_state_data = ls_data.get("state", {})
    searched_papers_raw = ls_state_data.get("searched_papers", [])
    logger.info("Loading literature search state",
                project_id=data.get("id"),
                search_history_count=len(ls_state_data.get("search_history", [])),
                searched_papers_count=len(searched_papers_raw))

    ls_state = LiteratureSearchState(**ls_state_data)

    # Debug: verify papers after Pydantic validation
    logger.info("Literature search state after validation",
                project_id=data.get("id"),
                searched_papers_count=len(ls_state.searched_papers))

    literature_search = LiteratureSearchProcess(
        status=ProcessStatus(ls_data.get("status", "locked")),
        state=ls_state
    )

    # Paper Writing process
    pw_data = processes_data.get("paper_writing", {})
    pw_state = PaperWritingState(**pw_data.get("state", {}))
    paper_writing = PaperWritingProcess(
        status=ProcessStatus(pw_data.get("status", "locked")),
        messages=pw_data.get("messages", []),
        artifact=pw_data.get("artifact", ""),
        state=pw_state
    )

    # Create ProjectProcesses
    processes = ProjectProcesses(
        research_experiment=research_experiment,
        literature_organization=literature_organization,
        literature_search=literature_search,
        paper_writing=paper_writing
    )

    # Create ProjectState
    return ProjectState(
        id=data["id"],
        topic=data.get("topic", ""),
        created_at=data.get("created_at", datetime.utcnow().isoformat()),
        updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        research_definition_complete=data.get("research_definition_complete", False),
        experiment_design_complete=data.get("experiment_design_complete", False),
        processes=processes
    )


def save_project(project: dict | ProjectState) -> bool:
    """프로젝트를 파일에 저장.

    Args:
        project: 저장할 프로젝트 데이터 (dict 또는 ProjectState)

    Returns:
        성공 여부
    """
    try:
        ensure_data_dir()

        # ProjectState인 경우 딕셔너리로 변환
        if isinstance(project, ProjectState):
            save_data = project_to_dict(project)
        else:
            save_data = project

        project_id = save_data.get("id")
        if not project_id:
            logger.error("Cannot save project without id")
            return False

        # papers_folder 설정 확인
        if "processes" in save_data:
            lo = save_data["processes"].get("literature_organization", {})
            if not lo.get("papers_folder"):
                save_data["processes"]["literature_organization"]["papers_folder"] = f"papers/{project_id}/"

        file_path = get_project_path(project_id)

        # updated_at 갱신
        save_data["updated_at"] = datetime.utcnow().isoformat()

        # JSON 파일로 저장
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        logger.debug("Project saved", project_id=project_id[:8])
        return True

    except Exception as e:
        pid = project.id if isinstance(project, ProjectState) else project.get("id", "unknown")
        logger.error("Failed to save project", error=str(e), project_id=str(pid)[:8])
        return False


def load_project(project_id: str) -> Optional[ProjectState]:
    """파일에서 프로젝트 로드.

    Args:
        project_id: 프로젝트 ID

    Returns:
        ProjectState 또는 None
    """
    try:
        file_path = get_project_path(project_id)

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 마이그레이션이 필요한 경우 자동 마이그레이션 후 저장
        if is_legacy_project(data):
            logger.info("Auto-migrating legacy project", project_id=project_id[:8])
            data = migrate_legacy_project(data)
            # 마이그레이션된 데이터 저장
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        project = dict_to_project(data)
        logger.debug("Project loaded", project_id=project_id[:8])
        return project

    except Exception as e:
        logger.error("Failed to load project", error=str(e), project_id=project_id[:8])
        return None


def load_project_dict(project_id: str) -> Optional[dict]:
    """파일에서 프로젝트를 딕셔너리로 로드 (API 응답용).

    Args:
        project_id: 프로젝트 ID

    Returns:
        프로젝트 딕셔너리 또는 None
    """
    project = load_project(project_id)
    if project:
        return project_to_dict(project)
    return None


def load_all_projects() -> dict[str, ProjectState]:
    """모든 프로젝트 로드.

    Returns:
        project_id -> ProjectState 딕셔너리
    """
    projects = {}

    try:
        ensure_data_dir()

        for file_path in DATA_DIR.glob("*.json"):
            try:
                project_id = file_path.stem
                project = load_project(project_id)
                if project:
                    projects[project.id] = project

            except Exception as e:
                logger.error("Failed to load project file", file=str(file_path), error=str(e))

        logger.info("All projects loaded", count=len(projects))

    except Exception as e:
        logger.error("Failed to load projects", error=str(e))

    return projects


def load_all_projects_dict() -> dict[str, dict]:
    """모든 프로젝트를 딕셔너리로 로드 (API 응답용).

    Returns:
        project_id -> 프로젝트 딕셔너리
    """
    projects = load_all_projects()
    return {pid: project_to_dict(p) for pid, p in projects.items()}


def delete_project_file(project_id: str) -> bool:
    """프로젝트 파일 및 관련 데이터 폴더 완전 삭제.

    삭제되는 항목:
    - data/projects/{project_id}.json (프로젝트 상태 파일)
    - data/papers/{project_id}/ (논문 폴더 전체)
      - Research Definition.md
      - Experiment Design.md
      - Paper.md
      - Literature Review/*.md

    Args:
        project_id: 프로젝트 ID

    Returns:
        성공 여부
    """
    from backend.storage.paper_files import delete_project_papers_folder

    success = True

    try:
        # 1. 프로젝트 JSON 파일 삭제
        file_path = get_project_path(project_id)
        if file_path.exists():
            file_path.unlink()
            logger.info("Project file deleted", project_id=project_id[:8], path=str(file_path))
        else:
            logger.warning("Project file not found", project_id=project_id[:8])
            success = False

        # 2. 논문 폴더 삭제 (data/papers/{project_id}/)
        papers_deleted = delete_project_papers_folder(project_id)
        if papers_deleted:
            logger.info("Project papers folder deleted", project_id=project_id[:8])

        return success

    except Exception as e:
        logger.error("Failed to delete project", error=str(e), project_id=project_id[:8])
        return False


def create_project(project_id: str, topic: str) -> ProjectState:
    """새 프로젝트 생성.

    Args:
        project_id: 프로젝트 ID
        topic: 프로젝트 주제

    Returns:
        생성된 ProjectState
    """
    now = datetime.utcnow().isoformat()
    papers_folder = f"papers/{project_id}/"

    # 논문 폴더 생성
    ensure_papers_dir(project_id)

    project = ProjectState(
        id=project_id,
        topic=topic,
        created_at=now,
        updated_at=now,
        research_definition_complete=False,
        experiment_design_complete=False,
        processes=ProjectProcesses(
            research_experiment=ResearchExperimentProcess(
                status="active",
                current_phase=ProcessPhase.RESEARCH_DEFINITION,
                messages=[],
                artifact="",
                state=ResearchExperimentState(research_topic=topic)
            ),
            literature_organization=LiteratureOrganizationProcess(
                status=ProcessStatus.UNLOCKED,  # Always unlocked
                papers_folder=papers_folder,
                state=LiteratureOrganizationState()
            ),
            literature_search=LiteratureSearchProcess(
                status=ProcessStatus.LOCKED,  # Locked until RD+ED complete
                state=LiteratureSearchState()
            ),
            paper_writing=PaperWritingProcess(
                status=ProcessStatus.LOCKED,
                messages=[],
                artifact="",
                state=PaperWritingState()
            )
        )
    )

    # 저장
    save_project(project)

    logger.info("Project created", project_id=project_id[:8], topic=topic[:30])
    return project
