"""Literature Search API routes.

v3.1: Web search for academic papers.
- Semantic Scholar, arXiv, Google Scholar search
- Locked until BOTH research_definition_complete AND experiment_design_complete

Note: PDF upload/processing is in literature.py (Literature Organization).
"""
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from backend.orchestrator.state import (
    ProcessStatus,
    PaperEntry,
    PaperType,
    PaperSource,
    PaperStatus,
)
from backend.storage.project_store import (
    save_project,
    project_to_dict,
    dict_to_project,
)
from backend.agents.literature_searcher import LiteratureSearcherAgent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/research/v3", tags=["literature-search"])

# Reference to _projects from main research router (will be set on app startup)
_projects: dict = {}


def set_projects_reference(projects: dict) -> None:
    """Set reference to shared projects dict."""
    global _projects
    _projects = projects


def get_project_v3(project_id: str):
    """Get project as v3 ProjectState model."""
    from backend.orchestrator.state import ProjectState

    if project_id not in _projects:
        return None
    project_data = _projects[project_id]
    # Handle case where project is already a ProjectState object
    if isinstance(project_data, ProjectState):
        return project_data
    return dict_to_project(project_data)


def save_project_v3(project) -> None:
    """Save v3 project to storage."""
    project_dict = project_to_dict(project)
    _projects[project.id] = project_dict
    save_project(project_dict)


def _find_paper_in_organization(project, paper_id: str) -> Optional[PaperEntry]:
    """Find a paper in Literature Organization by ID."""
    for paper in project.processes.literature_organization.state.papers:
        if paper.id == paper_id:
            return paper
    return None


async def download_and_extract_full_text(
    project_id: str,
    paper_id: str,
    pdf_url: str,
) -> None:
    """백그라운드에서 PDF 다운로드 및 텍스트 추출.

    다운로드된 PDF와 추출된 텍스트는 논문 폴더에 저장됩니다:
    - Literature Review/{paper_id}/{paper_id}.pdf
    - Literature Review/{paper_id}/{paper_id}_full_text.txt

    Args:
        project_id: Project ID.
        paper_id: Paper ID in Literature Organization.
        pdf_url: PDF download URL.
    """
    from backend.tools.pdf_processor import PDFProcessor
    from backend.storage.paper_files import (
        save_paper_pdf,
        save_paper_full_text,
        ensure_paper_folder,
    )

    logger.info("Starting PDF download",
               project_id=project_id,
               paper_id=paper_id,
               pdf_url=pdf_url[:100])

    try:
        # 상태 업데이트: DOWNLOADING
        project = get_project_v3(project_id)
        if not project:
            logger.warning("Project not found for PDF download", project_id=project_id)
            return

        paper = _find_paper_in_organization(project, paper_id)
        if not paper:
            logger.warning("Paper not found for PDF download", paper_id=paper_id)
            return

        paper.status = PaperStatus.DOWNLOADING
        save_project_v3(project)

        # 논문 폴더 생성
        ensure_paper_folder(project_id, paper_id)

        # PDF 다운로드
        pdf_processor = PDFProcessor()
        pdf_path = await pdf_processor.download_pdf(pdf_url, f"{paper_id}.pdf")

        if not pdf_path or not pdf_path.exists():
            logger.warning("PDF download failed", paper_id=paper_id, pdf_url=pdf_url[:100])
            # 다운로드 실패해도 수동 처리 가능하도록 PENDING으로 설정
            project = get_project_v3(project_id)
            paper = _find_paper_in_organization(project, paper_id)
            if paper:
                paper.status = PaperStatus.PENDING
                save_project_v3(project)
            return

        # PDF를 논문 폴더에 저장
        saved_pdf_path = save_paper_pdf(project_id, paper_id, pdf_path)
        if saved_pdf_path:
            logger.info("PDF saved to paper folder",
                       paper_id=paper_id,
                       path=str(saved_pdf_path))

        # 텍스트 추출
        try:
            parsed = pdf_processor.parse_pdf(pdf_path)
            full_text = parsed.full_text if parsed else ""
        except Exception as parse_error:
            logger.warning("PDF parsing failed", paper_id=paper_id, error=str(parse_error))
            full_text = ""

        # full_text 업데이트
        project = get_project_v3(project_id)  # 최신 상태 다시 로드
        paper = _find_paper_in_organization(project, paper_id)
        if paper:
            if full_text:
                # 100KB 제한 (약 50페이지 분량)
                paper.full_text = full_text[:100000]
                logger.info("Full text extracted",
                           paper_id=paper_id,
                           text_length=len(paper.full_text))

                # 전체 텍스트를 파일로도 저장
                save_paper_full_text(project_id, paper_id, full_text)

                # 추가 메타데이터 업데이트 (PDF에서 추출된 정보)
                if parsed:
                    if not paper.title and parsed.title:
                        paper.title = parsed.title
                    if not paper.authors and parsed.authors:
                        paper.authors = parsed.authors

            paper.status = PaperStatus.PENDING
            save_project_v3(project)

        # 임시 다운로드 PDF 삭제 (이미 논문 폴더에 복사됨)
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass

    except Exception as e:
        logger.error("PDF download/extraction failed",
                    paper_id=paper_id,
                    error=str(e))
        # 실패해도 상태는 PENDING으로 (수동 처리 가능)
        try:
            project = get_project_v3(project_id)
            paper = _find_paper_in_organization(project, paper_id)
            if paper:
                paper.status = PaperStatus.PENDING
                save_project_v3(project)
        except Exception:
            pass


# =============================================================================
# Request/Response Models
# =============================================================================

class LiteratureSearchStateResponse(BaseModel):
    """Response for Literature Search process state."""

    status: str
    is_locked: bool
    searched_papers: list[dict]


class SearchPapersRequest(BaseModel):
    """Request to search for papers."""

    query: str = Field(description="Search query")
    sources: list[str] = Field(
        default=["semantic_scholar", "arxiv"],
        description="Sources to search (semantic_scholar, arxiv, google_scholar)"
    )
    year_start: int = Field(default=2022, description="Start year for filter")
    year_end: int = Field(default=2026, description="End year for filter")
    limit: int = Field(default=10, description="Max papers per source")


class SearchPapersResponse(BaseModel):
    """Response from paper search."""

    query: str
    total_found: int
    papers: list[dict]
    sources_searched: list[str]


class AddToOrganizationRequest(BaseModel):
    """Request to add a searched paper to Literature Organization."""

    paper_id: str = Field(description="Paper ID from search results")


class AddToOrganizationResponse(BaseModel):
    """Response from adding paper to organization."""

    success: bool
    paper_id: str
    organization_paper_id: str
    message: str


class AutoSearchRequest(BaseModel):
    """Request for automatic search based on RD/ED artifacts."""

    sources: list[str] = Field(
        default=["semantic_scholar", "arxiv"],
        description="Sources to search (semantic_scholar, arxiv, google_scholar)"
    )
    year_start: int = Field(default=2020, description="Start year for filter")
    year_end: int = Field(default=2026, description="End year for filter")
    limit_per_query: int = Field(default=5, description="Max papers per query")


class AutoSearchResponse(BaseModel):
    """Response from automatic search."""

    queries_generated: list[str]
    total_found: int
    papers: list[dict]
    sources_searched: list[str]
    from_research_definition: bool
    from_experiment_design: bool


# =============================================================================
# Literature Search Process Routes (Locked until RD + ED complete)
# =============================================================================

@router.get("/{project_id}/process/literature-search", response_model=LiteratureSearchStateResponse)
async def get_literature_search_process(project_id: str) -> LiteratureSearchStateResponse:
    """Get Literature Search process state.

    Returns lock status and search history.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    process = project.processes.literature_search
    is_locked = not project.is_literature_search_accessible()

    # Debug logging
    logger.info("Getting literature search state",
               project_id=project_id,
               searched_papers_count=len(process.state.searched_papers))

    return LiteratureSearchStateResponse(
        status=process.status.value if hasattr(process.status, 'value') else process.status,
        is_locked=is_locked,
        searched_papers=[p.model_dump() for p in process.state.searched_papers],
    )


@router.post("/{project_id}/process/literature-search/search", response_model=SearchPapersResponse)
async def search_papers(
    project_id: str,
    request: SearchPapersRequest,
) -> SearchPapersResponse:
    """Search for papers across multiple sources.

    Requires Literature Search to be unlocked (both research_definition_complete
    AND experiment_design_complete must be True).
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked (requires BOTH RD and ED complete)
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    # Initialize searcher with requested sources
    use_ss = "semantic_scholar" in request.sources
    use_arxiv = "arxiv" in request.sources
    use_gs = "google_scholar" in request.sources

    searcher = LiteratureSearcherAgent(
        use_semantic_scholar=use_ss,
        use_arxiv=use_arxiv,
        use_google_scholar=use_gs,
    )

    # Perform search
    result = await searcher.search(
        query=request.query,
        keywords=[],
        year_start=request.year_start,
        year_end=request.year_end,
        limit_per_source=request.limit,
        min_citations=0,
    )

    # Clear existing search results and replace with new ones
    project.processes.literature_search.state.searched_papers = []

    # Convert papers to our format and add to searched_papers
    papers_added = []
    for paper in result.papers:
        # Generate unique paper ID
        paper_id = f"search_{len(project.processes.literature_search.state.searched_papers) + 1:03d}"

        # Determine source (case-insensitive comparison)
        source = PaperSource.SEMANTIC_SCHOLAR
        paper_source_lower = paper.source.lower() if paper.source else ""
        if paper_source_lower == "arxiv":
            source = PaperSource.ARXIV
        elif paper_source_lower == "google_scholar" or paper_source_lower == "google scholar":
            source = PaperSource.GOOGLE_SCHOLAR

        paper_entry = PaperEntry(
            id=paper_id,
            type=PaperType.SEARCH,
            title=paper.title,
            authors=paper.authors[:10],  # Limit authors
            year=paper.year,
            source=source,
            pdf_url=paper.pdf_url,
            doi=getattr(paper, 'doi', None),
            url=getattr(paper, 'url', None),
            venue=getattr(paper, 'venue', None),
            citations=getattr(paper, 'citations', 0) or 0,
            categories=getattr(paper, 'categories', []) or [],
            abstract=paper.abstract or "",
            md_file=f"{paper_id}.md",
            status=PaperStatus.PENDING,
        )
        project.processes.literature_search.state.searched_papers.append(paper_entry)
        papers_added.append(paper_entry.model_dump())

    logger.info("Papers converted",
               project_id=project_id,
               papers_converted=len(papers_added),
               total_in_state=len(project.processes.literature_search.state.searched_papers))

    # Save project
    save_project_v3(project)

    # Verify save
    verify_project = get_project_v3(project_id)
    if verify_project:
        logger.info("Papers after save",
                   project_id=project_id,
                   searched_papers_count=len(verify_project.processes.literature_search.state.searched_papers))

    logger.info("Papers searched",
               project_id=project_id,
               query=request.query,
               papers_found=len(papers_added))

    return SearchPapersResponse(
        query=request.query,
        total_found=result.total_found,
        papers=papers_added,
        sources_searched=result.sources_searched,
    )


@router.get("/{project_id}/process/literature-search/papers")
async def list_searched_papers(project_id: str) -> dict:
    """Get all papers found via search."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    papers = project.processes.literature_search.state.searched_papers

    return {
        "total": len(papers),
        "papers": [p.model_dump() for p in papers],
    }


@router.post("/{project_id}/process/literature-search/auto-search", response_model=AutoSearchResponse)
async def auto_search_papers(
    project_id: str,
    request: AutoSearchRequest,
) -> AutoSearchResponse:
    """Automatically search for related papers based on Research Definition and Experiment Design.

    Extracts keywords and research topics from the RD/ED artifacts and performs searches.
    Requires Literature Search to be unlocked (both research_definition_complete
    AND experiment_design_complete must be True).
    """
    from backend.llm.gemini import GeminiLLM

    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    # Get artifacts from research_experiment process
    rd_artifact = project.processes.research_experiment.research_definition_artifact
    ed_artifact = project.processes.research_experiment.experiment_design_artifact

    if not rd_artifact and not ed_artifact:
        raise HTTPException(
            status_code=400,
            detail="No Research Definition or Experiment Design artifacts found. Please complete at least one.",
        )

    # Use LLM to extract search queries from artifacts
    llm = GeminiLLM(model="gemini-2.0-flash")

    artifact_text = ""
    has_rd = bool(rd_artifact)
    has_ed = bool(ed_artifact)

    if rd_artifact:
        artifact_text += f"## Research Definition\n{rd_artifact}\n\n"
    if ed_artifact:
        artifact_text += f"## Experiment Design\n{ed_artifact}\n\n"

    extraction_prompt = f"""Based on the following research artifacts, extract 3-5 specific search queries for finding related academic papers.

{artifact_text}

Requirements:
1. Each query should be specific and academic (suitable for Semantic Scholar or arXiv)
2. Include technical terms, methodologies, and key concepts
3. Focus on the research gap, methodology, and theoretical framework
4. Queries should cover different aspects: theoretical background, methodology, similar studies

Return ONLY a JSON array of search queries, nothing else:
["query1", "query2", "query3", ...]

Example output:
["deep learning anomaly detection industrial IoT", "federated learning privacy preserving", "LSTM time series classification"]
"""

    try:
        response = await llm.generate(extraction_prompt, max_tokens=500)

        # Parse queries from response
        import json
        import re

        # Try to extract JSON array
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if json_match:
            queries = json.loads(json_match.group())
        else:
            # Fallback: split by newlines and clean up
            queries = [q.strip().strip('"\'') for q in response.strip().split('\n') if q.strip()]
            queries = queries[:5]  # Limit to 5

        logger.info("Auto-search queries extracted",
                   project_id=project_id,
                   queries=queries)

    except Exception as e:
        logger.error("Failed to extract search queries", error=str(e))
        # Fallback to basic extraction from topic
        queries = [project.topic] if project.topic else []

    if not queries:
        raise HTTPException(
            status_code=400,
            detail="Could not extract search queries from artifacts.",
        )

    # Initialize searcher with requested sources
    use_ss = "semantic_scholar" in request.sources
    use_arxiv = "arxiv" in request.sources
    use_gs = "google_scholar" in request.sources

    searcher = LiteratureSearcherAgent(
        use_semantic_scholar=use_ss,
        use_arxiv=use_arxiv,
        use_google_scholar=use_gs,
    )

    # Search for each query
    all_papers = []
    all_sources = set()
    total_found = 0

    for query in queries:
        try:
            result = await searcher.search(
                query=query,
                keywords=[],
                year_start=request.year_start,
                year_end=request.year_end,
                limit_per_source=request.limit_per_query,
                min_citations=0,
            )

            total_found += result.total_found
            all_sources.update(result.sources_searched)

            # Add papers (avoiding duplicates)
            existing_titles = {p.title.lower()[:50] for p in all_papers}
            for paper in result.papers:
                title_key = paper.title.lower()[:50]
                if title_key not in existing_titles:
                    existing_titles.add(title_key)
                    all_papers.append(paper)

        except Exception as e:
            logger.warning("Search failed for query", query=query, error=str(e))
            continue

    # Clear existing search results and replace with new ones
    project.processes.literature_search.state.searched_papers = []

    # Convert papers to our format and add to searched_papers
    papers_added = []
    for paper in all_papers:
        # Generate unique paper ID
        paper_id = f"auto_{len(project.processes.literature_search.state.searched_papers) + 1:03d}"

        # Determine source (case-insensitive comparison)
        source = PaperSource.SEMANTIC_SCHOLAR
        paper_source_lower = paper.source.lower() if paper.source else ""
        if paper_source_lower == "arxiv":
            source = PaperSource.ARXIV
        elif paper_source_lower == "google_scholar" or paper_source_lower == "google scholar":
            source = PaperSource.GOOGLE_SCHOLAR

        paper_entry = PaperEntry(
            id=paper_id,
            type=PaperType.SEARCH,
            title=paper.title,
            authors=paper.authors[:10],  # Limit authors
            year=paper.year,
            source=source,
            pdf_url=paper.pdf_url,
            doi=getattr(paper, 'doi', None),
            url=getattr(paper, 'url', None),
            venue=getattr(paper, 'venue', None),
            citations=getattr(paper, 'citations', 0) or 0,
            categories=getattr(paper, 'categories', []) or [],
            abstract=paper.abstract or "",
            md_file=f"{paper_id}.md",
            status=PaperStatus.PENDING,
        )
        project.processes.literature_search.state.searched_papers.append(paper_entry)
        papers_added.append(paper_entry.model_dump())

    logger.info("Auto-search papers converted",
               project_id=project_id,
               papers_converted=len(papers_added),
               total_in_state=len(project.processes.literature_search.state.searched_papers))

    # Save project
    save_project_v3(project)

    # Verify save
    verify_project = get_project_v3(project_id)
    if verify_project:
        logger.info("Auto-search papers after save",
                   project_id=project_id,
                   searched_papers_count=len(verify_project.processes.literature_search.state.searched_papers))

    logger.info("Auto-search completed",
               project_id=project_id,
               queries=queries,
               papers_found=len(papers_added))

    return AutoSearchResponse(
        queries_generated=queries,
        total_found=total_found,
        papers=papers_added,
        sources_searched=list(all_sources),
        from_research_definition=has_rd,
        from_experiment_design=has_ed,
    )


@router.post("/{project_id}/process/literature-search/add-to-organization/{paper_id}", response_model=AddToOrganizationResponse)
async def add_paper_to_organization(
    project_id: str,
    paper_id: str,
    background_tasks: BackgroundTasks,
) -> AddToOrganizationResponse:
    """Add a searched paper to Literature Organization for processing.

    This copies the paper from search results to the organization process,
    where it can be processed (PDF downloaded and converted to MD).

    If pdf_url is available, automatically downloads PDF and extracts full text
    in the background.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    # Find paper in search results
    source_paper = None
    for p in project.processes.literature_search.state.searched_papers:
        if p.id == paper_id:
            source_paper = p
            break

    if not source_paper:
        raise HTTPException(status_code=404, detail="Paper not found in search results")

    # Generate new ID for organization
    org_paper_id = f"paper_{len(project.processes.literature_organization.state.papers) + 1:03d}"

    # Determine initial status based on pdf_url availability
    # If pdf_url exists, we'll download in background
    has_pdf_url = bool(source_paper.pdf_url)
    initial_status = PaperStatus.PENDING_DOWNLOAD if has_pdf_url else PaperStatus.PENDING

    # Create a copy for organization (include all available data including metadata)
    org_paper = PaperEntry(
        id=org_paper_id,
        type=source_paper.type,
        title=source_paper.title,
        authors=source_paper.authors,
        year=source_paper.year,
        source=source_paper.source,
        pdf_url=source_paper.pdf_url,
        doi=source_paper.doi,
        url=source_paper.url,  # Paper URL (e.g., arXiv page)
        venue=source_paper.venue,  # Publication venue/journal
        citations=source_paper.citations,  # Citation count
        categories=source_paper.categories,  # Paper categories/fields
        abstract=source_paper.abstract,
        full_text=source_paper.full_text,  # Copy full_text if available
        md_file=f"{org_paper_id}.md",
        status=initial_status,
    )

    # Add to organization
    project.processes.literature_organization.state.papers.append(org_paper)

    # Save project
    save_project_v3(project)

    # If pdf_url exists, start background download
    if has_pdf_url:
        background_tasks.add_task(
            download_and_extract_full_text,
            project_id,
            org_paper_id,
            source_paper.pdf_url,
        )
        logger.info("Background PDF download scheduled",
                   project_id=project_id,
                   paper_id=org_paper_id,
                   pdf_url=source_paper.pdf_url[:50] if source_paper.pdf_url else "")

    logger.info("Paper added to organization",
               project_id=project_id,
               search_paper_id=paper_id,
               org_paper_id=org_paper_id,
               has_pdf_url=has_pdf_url)

    return AddToOrganizationResponse(
        success=True,
        paper_id=paper_id,
        organization_paper_id=org_paper_id,
        message=f"Paper added to Literature Organization as {org_paper_id}" +
                (" (PDF 다운로드 시작)" if has_pdf_url else ""),
    )


@router.delete("/{project_id}/process/literature-search/papers/{paper_id}")
async def delete_searched_paper(project_id: str, paper_id: str) -> dict:
    """Delete a paper from search results."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    # Find and remove paper
    papers = project.processes.literature_search.state.searched_papers
    paper_index = None
    for i, p in enumerate(papers):
        if p.id == paper_id:
            paper_index = i
            break

    if paper_index is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    removed_paper = papers.pop(paper_index)

    # Save project
    save_project_v3(project)

    logger.info("Searched paper deleted", project_id=project_id, paper_id=paper_id)

    return {
        "status": "deleted",
        "paper_id": paper_id,
        "title": removed_paper.title,
    }


@router.get("/{project_id}/process/literature-search/history")
async def get_search_history(project_id: str) -> dict:
    """Get search history."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if Literature Search is unlocked
    if not project.is_literature_search_accessible():
        raise HTTPException(
            status_code=403,
            detail="Literature Search is locked. Complete both Research Definition and Experiment Design first.",
        )

    history = project.processes.literature_search.state.search_history

    return {
        "total": len(history),
        "history": [h.model_dump() for h in history],
    }


# =============================================================================
# Project Rename (must be in this router due to /api/research/v3 prefix matching)
# =============================================================================


class RenameProjectRequest(BaseModel):
    """Request model for renaming a project."""

    topic: str = Field(min_length=1, max_length=500, description="New project name")


class RenameProjectResponse(BaseModel):
    """Response model for rename operation."""

    project_id: str
    topic: str
    message: str


@router.patch("/{project_id}/rename", response_model=RenameProjectResponse)
async def rename_project(
    project_id: str,
    request: RenameProjectRequest,
) -> RenameProjectResponse:
    """Rename a project.

    This endpoint is here (instead of research.py) because FastAPI's router
    prefix matching prefers the more specific /api/research/v3 prefix.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    old_topic = project.topic
    new_topic = request.topic.strip()

    # Update project topic
    project.topic = new_topic

    # Also update the research_topic in state for consistency
    project.processes.research_experiment.state.research_topic = new_topic

    save_project_v3(project)

    logger.info(
        "Project renamed",
        project_id=project_id,
        old_topic=old_topic,
        new_topic=new_topic,
    )

    return RenameProjectResponse(
        project_id=project_id,
        topic=new_topic,
        message="프로젝트 이름이 변경되었습니다.",
    )
