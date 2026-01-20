"""Literature Searcher Agent - Multi-source academic paper search.

Searches across:
- Semantic Scholar (SCIE/Conference papers)
- arXiv (preprints)
- Google Scholar (general academic)
"""

import asyncio
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from backend.tools.semantic_scholar import SemanticScholarTool, PaperInfo
from backend.tools.arxiv_search import ArxivSearchTool, ArxivPaper
from backend.tools.google_scholar import GoogleScholarTool, GoogleScholarPaper

logger = structlog.get_logger(__name__)


class UnifiedPaper(BaseModel):
    """Unified paper representation across all sources."""

    id: str = Field(description="Unique identifier")
    source: str = Field(description="Source: semantic_scholar, arxiv, google_scholar")
    title: str = Field(description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    abstract: str = Field(default="", description="Paper abstract")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Publication venue")
    citations: int = Field(default=0, description="Citation count")
    pdf_url: Optional[str] = Field(default=None, description="PDF URL")
    doi: Optional[str] = Field(default=None, description="DOI")
    url: Optional[str] = Field(default=None, description="Paper URL")
    categories: list[str] = Field(default_factory=list, description="Categories/fields")


class LiteratureSearchResult(BaseModel):
    """Combined search results from all sources."""

    papers: list[UnifiedPaper] = Field(default_factory=list)
    total_found: int = Field(default=0)
    sources_searched: list[str] = Field(default_factory=list)
    query: str = Field(description="Search query")


class LiteratureSearcherAgent:
    """Agent for searching academic papers across multiple sources.

    Aggregates results from Semantic Scholar, arXiv, and Google Scholar,
    deduplicates, and ranks by relevance/citations.
    """

    def __init__(
        self,
        use_semantic_scholar: bool = True,
        use_arxiv: bool = True,
        use_google_scholar: bool = True,
    ):
        """Initialize the Literature Searcher Agent.

        Args:
            use_semantic_scholar: Enable Semantic Scholar search.
            use_arxiv: Enable arXiv search.
            use_google_scholar: Enable Google Scholar search.
        """
        self.sources = []

        if use_semantic_scholar:
            self.semantic_scholar = SemanticScholarTool()
            self.sources.append("semantic_scholar")
        else:
            self.semantic_scholar = None

        if use_arxiv:
            self.arxiv = ArxivSearchTool()
            self.sources.append("arxiv")
        else:
            self.arxiv = None

        if use_google_scholar:
            self.google_scholar = GoogleScholarTool()
            self.sources.append("google_scholar")
        else:
            self.google_scholar = None

        logger.info("LiteratureSearcherAgent initialized", sources=self.sources)

    def _convert_semantic_scholar(self, paper: PaperInfo) -> UnifiedPaper:
        """Convert Semantic Scholar paper to unified format."""
        return UnifiedPaper(
            id=f"ss:{paper.paper_id}",
            source="semantic_scholar",
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract or "",
            year=paper.year,
            venue=paper.venue,
            citations=paper.citation_count,
            pdf_url=paper.open_access_pdf,
            doi=paper.doi,
            url=paper.url,
            categories=paper.fields_of_study,
        )

    def _convert_arxiv(self, paper: ArxivPaper) -> UnifiedPaper:
        """Convert arXiv paper to unified format."""
        year = None
        if paper.published:
            try:
                year = int(paper.published[:4])
            except (ValueError, TypeError):
                pass

        return UnifiedPaper(
            id=f"arxiv:{paper.arxiv_id}",
            source="arxiv",
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            year=year,
            venue="arXiv",
            citations=0,  # arXiv doesn't provide citation count
            pdf_url=paper.pdf_url,
            doi=paper.doi,
            url=f"https://arxiv.org/abs/{paper.arxiv_id}",
            categories=paper.categories,
        )

    def _convert_google_scholar(self, paper: GoogleScholarPaper) -> UnifiedPaper:
        """Convert Google Scholar paper to unified format."""
        return UnifiedPaper(
            id=f"gs:{paper.title[:50]}",  # Use title as ID
            source="google_scholar",
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            year=paper.year,
            venue=paper.venue,
            citations=paper.citations,
            pdf_url=paper.pdf_url,
            url=paper.url,
            categories=[],
        )

    def _deduplicate_papers(self, papers: list[UnifiedPaper]) -> list[UnifiedPaper]:
        """Remove duplicate papers based on title similarity.

        Args:
            papers: List of papers to deduplicate.

        Returns:
            Deduplicated list.
        """
        seen_titles = set()
        unique_papers = []

        for paper in papers:
            # Normalize title for comparison
            normalized = paper.title.lower().strip()
            # Remove common prefixes/suffixes
            normalized = normalized.replace(":", "").replace("-", " ")
            # Take first 100 chars for comparison
            key = normalized[:100]

            if key not in seen_titles:
                seen_titles.add(key)
                unique_papers.append(paper)

        return unique_papers

    async def search(
        self,
        query: str,
        keywords: Optional[list[str]] = None,
        year_start: int = 2023,
        year_end: int = 2026,
        limit_per_source: int = 20,
        min_citations: int = 0,
        categories: Optional[list[str]] = None,
    ) -> LiteratureSearchResult:
        """Search for papers across all configured sources.

        Args:
            query: Main search query.
            keywords: Additional keywords for search.
            year_start: Filter papers from this year.
            year_end: Filter papers until this year.
            limit_per_source: Max papers per source.
            min_citations: Minimum citation count filter.
            categories: Filter by categories (for arXiv).

        Returns:
            Combined and deduplicated search results.
        """
        search_query = query
        if keywords:
            search_query = f"{query} {' '.join(keywords)}"

        logger.info(
            "Starting literature search",
            query=search_query,
            year_range=f"{year_start}-{year_end}",
            sources=self.sources,
        )

        all_papers = []
        sources_searched = []
        total_found = 0

        # Run searches in parallel
        tasks = []

        if self.semantic_scholar:
            tasks.append(("semantic_scholar", self.semantic_scholar.search_papers(
                query=search_query,
                year_start=year_start,
                year_end=year_end,
                limit=limit_per_source,
                min_citations=min_citations,
            )))

        if self.arxiv:
            tasks.append(("arxiv", self.arxiv.search_papers(
                query=search_query,
                categories=categories,
                year_start=year_start,
                limit=limit_per_source,
            )))

        if self.google_scholar:
            tasks.append(("google_scholar", self.google_scholar.search_papers(
                query=search_query,
                year_start=year_start,
                year_end=year_end,
                limit=limit_per_source,
            )))

        # Execute all searches
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True,
        )

        # Process results
        for (source_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(f"{source_name} search failed", error=str(result))
                continue

            sources_searched.append(source_name)

            if source_name == "semantic_scholar":
                total_found += result.total
                for paper in result.papers:
                    all_papers.append(self._convert_semantic_scholar(paper))

            elif source_name == "arxiv":
                total_found += result.total
                for paper in result.papers:
                    all_papers.append(self._convert_arxiv(paper))

            elif source_name == "google_scholar":
                total_found += len(result.papers)
                for paper in result.papers:
                    all_papers.append(self._convert_google_scholar(paper))

        # Deduplicate
        unique_papers = self._deduplicate_papers(all_papers)

        # Sort by citations (descending), then by year (descending)
        unique_papers.sort(
            key=lambda p: (p.citations or 0, p.year or 0),
            reverse=True,
        )

        logger.info(
            "Literature search completed",
            query=search_query,
            total_papers=len(unique_papers),
            sources=sources_searched,
        )

        return LiteratureSearchResult(
            papers=unique_papers,
            total_found=total_found,
            sources_searched=sources_searched,
            query=search_query,
        )

    async def get_paper_details(
        self,
        paper_id: str,
    ) -> Optional[UnifiedPaper]:
        """Get detailed information about a specific paper.

        Args:
            paper_id: Paper ID in format "source:id".

        Returns:
            Paper details or None if not found.
        """
        if paper_id.startswith("ss:"):
            if self.semantic_scholar:
                ss_id = paper_id[3:]
                paper = await self.semantic_scholar.get_paper_details(ss_id)
                if paper:
                    return self._convert_semantic_scholar(paper)

        elif paper_id.startswith("arxiv:"):
            if self.arxiv:
                arxiv_id = paper_id[6:]
                paper = await self.arxiv.get_paper(arxiv_id)
                if paper:
                    return self._convert_arxiv(paper)

        return None

    def format_papers_for_display(self, papers: list[UnifiedPaper]) -> str:
        """Format papers for display in chat.

        Args:
            papers: List of papers to format.

        Returns:
            Formatted string.
        """
        if not papers:
            return "No papers found."

        lines = [f"Found {len(papers)} papers:\n"]

        for i, paper in enumerate(papers, 1):
            lines.append(f"**{i}. {paper.title}**")
            lines.append(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            lines.append(f"   Year: {paper.year or 'N/A'} | Citations: {paper.citations}")
            lines.append(f"   Source: {paper.source} | Venue: {paper.venue or 'N/A'}")
            if paper.pdf_url:
                lines.append(f"   PDF: {paper.pdf_url}")
            lines.append("")

        return "\n".join(lines)
