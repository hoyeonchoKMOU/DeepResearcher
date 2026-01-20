"""Google Scholar search tool using scholarly library."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Thread pool for running scholarly in async context
_executor = ThreadPoolExecutor(max_workers=3)


class GoogleScholarPaper(BaseModel):
    """Paper information from Google Scholar."""

    title: str = Field(description="Paper title")
    authors: list[str] = Field(default_factory=list, description="List of author names")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Publication venue")
    abstract: str = Field(default="", description="Paper abstract/snippet")
    citations: int = Field(default=0, description="Number of citations")
    url: Optional[str] = Field(default=None, description="Paper URL")
    pdf_url: Optional[str] = Field(default=None, description="PDF URL if available")
    scholar_id: Optional[str] = Field(default=None, description="Google Scholar ID")


class GoogleScholarSearchResult(BaseModel):
    """Search result from Google Scholar."""

    papers: list[GoogleScholarPaper] = Field(default_factory=list)
    query: str = Field(description="Original search query")


class GoogleScholarTool:
    """Tool for searching papers on Google Scholar.

    Note: Google Scholar has rate limits and may block requests.
    Use sparingly and with delays between requests.
    """

    def __init__(self):
        """Initialize Google Scholar tool."""
        self._scholarly_available = False
        self._scholarly = None
        try:
            from scholarly import scholarly
            self._scholarly = scholarly
            self._scholarly_available = True
            logger.info("scholarly library loaded successfully")
        except ImportError:
            logger.warning("scholarly library not available. Install with: pip install scholarly")
        except Exception as e:
            logger.warning("scholarly library failed to initialize", error=str(e))

    def _search_sync(
        self,
        query: str,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        limit: int = 20,
    ) -> GoogleScholarSearchResult:
        """Synchronous search function for thread pool."""
        if not self._scholarly_available:
            return GoogleScholarSearchResult(papers=[], query=query)

        papers = []
        try:
            search_query = self._scholarly.search_pubs(query)

            count = 0
            for pub in search_query:
                if count >= limit:
                    break

                try:
                    bib = pub.get("bib", {})

                    # Filter by year
                    year = None
                    if "pub_year" in bib:
                        try:
                            year = int(bib["pub_year"])
                            if year_start and year < year_start:
                                continue
                            if year_end and year > year_end:
                                continue
                        except (ValueError, TypeError):
                            pass

                    # Get authors
                    authors = bib.get("author", "").split(" and ") if "author" in bib else []
                    authors = [a.strip() for a in authors if a.strip()]

                    # Get PDF URL if available
                    pdf_url = None
                    eprint = pub.get("eprint_url")
                    if eprint:
                        pdf_url = eprint

                    paper = GoogleScholarPaper(
                        title=bib.get("title", ""),
                        authors=authors,
                        year=year,
                        venue=bib.get("venue", bib.get("journal", "")),
                        abstract=bib.get("abstract", ""),
                        citations=pub.get("num_citations", 0) or 0,
                        url=pub.get("pub_url"),
                        pdf_url=pdf_url,
                        scholar_id=pub.get("author_id", [None])[0] if pub.get("author_id") else None,
                    )
                    papers.append(paper)
                    count += 1

                except Exception as e:
                    logger.debug("Error parsing Google Scholar result", error=str(e))
                    continue

        except Exception as e:
            logger.error("Google Scholar search error", error=str(e))

        return GoogleScholarSearchResult(papers=papers, query=query)

    async def search_papers(
        self,
        query: str,
        year_start: int = 2023,
        year_end: int = 2026,
        limit: int = 20,
    ) -> GoogleScholarSearchResult:
        """Search for papers on Google Scholar.

        Args:
            query: Search query.
            year_start: Filter papers from this year onwards.
            year_end: Filter papers until this year.
            limit: Maximum number of results.

        Returns:
            GoogleScholarSearchResult with list of papers.
        """
        if not self._scholarly_available:
            logger.warning("scholarly not available, returning empty results")
            return GoogleScholarSearchResult(papers=[], query=query)

        logger.info(
            "Searching Google Scholar",
            query=query,
            year_range=f"{year_start}-{year_end}",
            limit=limit,
        )

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            self._search_sync,
            query,
            year_start,
            year_end,
            limit,
        )

        logger.info(
            "Google Scholar search completed",
            query=query,
            results=len(result.papers),
        )

        return result

    def _get_author_sync(self, author_name: str) -> Optional[dict]:
        """Get author profile synchronously."""
        if not self._scholarly_available:
            return None

        try:
            search = self._scholarly.search_author(author_name)
            author = next(search, None)
            if author:
                # Fill author details
                author = self._scholarly.fill(author)
                return {
                    "name": author.get("name", ""),
                    "affiliation": author.get("affiliation", ""),
                    "citations": author.get("citedby", 0),
                    "h_index": author.get("hindex", 0),
                    "i10_index": author.get("i10index", 0),
                    "interests": author.get("interests", []),
                }
        except Exception as e:
            logger.error("Failed to get author profile", author=author_name, error=str(e))

        return None

    async def get_author_profile(self, author_name: str) -> Optional[dict]:
        """Get author profile from Google Scholar.

        Args:
            author_name: Author name to search.

        Returns:
            Author profile dict or None if not found.
        """
        if not self._scholarly_available:
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            self._get_author_sync,
            author_name,
        )

    def _cite_paper_sync(self, title: str) -> Optional[str]:
        """Get citation for a paper synchronously."""
        if not self._scholarly_available:
            return None

        try:
            search = self._scholarly.search_pubs(title)
            pub = next(search, None)
            if pub:
                # Try to get BibTeX
                return self._scholarly.bibtex(pub)
        except Exception as e:
            logger.error("Failed to get citation", title=title, error=str(e))

        return None

    async def get_bibtex_citation(self, title: str) -> Optional[str]:
        """Get BibTeX citation for a paper.

        Args:
            title: Paper title to search.

        Returns:
            BibTeX string or None if not found.
        """
        if not self._scholarly_available:
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            self._cite_paper_sync,
            title,
        )
