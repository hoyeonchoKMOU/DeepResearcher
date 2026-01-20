"""Paper file storage service.

Manages markdown files for research artifacts:
- data/papers/{project_id}/
  - Research Definition.md
  - Experiment Design.md
  - Paper.md
  - Literature Review/
    - {paper_id}.md
"""
from pathlib import Path
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Base directory for paper files (absolute path for consistency)
PAPERS_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "papers"


def get_project_papers_dir(project_id: str) -> Path:
    """Get the papers directory for a project.

    Args:
        project_id: Project ID.

    Returns:
        Path to the project's papers directory.
    """
    return PAPERS_BASE_DIR / project_id


def get_literature_review_dir(project_id: str) -> Path:
    """Get the Literature Review directory for a project.

    Args:
        project_id: Project ID.

    Returns:
        Path to the project's Literature Review directory.
    """
    return get_project_papers_dir(project_id) / "Literature Review"


def get_paper_folder(project_id: str, paper_id: str) -> Path:
    """Get the folder for a specific paper.

    Each paper has its own subfolder containing:
    - {paper_id}_summary.md (generated summary)
    - {paper_id}.pdf (downloaded PDF, if available)
    - {paper_id}_full_text.txt (extracted full text, if available)

    Args:
        project_id: Project ID.
        paper_id: Paper ID.

    Returns:
        Path to the paper's folder.
    """
    return get_literature_review_dir(project_id) / paper_id


def ensure_paper_folder(project_id: str, paper_id: str) -> Path:
    """Ensure the paper folder exists.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.

    Returns:
        Path to the paper's folder.
    """
    paper_folder = get_paper_folder(project_id, paper_id)
    paper_folder.mkdir(parents=True, exist_ok=True)
    return paper_folder


def ensure_project_dirs(project_id: str) -> None:
    """Ensure all directories exist for a project.

    Args:
        project_id: Project ID.
    """
    project_dir = get_project_papers_dir(project_id)
    lit_review_dir = get_literature_review_dir(project_id)

    project_dir.mkdir(parents=True, exist_ok=True)
    lit_review_dir.mkdir(parents=True, exist_ok=True)

    logger.debug("Ensured project directories", project_id=project_id, path=str(project_dir))


def save_research_definition(project_id: str, content: str) -> Path:
    """Save Research Definition markdown file.

    Args:
        project_id: Project ID.
        content: Markdown content.

    Returns:
        Path to the saved file.
    """
    ensure_project_dirs(project_id)
    file_path = get_project_papers_dir(project_id) / "Research Definition.md"

    file_path.write_text(content, encoding="utf-8")
    logger.info("Saved Research Definition", project_id=project_id, path=str(file_path))

    return file_path


def save_experiment_design(project_id: str, content: str) -> Path:
    """Save Experiment Design markdown file.

    Args:
        project_id: Project ID.
        content: Markdown content.

    Returns:
        Path to the saved file.
    """
    ensure_project_dirs(project_id)
    file_path = get_project_papers_dir(project_id) / "Experiment Design.md"

    file_path.write_text(content, encoding="utf-8")
    logger.info("Saved Experiment Design", project_id=project_id, path=str(file_path))

    return file_path


def save_paper_draft(project_id: str, content: str) -> Path:
    """Save Paper draft markdown file.

    Args:
        project_id: Project ID.
        content: Markdown content.

    Returns:
        Path to the saved file.
    """
    ensure_project_dirs(project_id)
    file_path = get_project_papers_dir(project_id) / "Paper.md"

    file_path.write_text(content, encoding="utf-8")
    logger.info("Saved Paper draft", project_id=project_id, path=str(file_path))

    return file_path


def save_literature_paper(project_id: str, paper_id: str, title: str, content: str) -> Path:
    """Save a literature review paper markdown file.

    Saves to: Literature Review/{paper_id}/{paper_id}_{title}.md

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
        title: Paper title (used for filename).
        content: Markdown content.

    Returns:
        Path to the saved file.
    """
    paper_folder = ensure_paper_folder(project_id, paper_id)

    # Sanitize title for filename
    safe_title = sanitize_filename(title)
    filename = f"{paper_id}_{safe_title}.md"

    file_path = paper_folder / filename
    file_path.write_text(content, encoding="utf-8")

    logger.info("Saved literature paper", project_id=project_id, paper_id=paper_id, path=str(file_path))

    return file_path


def save_paper_pdf(project_id: str, paper_id: str, pdf_path: Path) -> Optional[Path]:
    """Save/move a PDF file to the paper's folder.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
        pdf_path: Source PDF path.

    Returns:
        Path to the saved PDF or None if failed.
    """
    import shutil

    if not pdf_path.exists():
        return None

    paper_folder = ensure_paper_folder(project_id, paper_id)
    dest_path = paper_folder / f"{paper_id}.pdf"

    try:
        shutil.copy2(pdf_path, dest_path)
        logger.info("Saved paper PDF", project_id=project_id, paper_id=paper_id, path=str(dest_path))
        return dest_path
    except Exception as e:
        logger.error("Failed to save paper PDF", error=str(e))
        return None


def save_paper_full_text(project_id: str, paper_id: str, full_text: str) -> Optional[Path]:
    """Save extracted full text to the paper's folder.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.
        full_text: Extracted full text.

    Returns:
        Path to the saved text file or None if failed.
    """
    if not full_text or len(full_text) < 100:
        return None

    paper_folder = ensure_paper_folder(project_id, paper_id)
    text_path = paper_folder / f"{paper_id}_full_text.txt"

    try:
        text_path.write_text(full_text, encoding="utf-8")
        logger.info("Saved paper full text",
                   project_id=project_id,
                   paper_id=paper_id,
                   text_length=len(full_text))
        return text_path
    except Exception as e:
        logger.error("Failed to save full text", error=str(e))
        return None


def get_paper_pdf_path(project_id: str, paper_id: str) -> Optional[Path]:
    """Get the path to a paper's PDF file.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.

    Returns:
        Path to the PDF or None if not found.
    """
    pdf_path = get_paper_folder(project_id, paper_id) / f"{paper_id}.pdf"
    return pdf_path if pdf_path.exists() else None


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Sanitize a string for use as a filename.

    Args:
        name: Original name.
        max_length: Maximum length.

    Returns:
        Sanitized filename-safe string.
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '')

    # Replace spaces and other problematic chars
    name = name.replace(' ', '_')
    name = name.strip('._')

    # Truncate
    if len(name) > max_length:
        name = name[:max_length]

    return name or "untitled"


def read_research_definition(project_id: str) -> Optional[str]:
    """Read Research Definition markdown file.

    Args:
        project_id: Project ID.

    Returns:
        File content or None if not found.
    """
    file_path = get_project_papers_dir(project_id) / "Research Definition.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def read_experiment_design(project_id: str) -> Optional[str]:
    """Read Experiment Design markdown file.

    Args:
        project_id: Project ID.

    Returns:
        File content or None if not found.
    """
    file_path = get_project_papers_dir(project_id) / "Experiment Design.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def read_paper_draft(project_id: str) -> Optional[str]:
    """Read Paper draft markdown file.

    Args:
        project_id: Project ID.

    Returns:
        File content or None if not found.
    """
    file_path = get_project_papers_dir(project_id) / "Paper.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def read_literature_paper(project_id: str, paper_id: str) -> Optional[str]:
    """Read a literature review paper markdown file.

    Args:
        project_id: Project ID.
        paper_id: Paper ID.

    Returns:
        File content or None if not found.
    """
    lit_dir = get_literature_review_dir(project_id)
    if not lit_dir.exists():
        return None

    # Find file by paper_id prefix
    for file_path in lit_dir.glob(f"{paper_id}_*.md"):
        return file_path.read_text(encoding="utf-8")

    return None


def list_literature_papers(project_id: str) -> list[dict]:
    """List all literature review papers for a project.

    Supports both old flat structure and new folder structure.

    Args:
        project_id: Project ID.

    Returns:
        List of paper info dicts with 'paper_id', 'filename', 'path', 'has_pdf', 'has_full_text'.
    """
    lit_dir = get_literature_review_dir(project_id)
    if not lit_dir.exists():
        return []

    papers = []

    # Check for new folder structure (subfolders for each paper)
    for item in sorted(lit_dir.iterdir()):
        if item.is_dir():
            # New structure: Literature Review/{paper_id}/
            paper_id = item.name

            # Find MD file in folder
            md_files = list(item.glob("*.md"))
            if md_files:
                md_file = md_files[0]
                papers.append({
                    "paper_id": paper_id,
                    "filename": md_file.name,
                    "path": str(md_file),
                    "folder_path": str(item),
                    "has_pdf": (item / f"{paper_id}.pdf").exists(),
                    "has_full_text": (item / f"{paper_id}_full_text.txt").exists(),
                })
        elif item.suffix == ".md":
            # Old structure: Literature Review/{paper_id}_{title}.md
            filename = item.stem
            parts = filename.split("_", 1)
            paper_id = parts[0] if parts else filename

            papers.append({
                "paper_id": paper_id,
                "filename": item.name,
                "path": str(item),
                "folder_path": None,
                "has_pdf": False,
                "has_full_text": False,
            })

    return papers


def delete_literature_paper(project_id: str, paper_id: str) -> bool:
    """Delete a literature review paper and all its associated files.

    Deletes:
    - Paper folder (if using new structure)
    - MD file, PDF file, full text file
    - Or legacy flat MD file

    Args:
        project_id: Project ID.
        paper_id: Paper ID.

    Returns:
        True if deleted, False if not found.
    """
    import shutil

    lit_dir = get_literature_review_dir(project_id)
    if not lit_dir.exists():
        return False

    deleted = False

    # Try new folder structure first
    paper_folder = get_paper_folder(project_id, paper_id)
    if paper_folder.exists():
        try:
            shutil.rmtree(paper_folder)
            logger.info("Deleted paper folder",
                       project_id=project_id,
                       paper_id=paper_id,
                       path=str(paper_folder))
            deleted = True
        except Exception as e:
            logger.error("Failed to delete paper folder", error=str(e))
            # Try deleting files individually
            for file_path in paper_folder.glob("*"):
                try:
                    file_path.unlink()
                    deleted = True
                except Exception:
                    pass
            try:
                paper_folder.rmdir()
            except Exception:
                pass

    # Also try legacy flat structure
    for file_path in lit_dir.glob(f"{paper_id}_*.md"):
        try:
            file_path.unlink()
            logger.info("Deleted legacy literature paper",
                       project_id=project_id,
                       paper_id=paper_id)
            deleted = True
        except Exception as e:
            logger.error("Failed to delete legacy paper file", error=str(e))

    return deleted


def delete_project_papers_folder(project_id: str, max_retries: int = 3) -> bool:
    """Delete the entire papers folder for a project.

    This removes all markdown files including:
    - Research Definition.md
    - Experiment Design.md
    - Paper.md
    - Literature Review/ folder and all its contents

    Handles OneDrive sync locks and Windows permission issues.

    Args:
        project_id: Project ID.
        max_retries: Maximum retry attempts (default 3).

    Returns:
        True if deleted, False if folder didn't exist or deletion failed.
    """
    import shutil
    import time
    import gc
    import stat
    import os

    project_dir = get_project_papers_dir(project_id)

    if not project_dir.exists():
        logger.debug("Project papers folder does not exist", project_id=project_id)
        return False

    def force_remove_readonly(func, path, exc_info):
        """Error handler for shutil.rmtree to handle readonly files (OneDrive issue)."""
        try:
            # Remove readonly attribute
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            logger.warning("force_remove_readonly failed", path=path, error=str(e))

    def delete_contents_first(folder: Path) -> bool:
        """Delete folder contents individually before removing folder."""
        try:
            # Delete all files first
            for item in list(folder.rglob("*")):
                if item.is_file():
                    try:
                        item.chmod(stat.S_IWRITE)
                        item.unlink()
                    except Exception as e:
                        logger.warning("Failed to delete file", path=str(item), error=str(e))

            # Delete empty subdirectories (deepest first)
            for item in sorted(folder.rglob("*"), key=lambda x: len(x.parts), reverse=True):
                if item.is_dir():
                    try:
                        item.rmdir()
                    except Exception as e:
                        logger.warning("Failed to delete dir", path=str(item), error=str(e))

            # Finally delete the main folder
            folder.rmdir()
            return True
        except Exception as e:
            logger.warning("delete_contents_first failed", error=str(e))
            return False

    # Force garbage collection to release any file handles
    gc.collect()

    for attempt in range(max_retries):
        try:
            # Try with onerror handler for readonly files
            shutil.rmtree(project_dir, onerror=force_remove_readonly)
            if not project_dir.exists():
                logger.info("Deleted project papers folder",
                           project_id=project_id,
                           path=str(project_dir),
                           attempt=attempt + 1)
                return True

        except PermissionError as e:
            logger.warning("Permission error deleting papers folder",
                          project_id=project_id,
                          attempt=attempt + 1,
                          error=str(e))

        except Exception as e:
            logger.warning("Failed to delete project papers folder",
                        project_id=project_id,
                        attempt=attempt + 1,
                        error=str(e))

        # Wait and retry
        if attempt < max_retries - 1:
            time.sleep(0.5 * (attempt + 1))  # Increasing delay
            gc.collect()

    # Fallback: try deleting contents individually
    logger.info("Trying individual file deletion", project_id=project_id)
    if delete_contents_first(project_dir):
        logger.info("Deleted project papers folder (individual deletion)",
                   project_id=project_id)
        return True

    # Final check
    if not project_dir.exists():
        logger.info("Project papers folder was deleted", project_id=project_id)
        return True

    # Log what's remaining
    remaining = list(project_dir.rglob("*")) if project_dir.exists() else []
    logger.error("Failed to fully delete papers folder after all attempts",
                project_id=project_id,
                folder_exists=project_dir.exists(),
                remaining_count=len(remaining))
    return False


def get_project_files_summary(project_id: str) -> dict:
    """Get a summary of all files for a project.

    Args:
        project_id: Project ID.

    Returns:
        Summary dict with file existence and counts.
    """
    project_dir = get_project_papers_dir(project_id)

    research_def = project_dir / "Research Definition.md"
    experiment_design = project_dir / "Experiment Design.md"
    paper_draft = project_dir / "Paper.md"

    lit_papers = list_literature_papers(project_id)

    return {
        "project_id": project_id,
        "base_path": str(project_dir),
        "files": {
            "research_definition": {
                "exists": research_def.exists(),
                "path": str(research_def) if research_def.exists() else None,
            },
            "experiment_design": {
                "exists": experiment_design.exists(),
                "path": str(experiment_design) if experiment_design.exists() else None,
            },
            "paper_draft": {
                "exists": paper_draft.exists(),
                "path": str(paper_draft) if paper_draft.exists() else None,
            },
            "literature_review": {
                "count": len(lit_papers),
                "papers": lit_papers,
            },
        },
    }
