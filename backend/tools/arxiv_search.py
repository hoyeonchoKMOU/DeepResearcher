"""arXiv API tool for preprint search."""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"


class ArxivPaper(BaseModel):
    """Paper information from arXiv."""

    arxiv_id: str = Field(description="arXiv paper ID")
    title: str = Field(description="Paper title")
    abstract: str = Field(default="", description="Paper abstract")
    authors: list[str] = Field(default_factory=list, description="List of author names")
    published: Optional[str] = Field(default=None, description="Publication date")
    updated: Optional[str] = Field(default=None, description="Last updated date")
    categories: list[str] = Field(default_factory=list, description="arXiv categories")
    pdf_url: str = Field(default="", description="PDF URL")
    doi: Optional[str] = Field(default=None, description="DOI if available")
    comment: Optional[str] = Field(default=None, description="Author comment")


class ArxivSearchResult(BaseModel):
    """Search result from arXiv."""

    papers: list[ArxivPaper] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of results")
    query: str = Field(description="Original search query")


class ArxivSearchTool:
    """Tool for searching papers on arXiv."""

    # arXiv category mappings for common fields
    CATEGORY_MAP = {
        "computer_science": "cs",
        "cs": "cs",
        "machine_learning": "cs.LG",
        "ml": "cs.LG",
        "artificial_intelligence": "cs.AI",
        "ai": "cs.AI",
        "nlp": "cs.CL",
        "computer_vision": "cs.CV",
        "cv": "cs.CV",
        "physics": "physics",
        "mathematics": "math",
        "statistics": "stat",
        "biology": "q-bio",
        "economics": "econ",
    }

    def __init__(self):
        """Initialize arXiv search tool."""
        pass

    def _build_query(
        self,
        keywords: list[str],
        categories: Optional[list[str]] = None,
        year_start: Optional[int] = None,
    ) -> str:
        """Build arXiv query string.

        Args:
            keywords: Search keywords.
            categories: arXiv categories to filter.
            year_start: Filter papers from this year onwards.

        Returns:
            arXiv query string.
        """
        query_parts = []

        # Add keywords - use simple OR-based search for better recall
        # Take most important keywords (first 4) and search in title/abstract
        if keywords:
            # Filter out very short words and special characters
            clean_keywords = [kw for kw in keywords if len(kw) >= 3 and kw.isalnum()][:4]
            if clean_keywords:
                # Search title OR abstract for each keyword (more permissive)
                keyword_queries = []
                for kw in clean_keywords:
                    keyword_queries.append(f"ti:{kw}")
                    keyword_queries.append(f"abs:{kw}")
                query_parts.append(f"({' OR '.join(keyword_queries)})")

        # Add category filter
        if categories:
            mapped_cats = []
            for cat in categories:
                mapped = self.CATEGORY_MAP.get(cat.lower(), cat)
                mapped_cats.append(f"cat:{mapped}")
            if mapped_cats:
                query_parts.append(f"({' OR '.join(mapped_cats)})")

        # If no valid query parts, just return joined keywords
        if not query_parts:
            return " ".join(keywords[:5])

        return " AND ".join(query_parts) if len(query_parts) > 1 else query_parts[0]

    def _parse_entry(self, entry: ElementTree.Element) -> Optional[ArxivPaper]:
        """Parse a single arXiv entry.

        Args:
            entry: XML element for the entry.

        Returns:
            ArxivPaper or None if parsing fails.
        """
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        try:
            # Get ID
            id_elem = entry.find("atom:id", ns)
            if id_elem is None or id_elem.text is None:
                return None

            full_id = id_elem.text
            # Extract just the arXiv ID (e.g., "2301.00001" from full URL)
            arxiv_id_match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?$", full_id)
            if arxiv_id_match:
                arxiv_id = arxiv_id_match.group(1)
            else:
                arxiv_id = full_id.split("/")[-1]

            # Get title
            title_elem = entry.find("atom:title", ns)
            title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""

            # Get abstract
            abstract_elem = entry.find("atom:summary", ns)
            abstract = abstract_elem.text.strip().replace("\n", " ") if abstract_elem is not None and abstract_elem.text else ""

            # Get authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name_elem = author.find("atom:name", ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)

            # Get dates
            published_elem = entry.find("atom:published", ns)
            published = published_elem.text[:10] if published_elem is not None and published_elem.text else None

            updated_elem = entry.find("atom:updated", ns)
            updated = updated_elem.text[:10] if updated_elem is not None and updated_elem.text else None

            # Get categories
            categories = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term")
                if term:
                    categories.append(term)

            # Get PDF link
            pdf_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")
                    break
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            # Get DOI
            doi_elem = entry.find("arxiv:doi", ns)
            doi = doi_elem.text if doi_elem is not None else None

            # Get comment
            comment_elem = entry.find("arxiv:comment", ns)
            comment = comment_elem.text if comment_elem is not None else None

            return ArxivPaper(
                arxiv_id=arxiv_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published=published,
                updated=updated,
                categories=categories,
                pdf_url=pdf_url,
                doi=doi,
                comment=comment,
            )

        except Exception as e:
            logger.error("Failed to parse arXiv entry", error=str(e))
            return None

    async def search_papers(
        self,
        query: str,
        categories: Optional[list[str]] = None,
        year_start: int = 2023,
        limit: int = 20,
        sort_by: str = "relevance",
    ) -> ArxivSearchResult:
        """Search for papers on arXiv.

        Args:
            query: Search query (keywords).
            categories: Filter by arXiv categories (e.g., ["cs.AI", "cs.LG"]).
            year_start: Filter papers from this year onwards.
            limit: Maximum number of results.
            sort_by: Sort order ("relevance", "lastUpdatedDate", "submittedDate").

        Returns:
            ArxivSearchResult with list of papers.
        """
        # Build query
        keywords = query.split()
        search_query = self._build_query(keywords, categories)

        logger.info(
            "Searching arXiv",
            original_query=query,
            built_query=search_query,
            categories=categories,
            year_start=year_start,
            limit=limit,
        )

        # Sort order mapping
        sort_map = {
            "relevance": "relevance",
            "lastUpdatedDate": "lastUpdatedDate",
            "submittedDate": "submittedDate",
            "date": "submittedDate",
        }

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(limit * 2, 100),  # Fetch more to filter by year
            "sortBy": sort_map.get(sort_by, "relevance"),
            "sortOrder": "descending",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(ARXIV_API, params=params)
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("arXiv API error", error=str(e))
                return ArxivSearchResult(papers=[], total=0, query=query)

        # Parse XML response
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as e:
            logger.error("Failed to parse arXiv XML", error=str(e))
            return ArxivSearchResult(papers=[], total=0, query=query)

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Get total results
        total_elem = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
        total = int(total_elem.text) if total_elem is not None and total_elem.text else 0

        # Parse entries
        papers = []
        for entry in root.findall("atom:entry", ns):
            paper = self._parse_entry(entry)
            if paper is None:
                continue

            # Filter by year
            if paper.published:
                try:
                    pub_year = int(paper.published[:4])
                    if pub_year < year_start:
                        continue
                except ValueError:
                    pass

            papers.append(paper)

            if len(papers) >= limit:
                break

        logger.info(
            "arXiv search completed",
            query=query,
            results=len(papers),
            total=total,
        )

        return ArxivSearchResult(
            papers=papers,
            total=total,
            query=query,
        )

    async def get_paper(self, arxiv_id: str) -> Optional[ArxivPaper]:
        """Get details of a specific arXiv paper.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2301.00001").

        Returns:
            ArxivPaper or None if not found.
        """
        # Clean up ID
        arxiv_id = arxiv_id.replace("arXiv:", "").strip()

        params = {
            "id_list": arxiv_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(ARXIV_API, params=params)
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("Failed to get arXiv paper", arxiv_id=arxiv_id, error=str(e))
                return None

        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            return None

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns)
        if not entries:
            return None

        return self._parse_entry(entries[0])

    async def get_recent_papers(
        self,
        categories: list[str],
        days: int = 7,
        limit: int = 50,
    ) -> ArxivSearchResult:
        """Get recent papers in specific categories.

        Args:
            categories: arXiv categories (e.g., ["cs.AI", "cs.LG"]).
            days: Number of days to look back.
            limit: Maximum number of results.

        Returns:
            ArxivSearchResult with recent papers.
        """
        # Build category query
        mapped_cats = []
        for cat in categories:
            mapped = self.CATEGORY_MAP.get(cat.lower(), cat)
            mapped_cats.append(f"cat:{mapped}")

        search_query = " OR ".join(mapped_cats)

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(ARXIV_API, params=params)
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("arXiv API error", error=str(e))
                return ArxivSearchResult(papers=[], total=0, query=search_query)

        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            return ArxivSearchResult(papers=[], total=0, query=search_query)

        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Calculate cutoff date
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        papers = []
        for entry in root.findall("atom:entry", ns):
            paper = self._parse_entry(entry)
            if paper is None:
                continue

            # Filter by date
            if paper.published and paper.published < cutoff_date:
                continue

            papers.append(paper)

        return ArxivSearchResult(
            papers=papers,
            total=len(papers),
            query=search_query,
        )
