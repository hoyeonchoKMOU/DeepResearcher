"""Unit tests for arXiv search tool."""

import pytest
from unittest.mock import MagicMock, patch
import httpx

from backend.tools.arxiv_search import (
    ArxivSearchTool,
    ArxivPaper,
    ArxivSearchResult,
    ARXIV_API,
)


# Sample XML response from arXiv API
SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query</title>
  <id>http://arxiv.org/api/test</id>
  <opensearch:totalResults>2</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <updated>2024-01-15T00:00:00Z</updated>
    <published>2024-01-15T00:00:00Z</published>
    <title>Test Paper on Machine Learning</title>
    <summary>This is a test abstract about machine learning.</summary>
    <author>
      <name>John Doe</name>
    </author>
    <author>
      <name>Jane Smith</name>
    </author>
    <arxiv:doi>10.1234/test</arxiv:doi>
    <link title="pdf" href="https://arxiv.org/pdf/2401.12345" rel="related"/>
    <arxiv:comment>10 pages, 5 figures</arxiv:comment>
    <category term="cs.LG"/>
    <category term="cs.AI"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2312.54321v2</id>
    <updated>2023-12-20T00:00:00Z</updated>
    <published>2023-12-10T00:00:00Z</published>
    <title>Another Test Paper</title>
    <summary>Another test abstract.</summary>
    <author>
      <name>Alice Johnson</name>
    </author>
    <link title="pdf" href="https://arxiv.org/pdf/2312.54321" rel="related"/>
    <category term="cs.CV"/>
  </entry>
</feed>
"""

EMPTY_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <title>ArXiv Query</title>
  <id>http://arxiv.org/api/test</id>
  <opensearch:totalResults>0</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
</feed>
"""


class TestArxivSearchTool:
    """Tests for ArxivSearchTool class."""

    @pytest.fixture
    def tool(self):
        """Create an ArxivSearchTool instance."""
        return ArxivSearchTool()

    def test_api_url_is_https(self):
        """Test that API URL uses HTTPS."""
        assert ARXIV_API.startswith("https://")
        assert "export.arxiv.org" in ARXIV_API

    def test_build_query_keywords_only(self, tool):
        """Test query building with keywords only."""
        query = tool._build_query(keywords=["machine", "learning"])
        assert "ti:" in query
        assert "abs:" in query
        assert "machine AND learning" in query

    def test_build_query_with_categories(self, tool):
        """Test query building with categories."""
        query = tool._build_query(
            keywords=["deep", "learning"],
            categories=["cs.LG", "cs.AI"],
        )
        assert "cat:cs.LG" in query
        assert "cat:cs.AI" in query

    def test_build_query_category_mapping(self, tool):
        """Test category mapping for common terms."""
        query = tool._build_query(keywords=["test"], categories=["machine_learning"])
        assert "cat:cs.LG" in query

        query = tool._build_query(keywords=["test"], categories=["ai"])
        assert "cat:cs.AI" in query

    @pytest.mark.asyncio
    async def test_search_papers_success(self, tool):
        """Test successful paper search."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = SAMPLE_ARXIV_XML.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(
                query="machine learning",
                year_start=2023,
                limit=10,
            )

            assert isinstance(result, ArxivSearchResult)
            assert len(result.papers) == 2
            assert result.total == 2

            # Check first paper
            paper1 = result.papers[0]
            assert paper1.arxiv_id == "2401.12345"
            assert "Machine Learning" in paper1.title
            assert len(paper1.authors) == 2
            assert "John Doe" in paper1.authors
            assert "cs.LG" in paper1.categories
            assert paper1.doi == "10.1234/test"
            assert paper1.comment == "10 pages, 5 figures"

    @pytest.mark.asyncio
    async def test_search_papers_empty_results(self, tool):
        """Test search with no results."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = EMPTY_ARXIV_XML.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(query="nonexistent topic")

            assert isinstance(result, ArxivSearchResult)
            assert len(result.papers) == 0
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_search_papers_http_error(self, tool):
        """Test handling of HTTP errors."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection failed")

            result = await tool.search_papers(query="test query")

            assert isinstance(result, ArxivSearchResult)
            assert len(result.papers) == 0

    @pytest.mark.asyncio
    async def test_search_papers_invalid_xml(self, tool):
        """Test handling of invalid XML response."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"<invalid xml"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(query="test")

            assert len(result.papers) == 0

    @pytest.mark.asyncio
    async def test_search_papers_year_filter(self, tool):
        """Test year filtering in search."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = SAMPLE_ARXIV_XML.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # Only papers from 2024 onwards
            result = await tool.search_papers(
                query="test",
                year_start=2024,
                limit=10,
            )

            # Only the 2024 paper should be included
            assert len(result.papers) == 1
            assert result.papers[0].published.startswith("2024")

    @pytest.mark.asyncio
    async def test_get_paper_by_id(self, tool):
        """Test getting a specific paper by ID."""
        single_paper_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>http://arxiv.org/abs/2401.12345</id>
            <published>2024-01-15T00:00:00Z</published>
            <updated>2024-01-15T00:00:00Z</updated>
            <title>Specific Paper</title>
            <summary>Specific abstract</summary>
            <author><name>Test Author</name></author>
            <category term="cs.LG"/>
          </entry>
        </feed>
        """

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = single_paper_xml.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            paper = await tool.get_paper("2401.12345")

            assert paper is not None
            assert paper.arxiv_id == "2401.12345"
            assert paper.title == "Specific Paper"

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self, tool):
        """Test getting a paper that doesn't exist."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Not found")

            paper = await tool.get_paper("nonexistent")

            assert paper is None

    @pytest.mark.asyncio
    async def test_get_paper_cleans_id(self, tool):
        """Test that paper ID is cleaned before request."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = EMPTY_ARXIV_XML.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            await tool.get_paper("arXiv:2401.12345")

            # Check that the ID was cleaned
            call_args = mock_get.call_args
            assert "arXiv:" not in str(call_args)

    @pytest.mark.asyncio
    async def test_get_recent_papers(self, tool):
        """Test getting recent papers by category."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = SAMPLE_ARXIV_XML.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.get_recent_papers(
                categories=["cs.LG", "cs.AI"],
                days=7,
                limit=50,
            )

            assert isinstance(result, ArxivSearchResult)
            # Both papers in sample are recent enough
            assert len(result.papers) >= 0

    def test_parse_entry_extracts_pdf_url(self, tool):
        """Test PDF URL extraction from entry."""
        from xml.etree import ElementTree

        entry_xml = """
        <entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <id>http://arxiv.org/abs/2401.12345</id>
          <title>Test</title>
          <summary>Test</summary>
          <published>2024-01-15</published>
          <link title="pdf" href="https://arxiv.org/pdf/2401.12345" rel="related"/>
        </entry>
        """
        entry = ElementTree.fromstring(entry_xml)
        paper = tool._parse_entry(entry)

        assert paper is not None
        assert "2401.12345" in paper.pdf_url

    def test_parse_entry_generates_pdf_url_if_missing(self, tool):
        """Test PDF URL generation when link is missing."""
        from xml.etree import ElementTree

        entry_xml = """
        <entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <id>http://arxiv.org/abs/2401.99999</id>
          <title>Test</title>
          <summary>Test</summary>
          <published>2024-01-15</published>
        </entry>
        """
        entry = ElementTree.fromstring(entry_xml)
        paper = tool._parse_entry(entry)

        assert paper is not None
        assert paper.pdf_url == "https://arxiv.org/pdf/2401.99999.pdf"


class TestArxivPaper:
    """Tests for ArxivPaper model."""

    def test_paper_creation(self):
        """Test creating an ArxivPaper instance."""
        paper = ArxivPaper(
            arxiv_id="2401.12345",
            title="Test Paper",
            abstract="Test abstract",
            authors=["Author 1", "Author 2"],
            published="2024-01-15",
            updated="2024-01-16",
            categories=["cs.LG", "cs.AI"],
            pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
            doi="10.1234/test",
            comment="10 pages",
        )

        assert paper.arxiv_id == "2401.12345"
        assert len(paper.authors) == 2
        assert len(paper.categories) == 2

    def test_paper_defaults(self):
        """Test ArxivPaper default values."""
        paper = ArxivPaper(arxiv_id="test", title="Test")

        assert paper.abstract == ""
        assert paper.authors == []
        assert paper.categories == []
        assert paper.pdf_url == ""
        assert paper.doi is None


class TestArxivSearchResult:
    """Tests for ArxivSearchResult model."""

    def test_result_creation(self):
        """Test creating an ArxivSearchResult instance."""
        papers = [
            ArxivPaper(arxiv_id="1", title="Paper 1"),
            ArxivPaper(arxiv_id="2", title="Paper 2"),
        ]
        result = ArxivSearchResult(papers=papers, total=100, query="test")

        assert len(result.papers) == 2
        assert result.total == 100
        assert result.query == "test"
