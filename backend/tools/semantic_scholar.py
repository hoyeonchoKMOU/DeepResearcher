"""Semantic Scholar API tool for literature search."""

import asyncio
from typing import Optional

import httpx
import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.config import get_settings

logger = structlog.get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2.0  # seconds

# Semantic Scholar API base URL
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"


class PaperInfo(BaseModel):
    """Paper information from Semantic Scholar."""

    paper_id: str = Field(description="Semantic Scholar paper ID")
    title: str = Field(description="Paper title")
    abstract: Optional[str] = Field(default=None, description="Paper abstract")
    authors: list[str] = Field(default_factory=list, description="List of author names")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Publication venue")
    citation_count: int = Field(default=0, description="Number of citations")
    open_access_pdf: Optional[str] = Field(default=None, description="Open access PDF URL")
    doi: Optional[str] = Field(default=None, description="DOI")
    url: Optional[str] = Field(default=None, description="Semantic Scholar URL")
    fields_of_study: list[str] = Field(default_factory=list, description="Fields of study")
    publication_types: list[str] = Field(default_factory=list, description="Publication types")


class SearchResult(BaseModel):
    """Search result containing multiple papers."""

    papers: list[PaperInfo] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of results")
    query: str = Field(description="Original search query")


class SemanticScholarTool:
    """Tool for searching papers on Semantic Scholar."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Semantic Scholar tool.

        Args:
            api_key: Optional API key for higher rate limits.
        """
        settings = get_settings()
        self.api_key = api_key or settings.semantic_scholar_api_key
        self.headers = {}
        if self.api_key:
            self.headers["x-api-key"] = self.api_key

    async def search_papers(
        self,
        query: str,
        year_start: int = 2023,
        year_end: int = 2026,
        limit: int = 20,
        fields_of_study: Optional[list[str]] = None,
        min_citations: int = 0,
        open_access_only: bool = False,
    ) -> SearchResult:
        """Search for papers on Semantic Scholar.

        Args:
            query: Search query string.
            year_start: Start year for filtering (inclusive).
            year_end: End year for filtering (inclusive).
            limit: Maximum number of results to return.
            fields_of_study: Filter by fields of study (e.g., ["Computer Science"]).
            min_citations: Minimum citation count filter.
            open_access_only: Only return open access papers.

        Returns:
            SearchResult with list of papers.
        """
        logger.info(
            "Searching Semantic Scholar",
            query=query,
            year_range=f"{year_start}-{year_end}",
            limit=limit,
        )

        # Build query parameters
        params = {
            "query": query,
            "limit": min(limit, 100),  # API max is 100
            "fields": ",".join([
                "paperId",
                "title",
                "abstract",
                "authors",
                "year",
                "venue",
                "citationCount",
                "openAccessPdf",
                "externalIds",
                "url",
                "fieldsOfStudy",
                "publicationTypes",
            ]),
            "year": f"{year_start}-{year_end}",
        }

        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        if open_access_only:
            params["openAccessPdf"] = ""

        async with httpx.AsyncClient(timeout=30.0) as client:
            data = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(
                        f"{SEMANTIC_SCHOLAR_API}/paper/search",
                        params=params,
                        headers=self.headers,
                    )
                    response.raise_for_status()
                    data = response.json()
                    break  # Success, exit retry loop
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Rate limited - wait and retry with exponential backoff
                        delay = RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(
                            "Rate limited by Semantic Scholar, retrying",
                            attempt=attempt + 1,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error("Semantic Scholar API error", error=str(e))
                    return SearchResult(papers=[], total=0, query=query)
                except httpx.HTTPError as e:
                    logger.error("Semantic Scholar API error", error=str(e))
                    return SearchResult(papers=[], total=0, query=query)

            if data is None:
                logger.error("Semantic Scholar API failed after retries")
                return SearchResult(papers=[], total=0, query=query)

        # Parse results
        papers = []
        for item in data.get("data", []):
            # Filter by citation count
            citation_count = item.get("citationCount", 0) or 0
            if citation_count < min_citations:
                continue

            paper = PaperInfo(
                paper_id=item.get("paperId", ""),
                title=item.get("title", ""),
                abstract=item.get("abstract"),
                authors=[a.get("name", "") for a in item.get("authors", [])],
                year=item.get("year"),
                venue=item.get("venue"),
                citation_count=citation_count,
                open_access_pdf=(
                    item.get("openAccessPdf", {}).get("url")
                    if item.get("openAccessPdf")
                    else None
                ),
                doi=item.get("externalIds", {}).get("DOI"),
                url=item.get("url"),
                fields_of_study=item.get("fieldsOfStudy") or [],
                publication_types=item.get("publicationTypes") or [],
            )
            papers.append(paper)

        # Sort by citation count
        papers.sort(key=lambda p: p.citation_count, reverse=True)

        logger.info(
            "Search completed",
            query=query,
            results=len(papers),
            total=data.get("total", 0),
        )

        return SearchResult(
            papers=papers[:limit],
            total=data.get("total", 0),
            query=query,
        )

    async def get_paper_details(self, paper_id: str) -> Optional[PaperInfo]:
        """Get detailed information about a specific paper.

        Args:
            paper_id: Semantic Scholar paper ID.

        Returns:
            Paper information or None if not found.
        """
        params = {
            "fields": ",".join([
                "paperId",
                "title",
                "abstract",
                "authors",
                "year",
                "venue",
                "citationCount",
                "openAccessPdf",
                "externalIds",
                "url",
                "fieldsOfStudy",
                "publicationTypes",
            ]),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                item = response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to get paper details", paper_id=paper_id, error=str(e))
                return None

        return PaperInfo(
            paper_id=item.get("paperId", ""),
            title=item.get("title", ""),
            abstract=item.get("abstract"),
            authors=[a.get("name", "") for a in item.get("authors", [])],
            year=item.get("year"),
            venue=item.get("venue"),
            citation_count=item.get("citationCount", 0) or 0,
            open_access_pdf=(
                item.get("openAccessPdf", {}).get("url")
                if item.get("openAccessPdf")
                else None
            ),
            doi=item.get("externalIds", {}).get("DOI"),
            url=item.get("url"),
            fields_of_study=item.get("fieldsOfStudy") or [],
            publication_types=item.get("publicationTypes") or [],
        )

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[PaperInfo]:
        """Get papers that cite the given paper.

        Args:
            paper_id: Semantic Scholar paper ID.
            limit: Maximum number of citations to return.

        Returns:
            List of citing papers.
        """
        params = {
            "fields": "paperId,title,authors,year,citationCount",
            "limit": min(limit, 1000),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}/citations",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to get citations", paper_id=paper_id, error=str(e))
                return []

        papers = []
        for item in data.get("data", []):
            citing = item.get("citingPaper", {})
            if not citing.get("paperId"):
                continue

            paper = PaperInfo(
                paper_id=citing.get("paperId", ""),
                title=citing.get("title", ""),
                authors=[a.get("name", "") for a in citing.get("authors", [])],
                year=citing.get("year"),
                citation_count=citing.get("citationCount", 0) or 0,
            )
            papers.append(paper)

        return papers

    async def get_references(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[PaperInfo]:
        """Get papers referenced by the given paper.

        Args:
            paper_id: Semantic Scholar paper ID.
            limit: Maximum number of references to return.

        Returns:
            List of referenced papers.
        """
        params = {
            "fields": "paperId,title,authors,year,citationCount",
            "limit": min(limit, 1000),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}/references",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to get references", paper_id=paper_id, error=str(e))
                return []

        papers = []
        for item in data.get("data", []):
            cited = item.get("citedPaper", {})
            if not cited.get("paperId"):
                continue

            paper = PaperInfo(
                paper_id=cited.get("paperId", ""),
                title=cited.get("title", ""),
                authors=[a.get("name", "") for a in cited.get("authors", [])],
                year=cited.get("year"),
                citation_count=cited.get("citationCount", 0) or 0,
            )
            papers.append(paper)

        return papers


# LangChain tool wrappers
_tool_instance: Optional[SemanticScholarTool] = None


def _get_tool() -> SemanticScholarTool:
    """Get or create tool instance."""
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = SemanticScholarTool()
    return _tool_instance


@tool
def search_academic_papers(
    query: str,
    year_start: int = 2023,
    year_end: int = 2026,
    limit: int = 20,
    min_citations: int = 0,
) -> str:
    """Search for academic papers on Semantic Scholar.

    Args:
        query: Search query (keywords, paper title, etc.)
        year_start: Start year for filtering
        year_end: End year for filtering
        limit: Maximum number of results
        min_citations: Minimum citation count filter

    Returns:
        Formatted string with paper information
    """
    tool = _get_tool()
    result = asyncio.run(
        tool.search_papers(
            query=query,
            year_start=year_start,
            year_end=year_end,
            limit=limit,
            min_citations=min_citations,
        )
    )

    if not result.papers:
        return f"No papers found for query: {query}"

    lines = [f"Found {len(result.papers)} papers (total: {result.total}):\n"]
    for i, paper in enumerate(result.papers, 1):
        lines.append(f"{i}. {paper.title}")
        lines.append(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        lines.append(f"   Year: {paper.year or 'N/A'} | Citations: {paper.citation_count}")
        lines.append(f"   Venue: {paper.venue or 'N/A'}")
        if paper.open_access_pdf:
            lines.append(f"   PDF: {paper.open_access_pdf}")
        lines.append("")

    return "\n".join(lines)


@tool
def get_paper_citations(paper_id: str, limit: int = 20) -> str:
    """Get papers that cite a specific paper.

    Args:
        paper_id: Semantic Scholar paper ID
        limit: Maximum number of citations to return

    Returns:
        Formatted string with citing papers
    """
    tool = _get_tool()
    papers = asyncio.run(tool.get_citations(paper_id, limit))

    if not papers:
        return f"No citations found for paper: {paper_id}"

    lines = [f"Found {len(papers)} citing papers:\n"]
    for i, paper in enumerate(papers, 1):
        lines.append(f"{i}. {paper.title}")
        lines.append(f"   Year: {paper.year or 'N/A'} | Citations: {paper.citation_count}")
        lines.append("")

    return "\n".join(lines)
