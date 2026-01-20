"""PDF processing tool for downloading and parsing academic papers."""

import re
from pathlib import Path
from typing import Optional

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class PDFSection(BaseModel):
    """Represents a section of a PDF document."""

    title: str = Field(description="Section title")
    content: str = Field(description="Section content text")
    page_start: int = Field(default=1, description="Starting page number")
    page_end: int = Field(default=1, description="Ending page number")


class ParsedPDF(BaseModel):
    """Parsed PDF document."""

    title: str = Field(default="", description="Document title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    abstract: str = Field(default="", description="Paper abstract")
    full_text: str = Field(default="", description="Full extracted text")
    sections: list[PDFSection] = Field(default_factory=list, description="Parsed sections")
    page_count: int = Field(default=0, description="Total page count")
    metadata: dict = Field(default_factory=dict, description="PDF metadata")


class PDFProcessor:
    """Process PDF files for academic papers."""

    # Common section headers in academic papers
    SECTION_PATTERNS = [
        r"(?i)^abstract\s*$",
        r"(?i)^introduction\s*$",
        r"(?i)^(?:\d+\.?\s*)?background\s*$",
        r"(?i)^(?:\d+\.?\s*)?related\s+work\s*$",
        r"(?i)^(?:\d+\.?\s*)?literature\s+review\s*$",
        r"(?i)^(?:\d+\.?\s*)?method(?:s|ology)?\s*$",
        r"(?i)^(?:\d+\.?\s*)?approach\s*$",
        r"(?i)^(?:\d+\.?\s*)?experiment(?:s|al)?\s*(?:setup|design)?\s*$",
        r"(?i)^(?:\d+\.?\s*)?result(?:s)?\s*$",
        r"(?i)^(?:\d+\.?\s*)?evaluation\s*$",
        r"(?i)^(?:\d+\.?\s*)?discussion\s*$",
        r"(?i)^(?:\d+\.?\s*)?conclusion(?:s)?\s*$",
        r"(?i)^(?:\d+\.?\s*)?future\s+work\s*$",
        r"(?i)^(?:\d+\.?\s*)?acknowledgment(?:s)?\s*$",
        r"(?i)^(?:\d+\.?\s*)?references\s*$",
        r"(?i)^(?:\d+\.?\s*)?appendix\s*$",
    ]

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize PDF processor.

        Args:
            storage_dir: Directory to store downloaded PDFs.
        """
        self.storage_dir = storage_dir or Path("./papers")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def download_pdf(
        self,
        url: str,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """Download PDF from URL.

        Args:
            url: PDF URL.
            filename: Optional filename to save as.

        Returns:
            Path to downloaded file or None if failed.
        """
        if not filename:
            # Extract filename from URL
            filename = url.split("/")[-1]
            if not filename.endswith(".pdf"):
                filename = f"{filename}.pdf"

        filepath = self.storage_dir / filename

        logger.info("Downloading PDF", url=url, path=str(filepath))

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                    logger.warning("Response may not be a PDF", content_type=content_type)

                with open(filepath, "wb") as f:
                    f.write(response.content)

                logger.info("PDF downloaded", path=str(filepath), size=len(response.content))
                return filepath

            except httpx.HTTPError as e:
                logger.error("Failed to download PDF", url=url, error=str(e))
                return None

    def parse_pdf(self, filepath: Path) -> ParsedPDF:
        """Parse PDF file and extract text and structure.

        Args:
            filepath: Path to PDF file.

        Returns:
            ParsedPDF with extracted content.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed. Run: pip install pymupdf")
            return ParsedPDF(full_text="Error: PyMuPDF not installed")

        logger.info("Parsing PDF", path=str(filepath))

        try:
            doc = fitz.open(filepath)
        except Exception as e:
            logger.error("Failed to open PDF", path=str(filepath), error=str(e))
            return ParsedPDF(full_text=f"Error opening PDF: {str(e)}")

        # Extract metadata
        metadata = doc.metadata or {}

        # Extract text from all pages
        full_text = ""
        page_texts = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            page_texts.append(text)
            full_text += text + "\n\n"

        # Try to extract title (usually first large text on first page)
        title = metadata.get("title", "")
        if not title and page_texts:
            # Try to get title from first page
            first_lines = page_texts[0].split("\n")[:5]
            for line in first_lines:
                line = line.strip()
                if len(line) > 10 and len(line) < 200:
                    title = line
                    break

        # Try to extract authors
        authors = []
        author_str = metadata.get("author", "")
        if author_str:
            # Split by common separators
            authors = re.split(r"[,;]", author_str)
            authors = [a.strip() for a in authors if a.strip()]

        # Extract abstract
        abstract = self._extract_abstract(full_text)

        # Parse sections
        sections = self._parse_sections(full_text, page_texts)

        doc.close()

        logger.info(
            "PDF parsed",
            title=title[:50] if title else "Unknown",
            pages=len(page_texts),
            sections=len(sections),
        )

        return ParsedPDF(
            title=title,
            authors=authors,
            abstract=abstract,
            full_text=full_text,
            sections=sections,
            page_count=len(page_texts),
            metadata=metadata,
        )

    def _extract_abstract(self, text: str) -> str:
        """Extract abstract from text.

        Args:
            text: Full document text.

        Returns:
            Extracted abstract or empty string.
        """
        # Look for "Abstract" section
        abstract_match = re.search(
            r"(?i)abstract\s*\n+(.*?)(?=\n\s*(?:introduction|keywords|1\.|I\.))",
            text,
            re.DOTALL,
        )

        if abstract_match:
            abstract = abstract_match.group(1).strip()
            # Clean up
            abstract = re.sub(r"\s+", " ", abstract)
            return abstract[:2000]  # Limit length

        return ""

    def _parse_sections(
        self,
        full_text: str,
        page_texts: list[str],
    ) -> list[PDFSection]:
        """Parse document into sections.

        Args:
            full_text: Full document text.
            page_texts: Text by page.

        Returns:
            List of parsed sections.
        """
        sections = []
        lines = full_text.split("\n")

        current_section = None
        current_content = []

        for line in lines:
            line_stripped = line.strip()

            # Check if this line is a section header
            is_header = False
            for pattern in self.SECTION_PATTERNS:
                if re.match(pattern, line_stripped):
                    is_header = True
                    break

            if is_header:
                # Save previous section
                if current_section:
                    sections.append(PDFSection(
                        title=current_section,
                        content="\n".join(current_content).strip(),
                    ))

                current_section = line_stripped
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections.append(PDFSection(
                title=current_section,
                content="\n".join(current_content).strip(),
            ))

        return sections

    def extract_references(self, text: str) -> list[str]:
        """Extract references from text.

        Args:
            text: Document text.

        Returns:
            List of reference strings.
        """
        # Find references section
        ref_match = re.search(
            r"(?i)references\s*\n+(.*?)(?=\n\s*(?:appendix|$))",
            text,
            re.DOTALL,
        )

        if not ref_match:
            return []

        ref_text = ref_match.group(1)

        # Try to split by common reference patterns
        # [1], [2], etc.
        refs = re.split(r"\[\d+\]", ref_text)

        # If that doesn't work, try numbered lists
        if len(refs) <= 1:
            refs = re.split(r"\n\d+\.", ref_text)

        # Clean up
        references = []
        for ref in refs:
            ref = ref.strip()
            ref = re.sub(r"\s+", " ", ref)
            if len(ref) > 20:  # Minimum length for a reference
                references.append(ref)

        return references


class MarkdownFormatter:
    """Format parsed PDF content as Markdown."""

    @staticmethod
    def format_paper_summary(
        paper: ParsedPDF,
        relevance_notes: str = "",
    ) -> str:
        """Format paper as Markdown summary.

        Args:
            paper: Parsed PDF content.
            relevance_notes: Notes about relevance to research.

        Returns:
            Markdown formatted string.
        """
        lines = []

        # Title
        lines.append(f"# {paper.title or 'Untitled Paper'}")
        lines.append("")

        # Metadata
        lines.append("## Metadata")
        if paper.authors:
            lines.append(f"- **Authors**: {', '.join(paper.authors)}")
        lines.append(f"- **Pages**: {paper.page_count}")
        lines.append("")

        # Abstract
        if paper.abstract:
            lines.append("## Abstract")
            lines.append(paper.abstract)
            lines.append("")

        # Sections
        for section in paper.sections:
            if section.title.lower() not in ["abstract", "references", "acknowledgments"]:
                lines.append(f"## {section.title}")
                # Truncate long sections
                content = section.content[:3000]
                if len(section.content) > 3000:
                    content += "\n\n*[Content truncated...]*"
                lines.append(content)
                lines.append("")

        # Relevance notes
        if relevance_notes:
            lines.append("## Relevance to Research")
            lines.append(relevance_notes)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_literature_matrix(
        papers: list[dict],
    ) -> str:
        """Format papers as a comparison matrix.

        Args:
            papers: List of paper dictionaries with title, year, methodology, findings.

        Returns:
            Markdown table string.
        """
        if not papers:
            return "No papers to compare."

        lines = []
        lines.append("# Literature Comparison Matrix")
        lines.append("")
        lines.append("| Paper | Year | Methodology | Key Findings |")
        lines.append("|-------|------|-------------|--------------|")

        for paper in papers:
            title = paper.get("title", "")[:50]
            year = paper.get("year", "N/A")
            method = paper.get("methodology", "")[:100]
            findings = paper.get("findings", "")[:100]
            lines.append(f"| {title} | {year} | {method} | {findings} |")

        return "\n".join(lines)


class LocalPDFScanner:
    """Scan local folder for PDF files."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize scanner.

        Args:
            base_dir: Base directory to scan for PDFs.
        """
        self.base_dir = base_dir or Path("./papers")

    def scan_folder(self, folder_path: Optional[Path] = None) -> list[Path]:
        """Scan folder for PDF files.

        Args:
            folder_path: Folder to scan. Defaults to base_dir.

        Returns:
            List of PDF file paths.
        """
        target_dir = folder_path or self.base_dir

        if not target_dir.exists():
            logger.warning("Folder does not exist", path=str(target_dir))
            return []

        pdf_files = list(target_dir.glob("**/*.pdf"))
        logger.info("Found PDF files", count=len(pdf_files), path=str(target_dir))

        return sorted(pdf_files, key=lambda p: p.stat().st_mtime, reverse=True)

    def get_pdf_info(self, filepath: Path) -> dict:
        """Get basic info about a PDF file without parsing.

        Args:
            filepath: Path to PDF file.

        Returns:
            Dictionary with file info.
        """
        if not filepath.exists():
            return {"error": "File not found"}

        stat = filepath.stat()
        return {
            "filename": filepath.name,
            "path": str(filepath),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": stat.st_mtime,
        }

    def list_all_pdfs(self, folder_path: Optional[Path] = None) -> list[dict]:
        """List all PDFs with their info.

        Args:
            folder_path: Folder to scan.

        Returns:
            List of PDF info dictionaries.
        """
        pdf_files = self.scan_folder(folder_path)
        return [self.get_pdf_info(f) for f in pdf_files]
