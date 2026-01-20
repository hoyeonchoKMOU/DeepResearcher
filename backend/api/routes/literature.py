"""Literature Organization API routes.

v3.1: Non-conversational document management for PDF → MD conversion.
- PDF upload and MD conversion (with LLM summarization)
- Master MD auto-generation
- Always unlocked from project creation

Note: Literature Search (web search) is in a separate module.
"""
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
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
from backend.tools.pdf_processor import PDFProcessor
from backend.agents.pdf_summary import PDFSummaryProcessor, FastPDFSummarizer
from backend.storage.paper_files import save_literature_paper, delete_literature_paper

logger = structlog.get_logger(__name__)

# Global PDF processors (lazy initialized)
_pdf_processor: Optional[PDFProcessor] = None
_pdf_summary_processor: Optional[PDFSummaryProcessor] = None
_fast_pdf_summarizer: Optional[FastPDFSummarizer] = None


def get_pdf_processor() -> PDFProcessor:
    """Get or create PDF processor instance."""
    global _pdf_processor
    if _pdf_processor is None:
        _pdf_processor = PDFProcessor()
    return _pdf_processor


def get_pdf_summary_processor() -> PDFSummaryProcessor:
    """Get or create PDF summary processor instance."""
    global _pdf_summary_processor
    if _pdf_summary_processor is None:
        _pdf_summary_processor = PDFSummaryProcessor()
    return _pdf_summary_processor


def get_fast_pdf_summarizer() -> FastPDFSummarizer:
    """Get or create fast PDF summarizer instance (uses Gemini 2.0 Flash)."""
    global _fast_pdf_summarizer
    if _fast_pdf_summarizer is None:
        _fast_pdf_summarizer = FastPDFSummarizer()
    return _fast_pdf_summarizer

router = APIRouter(prefix="/api/research/v3", tags=["literature-organization"])

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


# =============================================================================
# Request/Response Models
# =============================================================================

class LiteratureOrganizationStateResponse(BaseModel):
    """Response for Literature Organization process state."""

    status: str
    is_locked: bool  # Always False for Literature Organization
    papers_folder: str
    papers: list[dict]
    master_md: str


class AddPaperRequest(BaseModel):
    """Request to add a paper manually."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    source: str = Field(default="upload")
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    abstract: str = Field(default="")
    full_text: Optional[str] = Field(default=None, description="Full text of the paper for better summarization")


class PaperResponse(BaseModel):
    """Response with paper details."""

    id: str
    type: str
    title: str
    authors: list[str]
    year: Optional[int]
    source: str
    pdf_url: Optional[str]
    doi: Optional[str]
    abstract: str
    md_file: str
    md_content: str = ""
    status: str
    added_at: str


class ProcessPaperResponse(BaseModel):
    """Response from processing a paper."""

    paper_id: str
    status: str
    md_file: str
    message: str


# =============================================================================
# Literature Organization Process Routes (Always Unlocked)
# =============================================================================

@router.get("/{project_id}/process/literature-organization", response_model=LiteratureOrganizationStateResponse)
async def get_literature_organization_process(project_id: str) -> LiteratureOrganizationStateResponse:
    """Get Literature Organization process state.

    This process is always unlocked from project creation.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    process = project.processes.literature_organization

    return LiteratureOrganizationStateResponse(
        status=process.status.value if hasattr(process.status, 'value') else process.status,
        is_locked=False,  # Always unlocked
        papers_folder=process.papers_folder,
        papers=[p.model_dump() for p in process.state.papers],
        master_md=process.state.master_md,
    )


@router.get("/{project_id}/process/literature-organization/papers")
async def list_papers(project_id: str) -> dict:
    """Get all papers in Literature Organization."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    papers = project.processes.literature_organization.state.papers

    return {
        "total": len(papers),
        "papers": [p.model_dump() for p in papers],
    }


@router.get("/{project_id}/process/literature-organization/papers/{paper_id}", response_model=PaperResponse)
async def get_paper(project_id: str, paper_id: str) -> PaperResponse:
    """Get a specific paper's details."""
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Find paper
    paper = None
    for p in project.processes.literature_organization.state.papers:
        if p.id == paper_id:
            paper = p
            break

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    return PaperResponse(
        id=paper.id,
        type=paper.type.value,
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        source=paper.source.value,
        pdf_url=paper.pdf_url,
        doi=paper.doi,
        abstract=paper.abstract,
        md_file=paper.md_file,
        md_content=paper.md_content,
        status=paper.status.value,
        added_at=paper.added_at,
    )


@router.get("/{project_id}/process/literature-organization/papers/{paper_id}/download")
async def download_paper_md(project_id: str, paper_id: str) -> Response:
    """Download a paper's summary as a markdown file.

    Returns the MD content as a downloadable file.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Find paper
    paper = None
    for p in project.processes.literature_organization.state.papers:
        if p.id == paper_id:
            paper = p
            break

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.md_content:
        raise HTTPException(status_code=404, detail="Paper summary not yet generated")

    # Create safe filename from title
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in paper.title[:50])
    safe_title = safe_title.strip().replace(' ', '_')
    filename = f"{safe_title}_{paper_id}.md"

    return Response(
        content=paper.md_content.encode('utf-8'),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/markdown; charset=utf-8",
        }
    )


@router.post("/{project_id}/process/literature-organization/papers", response_model=PaperResponse)
async def add_paper(
    project_id: str,
    request: AddPaperRequest,
) -> PaperResponse:
    """Manually add a paper to Literature Organization.

    No lock check - always accessible.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # No lock check - Literature Organization is always unlocked

    # Generate unique paper ID
    paper_id = f"paper_{len(project.processes.literature_organization.state.papers) + 1:03d}"

    # Determine source
    source = PaperSource.UPLOAD
    if request.source == "arXiv":
        source = PaperSource.ARXIV
    elif request.source in ["S2", "semantic_scholar"]:
        source = PaperSource.SEMANTIC_SCHOLAR
    elif request.source in ["GS", "google_scholar"]:
        source = PaperSource.GOOGLE_SCHOLAR

    # Create paper entry
    paper_entry = PaperEntry(
        id=paper_id,
        type=PaperType.UPLOAD,
        title=request.title,
        authors=request.authors,
        year=request.year,
        source=source,
        pdf_url=request.pdf_url,
        doi=request.doi,
        abstract=request.abstract,
        full_text=request.full_text,
        md_file=f"{paper_id}.md",
        status=PaperStatus.PENDING,
    )
    project.processes.literature_organization.state.papers.append(paper_entry)

    # Save project
    save_project_v3(project)

    logger.info("Paper added manually", project_id=project_id, paper_id=paper_id)

    return PaperResponse(
        id=paper_entry.id,
        type=paper_entry.type.value,
        title=paper_entry.title,
        authors=paper_entry.authors,
        year=paper_entry.year,
        source=paper_entry.source.value,
        pdf_url=paper_entry.pdf_url,
        doi=paper_entry.doi,
        abstract=paper_entry.abstract,
        md_file=paper_entry.md_file,
        md_content=paper_entry.md_content,
        status=paper_entry.status.value,
        added_at=paper_entry.added_at,
    )


@router.delete("/{project_id}/process/literature-organization/papers/{paper_id}")
async def delete_paper(project_id: str, paper_id: str) -> dict:
    """Delete a paper from Literature Organization.

    No lock check - always accessible.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # No lock check - Literature Organization is always unlocked

    # Find and remove paper
    papers = project.processes.literature_organization.state.papers
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

    # Delete the file
    delete_literature_paper(project_id, paper_id)

    logger.info("Paper deleted", project_id=project_id, paper_id=paper_id)

    return {
        "status": "deleted",
        "paper_id": paper_id,
        "title": removed_paper.title,
    }


class ResetLiteratureRequest(BaseModel):
    """Request to reset Literature Organization."""

    reset_all_papers: bool = Field(default=True, description="Delete all papers")


class ResetLiteratureResponse(BaseModel):
    """Response after resetting Literature Organization."""

    success: bool
    message: str
    deleted_papers_count: int


@router.post("/{project_id}/process/literature-organization/reset", response_model=ResetLiteratureResponse)
async def reset_literature_organization(
    project_id: str,
    request: ResetLiteratureRequest,
) -> ResetLiteratureResponse:
    """Reset Literature Organization (delete all papers).

    Args:
        project_id: Project ID.
        request: Reset options.

    Returns:
        Reset result.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    deleted_count = 0

    if request.reset_all_papers:
        papers = project.processes.literature_organization.state.papers
        deleted_count = len(papers)

        # Delete all paper files
        for paper in papers:
            try:
                delete_literature_paper(project_id, paper.id)
            except Exception as e:
                logger.warning("Failed to delete paper file", paper_id=paper.id, error=str(e))

        # Clear papers list
        project.processes.literature_organization.state.papers = []

    save_project_v3(project)

    message = f"{deleted_count}개의 문헌이 삭제되었습니다." if deleted_count > 0 else "삭제할 문헌이 없습니다."

    logger.info(
        "Literature Organization reset",
        project_id=project_id[:8],
        deleted_count=deleted_count,
    )

    return ResetLiteratureResponse(
        success=True,
        message=message,
        deleted_papers_count=deleted_count,
    )


@router.post("/{project_id}/process/literature-organization/process/{paper_id}", response_model=ProcessPaperResponse)
async def process_paper(project_id: str, paper_id: str, background_tasks: BackgroundTasks) -> ProcessPaperResponse:
    """Process a paper (download PDF and convert to MD).

    This triggers the PDF→MD conversion pipeline using LLM summarization.
    If the paper has a PDF URL, it will be downloaded and processed.
    Otherwise, the metadata (abstract) will be used to generate a summary.

    No lock check - always accessible.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # No lock check - Literature Organization is always unlocked

    # Find paper
    paper = None
    for p in project.processes.literature_organization.state.papers:
        if p.id == paper_id:
            paper = p
            break

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Update status to processing
    paper.status = PaperStatus.PROCESSING
    save_project_v3(project)

    # Schedule background processing
    background_tasks.add_task(
        process_paper_with_llm_background,
        project_id,
        paper_id,
    )

    logger.info("Paper processing started", project_id=project_id, paper_id=paper_id)

    return ProcessPaperResponse(
        paper_id=paper_id,
        status=paper.status.value,
        md_file=paper.md_file,
        message="Paper processing started",
    )


async def process_paper_with_llm_background(project_id: str, paper_id: str):
    """Background task to process a paper with FastPDFSummarizer (Gemini 2.0 Flash).

    This uses the fast summarization pipeline:
    1. Use full_text if available (direct text input)
    2. Otherwise, download PDF from URL (if available)
    3. Extract text using PyMuPDF
    4. Summarize with Gemini 2.0 Flash for speed
    5. Fall back to metadata-based summary if no PDF

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
    """
    logger.info("Starting paper processing (FastPDFSummarizer)", project_id=project_id, paper_id=paper_id)

    try:
        project = get_project_v3(project_id)
        if not project:
            return

        paper = None
        for p in project.processes.literature_organization.state.papers:
            if p.id == paper_id:
                paper = p
                break

        if not paper:
            return

        research_topic = project.topic
        # Get Research Definition for better relevance analysis
        research_definition = project.processes.research_experiment.research_definition_artifact or ""

        # Priority 1: Use full_text if available
        if paper.full_text and len(paper.full_text.strip()) > 100:
            logger.info("Using full_text for summarization", paper_id=paper_id, text_length=len(paper.full_text))
            await _generate_summary_from_metadata(project_id, paper_id, research_topic, research_definition)
            return

        pdf_processor = get_pdf_processor()

        # Priority 2: Try to download and process PDF if URL exists
        if paper.pdf_url:
            logger.info("Downloading PDF", url=paper.pdf_url)
            try:
                pdf_path = await pdf_processor.download_pdf(paper.pdf_url, f"{paper_id}.pdf")
                if pdf_path and pdf_path.exists():
                    # Use FastPDFSummarizer (Gemini 2.0 Flash) for quick summarization
                    fast_summarizer = get_fast_pdf_summarizer()
                    md_content, metadata = await fast_summarizer.summarize_pdf(pdf_path, research_topic, research_definition)

                    # Update paper with extracted data
                    project = get_project_v3(project_id)
                    paper = None
                    for p in project.processes.literature_organization.state.papers:
                        if p.id == paper_id:
                            paper = p
                            break

                    if paper:
                        # Update title if LLM extracted a better one
                        if metadata.get("title") and metadata["title"] != paper.title:
                            paper.title = metadata["title"]

                        # Update authors if extracted
                        if metadata.get("authors") and not paper.authors:
                            paper.authors = metadata["authors"]

                        # Set abstract from summary
                        if metadata.get("summary"):
                            paper.abstract = metadata["summary"]

                        # Add DOI/PDF links to md_content if available
                        if paper.doi or paper.pdf_url:
                            links_section = "\n## 링크 (Links)\n"
                            if paper.doi:
                                links_section += f"- **DOI**: [{paper.doi}](https://doi.org/{paper.doi})\n"
                            if paper.pdf_url:
                                links_section += f"- **PDF**: [PDF 다운로드]({paper.pdf_url})\n"
                            # Insert links section after the first heading
                            if "\n## " in md_content:
                                # Insert after the title heading
                                first_section_idx = md_content.find("\n## ")
                                md_content = md_content[:first_section_idx] + links_section + md_content[first_section_idx:]
                            else:
                                md_content = md_content + "\n" + links_section

                        # Set markdown content
                        paper.md_content = md_content
                        paper.status = PaperStatus.COMPLETED
                        save_project_v3(project)
                        # Save to file
                        save_literature_paper(project_id, paper_id, paper.title, md_content)

                    # Clean up downloaded PDF
                    try:
                        pdf_path.unlink()
                    except:
                        pass

                    logger.info("Paper processed via PDF (FastPDFSummarizer)", project_id=project_id, paper_id=paper_id)
                    return

            except Exception as e:
                logger.warning("PDF download/process failed, falling back to metadata", error=str(e))

        # Fallback: Generate summary from metadata using LLM
        await _generate_summary_from_metadata(project_id, paper_id, research_topic, research_definition)

    except Exception as e:
        logger.error("Paper processing failed", project_id=project_id, paper_id=paper_id, error=str(e))

        # Update status to failed
        try:
            project = get_project_v3(project_id)
            if project:
                for p in project.processes.literature_organization.state.papers:
                    if p.id == paper_id:
                        p.status = PaperStatus.FAILED
                        p.md_content = f"# Processing Failed\n\nError: {str(e)}"
                        break
                save_project_v3(project)
        except:
            pass


async def _generate_summary_from_metadata(project_id: str, paper_id: str, research_topic: str, research_definition: str = ""):
    """Generate a summary from paper metadata or full text using Gemini 2.0 Flash.

    If full_text is available, uses that for more accurate summarization.
    Otherwise, falls back to metadata-based summary.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
        research_topic: Research topic for context.
        research_definition: Full Research Definition content for relevance analysis.
    """
    project = get_project_v3(project_id)
    if not project:
        return

    paper = None
    for p in project.processes.literature_organization.state.papers:
        if p.id == paper_id:
            paper = p
            break

    if not paper:
        return

    try:
        # Use FastPDFSummarizer's text summarization (Gemini 2.0 Flash)
        fast_summarizer = get_fast_pdf_summarizer()

        # Use full_text if available, otherwise build text from metadata
        if paper.full_text and len(paper.full_text.strip()) > 100:
            # Use full text for better summarization
            text = paper.full_text
            logger.info("Using full text for summarization", paper_id=paper_id, text_length=len(text))
        else:
            # Fall back to metadata
            text = f"""Title: {paper.title}
Authors: {', '.join(paper.authors) if paper.authors else 'Unknown'}
Year: {paper.year or 'Unknown'}
Abstract: {paper.abstract or 'No abstract available.'}"""
            logger.info("Using metadata for summarization", paper_id=paper_id)

        response = await fast_summarizer.summarize_text(text, paper.title, research_topic, research_definition)

        # Build markdown content
        authors_str = ", ".join(paper.authors[:5]) if paper.authors else "Unknown"
        if paper.authors and len(paper.authors) > 5:
            authors_str += " et al."

        # Build DOI link
        doi_str = "N/A"
        if paper.doi:
            doi_str = f"[{paper.doi}](https://doi.org/{paper.doi})"

        # Build PDF link
        pdf_str = "N/A"
        if paper.pdf_url:
            pdf_str = f"[PDF 다운로드]({paper.pdf_url})"

        md_content = f"""# {paper.title}

## Metadata
- **Authors**: {authors_str}
- **Year**: {paper.year or 'Unknown'}
- **Source**: {paper.source.value if hasattr(paper.source, 'value') else paper.source}
- **DOI**: {doi_str}
- **PDF**: {pdf_str}

## Abstract
{paper.abstract or 'No abstract available.'}

## AI Analysis

{response}

---
*Processed by DeepResearcher on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*
"""

        paper.md_content = md_content
        paper.status = PaperStatus.COMPLETED
        save_project_v3(project)
        # Save to file
        save_literature_paper(project_id, paper_id, paper.title, md_content)

        logger.info("Paper processed via metadata", project_id=project_id, paper_id=paper_id)

    except Exception as e:
        logger.error("Metadata summary generation failed", error=str(e))

        # Fallback to basic markdown
        authors_str = ", ".join(paper.authors[:5]) if paper.authors else "Unknown"
        if paper.authors and len(paper.authors) > 5:
            authors_str += " et al."

        # Build DOI link
        doi_str = "N/A"
        if paper.doi:
            doi_str = f"[{paper.doi}](https://doi.org/{paper.doi})"

        # Build PDF link
        pdf_str = "N/A"
        if paper.pdf_url:
            pdf_str = f"[PDF 다운로드]({paper.pdf_url})"

        fallback_md = f"""# {paper.title}

## Metadata
- **Authors**: {authors_str}
- **Year**: {paper.year or 'Unknown'}
- **Source**: {paper.source.value if hasattr(paper.source, 'value') else paper.source}
- **DOI**: {doi_str}
- **PDF**: {pdf_str}

## Abstract
{paper.abstract or 'No abstract available.'}

## Note
LLM summarization was not available. This is a basic summary based on paper metadata.

---
*Processed by DeepResearcher on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*
"""
        paper.md_content = fallback_md
        paper.status = PaperStatus.COMPLETED
        save_project_v3(project)
        # Save to file
        save_literature_paper(project_id, paper_id, paper.title, fallback_md)


@router.get("/{project_id}/process/literature-organization/master")
async def get_master_md(project_id: str) -> dict:
    """Get the master MD file content (reference list).

    Returns auto-generated master reference document.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    papers = project.processes.literature_organization.state.papers
    topic = project.topic

    # Generate master MD content
    search_papers = [p for p in papers if p.type == PaperType.SEARCH]
    upload_papers = [p for p in papers if p.type == PaperType.UPLOAD]

    md_content = f"""# Literature Reference List

## Project Information
- **Research Topic**: {topic}
- **Generated At**: {datetime.utcnow().isoformat()}
- **Total Papers**: {len(papers)}

---

## Searched Papers ({len(search_papers)} papers)

| # | Title | Authors | Year | Source | Status |
|---|-------|---------|------|--------|--------|
"""

    for i, paper in enumerate(search_papers, 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += "..."
        md_content += f"| {i} | {paper.title[:50]}... | {authors_str} | {paper.year or 'N/A'} | {paper.source.value} | {paper.status.value} |\n"

    md_content += f"""
---

## Uploaded Papers ({len(upload_papers)} papers)

| # | Title | Authors | Year | Status |
|---|-------|---------|------|--------|
"""

    for i, paper in enumerate(upload_papers, 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += "..."
        md_content += f"| {i} | {paper.title[:50]}... | {authors_str} | {paper.year or 'N/A'} | {paper.status.value} |\n"

    md_content += """
---
*Generated by DeepResearcher*
"""

    return {
        "filename": project.processes.literature_organization.state.master_md,
        "content": md_content,
        "total_papers": len(papers),
        "search_papers": len(search_papers),
        "upload_papers": len(upload_papers),
    }


async def process_uploaded_pdf_background(
    project_id: str,
    paper_id: str,
    pdf_content: bytes,
    original_filename: str,
):
    """Background task to process uploaded PDF with FastPDFSummarizer (Gemini 2.0 Flash).

    This uses the fast summarization pipeline:
    1. Extract text from PDF using PyMuPDF
    2. Clean and normalize the text
    3. Summarize with Gemini 2.0 Flash for speed

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
        pdf_content: PDF file content bytes.
        original_filename: Original filename for temp file.
    """
    logger.info("Starting background PDF processing (FastPDFSummarizer)", project_id=project_id, paper_id=paper_id)

    try:
        # Get project and paper
        project = get_project_v3(project_id)
        if not project:
            logger.error("Project not found in background task", project_id=project_id)
            return

        paper = None
        for p in project.processes.literature_organization.state.papers:
            if p.id == paper_id:
                paper = p
                break

        if not paper:
            logger.error("Paper not found in background task", paper_id=paper_id)
            return

        # Update status to processing
        paper.status = PaperStatus.PROCESSING
        save_project_v3(project)

        # Save PDF to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(pdf_content)
            tmp_path = Path(tmp_file.name)

        try:
            # Get research topic for context
            research_topic = project.topic

            # Use FastPDFSummarizer (Gemini 2.0 Flash) for quick summarization
            fast_summarizer = get_fast_pdf_summarizer()
            md_content, metadata = await fast_summarizer.summarize_pdf(tmp_path, research_topic)

            # Re-fetch project to avoid stale state
            project = get_project_v3(project_id)
            paper = None
            for p in project.processes.literature_organization.state.papers:
                if p.id == paper_id:
                    paper = p
                    break

            if not paper:
                return

            # Update paper with extracted metadata
            if metadata.get("title") and metadata["title"] != original_filename.replace(".pdf", ""):
                paper.title = metadata["title"]

            if metadata.get("authors"):
                paper.authors = metadata["authors"]

            if metadata.get("summary"):
                paper.abstract = metadata["summary"]

            # Set markdown content
            paper.md_content = md_content
            paper.status = PaperStatus.COMPLETED

            logger.info("PDF processed successfully with FastPDFSummarizer",
                       project_id=project_id,
                       paper_id=paper_id,
                       title=paper.title[:50] if paper.title else "Unknown")

        finally:
            # Clean up temp file
            try:
                tmp_path.unlink()
            except:
                pass

        save_project_v3(project)
        # Save to file
        if paper.md_content:
            save_literature_paper(project_id, paper_id, paper.title, paper.md_content)

    except Exception as e:
        logger.error("PDF processing failed", project_id=project_id, paper_id=paper_id, error=str(e))

        # Update status to failed
        try:
            project = get_project_v3(project_id)
            if project:
                for p in project.processes.literature_organization.state.papers:
                    if p.id == paper_id:
                        p.status = PaperStatus.FAILED
                        p.md_content = f"# Processing Failed\n\nError: {str(e)}"
                        break
                save_project_v3(project)
        except:
            pass


def _generate_summary_markdown(summary_output) -> str:
    """Generate markdown from PDFSummaryOutput.

    Args:
        summary_output: PDFSummaryOutput object.

    Returns:
        Formatted markdown string.
    """
    lines = []

    # Title
    lines.append(f"# {summary_output.title or 'Untitled Paper'}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    if summary_output.authors:
        lines.append(f"- **Authors**: {', '.join(summary_output.authors)}")
    if summary_output.year:
        lines.append(f"- **Year**: {summary_output.year}")
    if summary_output.venue:
        lines.append(f"- **Venue**: {summary_output.venue}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(summary_output.abstract_summary or "No summary available.")
    lines.append("")

    # Problem Statement
    if summary_output.problem_statement:
        lines.append("## Problem Statement")
        lines.append(summary_output.problem_statement)
        lines.append("")

    # Key Contributions
    if summary_output.key_contributions:
        lines.append("## Key Contributions")
        for contrib in summary_output.key_contributions:
            lines.append(f"### {contrib.type.title() if hasattr(contrib, 'type') else 'Contribution'}")
            lines.append(f"- {contrib.contribution if hasattr(contrib, 'contribution') else str(contrib)}")
            if hasattr(contrib, 'significance') and contrib.significance:
                lines.append(f"- **Significance**: {contrib.significance}")
            lines.append("")

    # Methodology
    if summary_output.methodology:
        lines.append("## Methodology")
        method = summary_output.methodology
        if hasattr(method, 'approach') and method.approach:
            lines.append(f"**Approach**: {method.approach}")
        if hasattr(method, 'techniques') and method.techniques:
            lines.append(f"**Techniques**: {', '.join(method.techniques)}")
        if hasattr(method, 'datasets') and method.datasets:
            lines.append(f"**Datasets**: {', '.join(method.datasets)}")
        if hasattr(method, 'evaluation_metrics') and method.evaluation_metrics:
            lines.append(f"**Metrics**: {', '.join(method.evaluation_metrics)}")
        lines.append("")

    # Main Results
    if summary_output.main_results:
        lines.append("## Main Results")
        for result in summary_output.main_results:
            lines.append(f"- {result}")
        lines.append("")

    # Limitations
    if summary_output.limitations:
        lines.append("## Limitations")
        for limitation in summary_output.limitations:
            lines.append(f"- {limitation}")
        lines.append("")

    # Relevance
    if summary_output.relevance_to_research:
        lines.append("## Relevance to Our Research")
        lines.append(summary_output.relevance_to_research)
        lines.append("")

    # Quality Assessment
    if summary_output.quality_assessment:
        lines.append("## Quality Assessment")
        lines.append(summary_output.quality_assessment)
        lines.append("")

    # Timestamp
    lines.append("---")
    lines.append(f"*Processed by DeepResearcher on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*")

    return "\n".join(lines)


@router.post("/{project_id}/process/literature-organization/upload")
async def upload_paper_pdf(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    authors: str = Form(default=""),
) -> PaperResponse:
    """Upload a PDF file to add as a paper.

    The PDF will be automatically processed with LLM to extract title and generate summary.

    No lock check - always accessible.
    """
    project = get_project_v3(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # No lock check - Literature Organization is always unlocked

    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read PDF content
    pdf_content = await file.read()

    # Generate unique paper ID
    paper_id = f"upload_{len(project.processes.literature_organization.state.papers) + 1:03d}"

    # Parse authors
    authors_list = [a.strip() for a in authors.split(",")] if authors else []

    # Create paper entry with processing status
    paper_entry = PaperEntry(
        id=paper_id,
        type=PaperType.UPLOAD,
        title=title or file.filename.replace(".pdf", ""),
        authors=authors_list,
        year=None,
        source=PaperSource.UPLOAD,
        pdf_url=None,
        doi=None,
        abstract="Processing...",
        md_file=f"{paper_id}.md",
        status=PaperStatus.PROCESSING,  # Start as processing
    )
    project.processes.literature_organization.state.papers.append(paper_entry)

    # Save project
    save_project_v3(project)

    # Schedule background PDF processing
    background_tasks.add_task(
        process_uploaded_pdf_background,
        project_id,
        paper_id,
        pdf_content,
        file.filename,
    )

    logger.info("Paper uploaded, processing started", project_id=project_id, paper_id=paper_id, filename=file.filename)

    return PaperResponse(
        id=paper_entry.id,
        type=paper_entry.type.value,
        title=paper_entry.title,
        authors=paper_entry.authors,
        year=paper_entry.year,
        source=paper_entry.source.value,
        pdf_url=paper_entry.pdf_url,
        doi=paper_entry.doi,
        abstract=paper_entry.abstract,
        md_file=paper_entry.md_file,
        md_content=paper_entry.md_content,
        status=paper_entry.status.value,
        added_at=paper_entry.added_at,
    )
