"""Unit tests for Google Scholar search tool."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from backend.tools.google_scholar import (
    GoogleScholarTool,
    GoogleScholarPaper,
    GoogleScholarSearchResult,
)


class TestGoogleScholarTool:
    """Tests for GoogleScholarTool class."""

    @pytest.fixture
    def mock_scholarly(self):
        """Create a mock scholarly module."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def tool_with_scholarly(self, mock_scholarly):
        """Create a GoogleScholarTool with mocked scholarly."""
        with patch.dict("sys.modules", {"scholarly": MagicMock()}):
            with patch(
                "backend.tools.google_scholar.GoogleScholarTool.__init__",
                lambda self: None,
            ):
                tool = GoogleScholarTool()
                tool._scholarly_available = True
                tool._scholarly = mock_scholarly
                return tool

    @pytest.fixture
    def tool_without_scholarly(self):
        """Create a GoogleScholarTool without scholarly."""
        with patch(
            "backend.tools.google_scholar.GoogleScholarTool.__init__",
            lambda self: None,
        ):
            tool = GoogleScholarTool()
            tool._scholarly_available = False
            tool._scholarly = None
            return tool

    @pytest.fixture
    def sample_pub_data(self):
        """Sample publication data from scholarly."""
        return [
            {
                "bib": {
                    "title": "Test Paper 1",
                    "author": "John Doe and Jane Smith",
                    "pub_year": "2024",
                    "venue": "Test Conference",
                    "abstract": "This is a test abstract",
                },
                "num_citations": 100,
                "pub_url": "https://example.com/paper1",
                "eprint_url": "https://example.com/paper1.pdf",
                "author_id": ["author123"],
            },
            {
                "bib": {
                    "title": "Test Paper 2",
                    "author": "Alice Johnson",
                    "pub_year": "2023",
                    "journal": "Test Journal",
                    "abstract": "Another test abstract",
                },
                "num_citations": 50,
                "pub_url": "https://example.com/paper2",
                "eprint_url": None,
                "author_id": None,
            },
        ]

    def test_tool_handles_missing_scholarly_gracefully(self, tool_without_scholarly):
        """Test that tool works gracefully when scholarly is not available."""
        # Tool without scholarly should have _scholarly_available = False
        assert not tool_without_scholarly._scholarly_available
        assert tool_without_scholarly._scholarly is None

        # Sync search should return empty results
        result = tool_without_scholarly._search_sync("test", limit=10)
        assert len(result.papers) == 0

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_scholarly_unavailable(self, tool_without_scholarly):
        """Test async search returns empty when scholarly is unavailable."""
        result = await tool_without_scholarly.search_papers("test", limit=10)
        assert len(result.papers) == 0
        assert result.query == "test"

    def test_search_sync_success(self, tool_with_scholarly, mock_scholarly, sample_pub_data):
        """Test synchronous search function."""
        mock_scholarly.search_pubs.return_value = iter(sample_pub_data)

        result = tool_with_scholarly._search_sync(
            query="test query",
            year_start=2023,
            year_end=2025,
            limit=10,
        )

        assert isinstance(result, GoogleScholarSearchResult)
        assert len(result.papers) == 2
        assert result.query == "test query"

        # Check first paper
        paper1 = result.papers[0]
        assert paper1.title == "Test Paper 1"
        assert "John Doe" in paper1.authors
        assert "Jane Smith" in paper1.authors
        assert paper1.year == 2024
        assert paper1.citations == 100
        assert paper1.pdf_url == "https://example.com/paper1.pdf"

    def test_search_sync_year_filter(self, tool_with_scholarly, mock_scholarly, sample_pub_data):
        """Test year filtering in synchronous search."""
        mock_scholarly.search_pubs.return_value = iter(sample_pub_data)

        result = tool_with_scholarly._search_sync(
            query="test",
            year_start=2024,  # Should exclude 2023 paper
            year_end=2025,
            limit=10,
        )

        assert len(result.papers) == 1
        assert result.papers[0].year == 2024

    def test_search_sync_limit(self, tool_with_scholarly, mock_scholarly, sample_pub_data):
        """Test limit in synchronous search."""
        mock_scholarly.search_pubs.return_value = iter(sample_pub_data)

        result = tool_with_scholarly._search_sync(
            query="test",
            limit=1,
        )

        assert len(result.papers) == 1

    def test_search_sync_scholarly_not_available(self, tool_without_scholarly):
        """Test search when scholarly is not available."""
        result = tool_without_scholarly._search_sync(
            query="test",
            limit=10,
        )

        assert len(result.papers) == 0
        assert result.query == "test"

    def test_search_sync_exception_handling(self, tool_with_scholarly, mock_scholarly):
        """Test exception handling in synchronous search."""
        mock_scholarly.search_pubs.side_effect = Exception("API error")

        result = tool_with_scholarly._search_sync(
            query="test",
            limit=10,
        )

        assert len(result.papers) == 0

    @pytest.mark.asyncio
    async def test_search_papers_async(self, tool_with_scholarly, mock_scholarly, sample_pub_data):
        """Test async search papers method."""
        mock_scholarly.search_pubs.return_value = iter(sample_pub_data)

        # Mock run_in_executor to run synchronously
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=GoogleScholarSearchResult(
                    papers=[
                        GoogleScholarPaper(
                            title="Test Paper",
                            authors=["Author"],
                            year=2024,
                            citations=100,
                        )
                    ],
                    query="test",
                )
            )

            result = await tool_with_scholarly.search_papers(
                query="test",
                year_start=2023,
                year_end=2025,
                limit=10,
            )

            assert isinstance(result, GoogleScholarSearchResult)
            assert len(result.papers) == 1

    @pytest.mark.asyncio
    async def test_search_papers_scholarly_not_available(self, tool_without_scholarly):
        """Test async search when scholarly is not available."""
        result = await tool_without_scholarly.search_papers(
            query="test",
            limit=10,
        )

        assert len(result.papers) == 0

    def test_get_author_sync_success(self, tool_with_scholarly, mock_scholarly):
        """Test synchronous author profile retrieval."""
        mock_author = {
            "name": "Test Author",
            "affiliation": "Test University",
            "citedby": 1000,
            "hindex": 20,
            "i10index": 30,
            "interests": ["Machine Learning", "AI"],
        }
        mock_scholarly.search_author.return_value = iter([mock_author])
        mock_scholarly.fill.return_value = mock_author

        result = tool_with_scholarly._get_author_sync("Test Author")

        assert result is not None
        assert result["name"] == "Test Author"
        assert result["citations"] == 1000
        assert result["h_index"] == 20

    def test_get_author_sync_not_found(self, tool_with_scholarly, mock_scholarly):
        """Test author profile when not found."""
        mock_scholarly.search_author.return_value = iter([])

        result = tool_with_scholarly._get_author_sync("Unknown Author")

        assert result is None

    def test_get_author_sync_exception(self, tool_with_scholarly, mock_scholarly):
        """Test author profile exception handling."""
        mock_scholarly.search_author.side_effect = Exception("API error")

        result = tool_with_scholarly._get_author_sync("Test Author")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_author_profile_async(self, tool_with_scholarly):
        """Test async author profile retrieval."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value={
                    "name": "Test Author",
                    "citations": 1000,
                }
            )

            result = await tool_with_scholarly.get_author_profile("Test Author")

            assert result is not None
            assert result["name"] == "Test Author"

    @pytest.mark.asyncio
    async def test_get_author_profile_not_available(self, tool_without_scholarly):
        """Test author profile when scholarly not available."""
        result = await tool_without_scholarly.get_author_profile("Test Author")

        assert result is None

    def test_cite_paper_sync_success(self, tool_with_scholarly, mock_scholarly):
        """Test synchronous BibTeX citation retrieval."""
        mock_pub = {"title": "Test Paper"}
        mock_scholarly.search_pubs.return_value = iter([mock_pub])
        mock_scholarly.bibtex.return_value = "@article{test, title={Test Paper}}"

        result = tool_with_scholarly._cite_paper_sync("Test Paper")

        assert result is not None
        assert "@article" in result

    def test_cite_paper_sync_not_found(self, tool_with_scholarly, mock_scholarly):
        """Test citation when paper not found."""
        mock_scholarly.search_pubs.return_value = iter([])

        result = tool_with_scholarly._cite_paper_sync("Unknown Paper")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_bibtex_citation(self, tool_with_scholarly):
        """Test async BibTeX citation retrieval."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value="@article{test, title={Test}}"
            )

            result = await tool_with_scholarly.get_bibtex_citation("Test Paper")

            assert result is not None
            assert "@article" in result

    @pytest.mark.asyncio
    async def test_get_bibtex_citation_not_available(self, tool_without_scholarly):
        """Test BibTeX when scholarly not available."""
        result = await tool_without_scholarly.get_bibtex_citation("Test Paper")

        assert result is None


class TestGoogleScholarPaper:
    """Tests for GoogleScholarPaper model."""

    def test_paper_creation(self):
        """Test creating a GoogleScholarPaper instance."""
        paper = GoogleScholarPaper(
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            year=2024,
            venue="Test Conference",
            abstract="Test abstract",
            citations=100,
            url="https://example.com/paper",
            pdf_url="https://example.com/paper.pdf",
            scholar_id="abc123",
        )

        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2
        assert paper.citations == 100

    def test_paper_defaults(self):
        """Test GoogleScholarPaper default values."""
        paper = GoogleScholarPaper(title="Test")

        assert paper.authors == []
        assert paper.year is None
        assert paper.venue is None
        assert paper.abstract == ""
        assert paper.citations == 0
        assert paper.url is None
        assert paper.pdf_url is None


class TestGoogleScholarSearchResult:
    """Tests for GoogleScholarSearchResult model."""

    def test_result_creation(self):
        """Test creating a GoogleScholarSearchResult instance."""
        papers = [
            GoogleScholarPaper(title="Paper 1", citations=100),
            GoogleScholarPaper(title="Paper 2", citations=50),
        ]
        result = GoogleScholarSearchResult(papers=papers, query="test")

        assert len(result.papers) == 2
        assert result.query == "test"

    def test_result_empty(self):
        """Test empty GoogleScholarSearchResult."""
        result = GoogleScholarSearchResult(papers=[], query="no results")

        assert len(result.papers) == 0
