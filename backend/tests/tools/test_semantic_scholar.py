"""Unit tests for Semantic Scholar search tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from backend.tools.semantic_scholar import (
    SemanticScholarTool,
    PaperInfo,
    SearchResult,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
)


class TestSemanticScholarTool:
    """Tests for SemanticScholarTool class."""

    @pytest.fixture
    def tool(self):
        """Create a SemanticScholarTool instance."""
        with patch("backend.tools.semantic_scholar.get_settings") as mock_settings:
            mock_settings.return_value.semantic_scholar_api_key = None
            return SemanticScholarTool()

    @pytest.fixture
    def mock_paper_response(self):
        """Sample API response for paper search."""
        return {
            "total": 2,
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Test Paper 1",
                    "abstract": "This is a test abstract",
                    "authors": [
                        {"name": "Author One"},
                        {"name": "Author Two"},
                    ],
                    "year": 2024,
                    "venue": "Test Conference",
                    "citationCount": 100,
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "externalIds": {"DOI": "10.1234/test"},
                    "url": "https://semanticscholar.org/paper/abc123",
                    "fieldsOfStudy": ["Computer Science"],
                    "publicationTypes": ["Conference"],
                },
                {
                    "paperId": "def456",
                    "title": "Test Paper 2",
                    "abstract": "Another test abstract",
                    "authors": [{"name": "Author Three"}],
                    "year": 2023,
                    "venue": "Test Journal",
                    "citationCount": 50,
                    "openAccessPdf": None,
                    "externalIds": {},
                    "url": "https://semanticscholar.org/paper/def456",
                    "fieldsOfStudy": ["Computer Science", "AI"],
                    "publicationTypes": ["JournalArticle"],
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_search_papers_success(self, tool, mock_paper_response):
        """Test successful paper search."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_paper_response
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(
                query="machine learning",
                year_start=2023,
                year_end=2025,
                limit=10,
            )

            assert isinstance(result, SearchResult)
            assert len(result.papers) == 2
            assert result.total == 2
            assert result.query == "machine learning"

            # Check first paper
            paper1 = result.papers[0]
            assert paper1.paper_id == "abc123"
            assert paper1.title == "Test Paper 1"
            assert paper1.citation_count == 100
            assert paper1.open_access_pdf == "https://example.com/paper.pdf"
            assert len(paper1.authors) == 2

    @pytest.mark.asyncio
    async def test_search_papers_empty_results(self, tool):
        """Test search with no results."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"total": 0, "data": []}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(query="nonexistent topic")

            assert isinstance(result, SearchResult)
            assert len(result.papers) == 0
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_search_papers_http_error(self, tool):
        """Test handling of HTTP errors."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection failed")

            result = await tool.search_papers(query="test query")

            assert isinstance(result, SearchResult)
            assert len(result.papers) == 0
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_search_papers_rate_limit_retry(self, tool, mock_paper_response):
        """Test retry logic on 429 rate limit."""
        with patch("httpx.AsyncClient.get") as mock_get:
            # First two calls return 429, third succeeds
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_error = httpx.HTTPStatusError(
                "Rate limited",
                request=MagicMock(),
                response=rate_limit_response,
            )

            success_response = MagicMock()
            success_response.json.return_value = mock_paper_response
            success_response.raise_for_status = MagicMock()

            mock_get.side_effect = [
                rate_limit_error,  # First attempt fails
                rate_limit_error,  # Second attempt fails
                success_response,  # Third attempt succeeds
            ]

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await tool.search_papers(query="test query")

                # Verify retries happened
                assert mock_sleep.call_count == 2
                # Check exponential backoff delays
                mock_sleep.assert_any_call(RETRY_DELAY_BASE * 1)  # 2^0 = 1
                mock_sleep.assert_any_call(RETRY_DELAY_BASE * 2)  # 2^1 = 2

                # Result should be successful
                assert len(result.papers) == 2

    @pytest.mark.asyncio
    async def test_search_papers_rate_limit_exhausted(self, tool):
        """Test when all retry attempts are exhausted."""
        with patch("httpx.AsyncClient.get") as mock_get:
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_error = httpx.HTTPStatusError(
                "Rate limited",
                request=MagicMock(),
                response=rate_limit_response,
            )
            mock_get.side_effect = rate_limit_error

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await tool.search_papers(query="test query")

                assert len(result.papers) == 0

    @pytest.mark.asyncio
    async def test_search_papers_min_citations_filter(self, tool, mock_paper_response):
        """Test minimum citation count filter."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_paper_response
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(
                query="test",
                min_citations=75,  # Should filter out the second paper (50 citations)
            )

            assert len(result.papers) == 1
            assert result.papers[0].citation_count >= 75

    @pytest.mark.asyncio
    async def test_search_papers_sorted_by_citations(self, tool, mock_paper_response):
        """Test that results are sorted by citation count."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_paper_response
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.search_papers(query="test")

            # Results should be sorted by citation count descending
            citations = [p.citation_count for p in result.papers]
            assert citations == sorted(citations, reverse=True)

    @pytest.mark.asyncio
    async def test_get_paper_details_success(self, tool):
        """Test getting details for a specific paper."""
        paper_data = {
            "paperId": "test123",
            "title": "Test Paper",
            "abstract": "Test abstract",
            "authors": [{"name": "Test Author"}],
            "year": 2024,
            "venue": "Test Venue",
            "citationCount": 42,
            "openAccessPdf": None,
            "externalIds": {"DOI": "10.1234/test"},
            "url": "https://semanticscholar.org/paper/test123",
            "fieldsOfStudy": ["Computer Science"],
            "publicationTypes": ["Conference"],
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = paper_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.get_paper_details("test123")

            assert result is not None
            assert result.paper_id == "test123"
            assert result.title == "Test Paper"
            assert result.citation_count == 42

    @pytest.mark.asyncio
    async def test_get_paper_details_not_found(self, tool):
        """Test paper details when paper is not found."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Not found")

            result = await tool.get_paper_details("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_citations(self, tool):
        """Test getting citations for a paper."""
        citations_data = {
            "data": [
                {
                    "citingPaper": {
                        "paperId": "cite1",
                        "title": "Citing Paper 1",
                        "authors": [{"name": "Author A"}],
                        "year": 2024,
                        "citationCount": 10,
                    }
                },
                {
                    "citingPaper": {
                        "paperId": "cite2",
                        "title": "Citing Paper 2",
                        "authors": [{"name": "Author B"}],
                        "year": 2023,
                        "citationCount": 5,
                    }
                },
            ]
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = citations_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.get_citations("test123", limit=10)

            assert len(result) == 2
            assert result[0].paper_id == "cite1"
            assert result[1].paper_id == "cite2"

    @pytest.mark.asyncio
    async def test_get_references(self, tool):
        """Test getting references for a paper."""
        references_data = {
            "data": [
                {
                    "citedPaper": {
                        "paperId": "ref1",
                        "title": "Referenced Paper 1",
                        "authors": [{"name": "Author X"}],
                        "year": 2020,
                        "citationCount": 100,
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = references_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await tool.get_references("test123", limit=10)

            assert len(result) == 1
            assert result[0].paper_id == "ref1"


class TestPaperInfo:
    """Tests for PaperInfo model."""

    def test_paper_info_creation(self):
        """Test creating a PaperInfo instance."""
        paper = PaperInfo(
            paper_id="test123",
            title="Test Paper",
            abstract="Test abstract",
            authors=["Author 1", "Author 2"],
            year=2024,
            venue="Test Conference",
            citation_count=50,
            open_access_pdf="https://example.com/paper.pdf",
            doi="10.1234/test",
            url="https://semanticscholar.org/paper/test123",
            fields_of_study=["Computer Science"],
            publication_types=["Conference"],
        )

        assert paper.paper_id == "test123"
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2

    def test_paper_info_defaults(self):
        """Test PaperInfo default values."""
        paper = PaperInfo(paper_id="test", title="Test")

        assert paper.abstract is None
        assert paper.authors == []
        assert paper.year is None
        assert paper.citation_count == 0
        assert paper.fields_of_study == []


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self):
        """Test creating a SearchResult instance."""
        papers = [
            PaperInfo(paper_id="1", title="Paper 1"),
            PaperInfo(paper_id="2", title="Paper 2"),
        ]
        result = SearchResult(papers=papers, total=100, query="test query")

        assert len(result.papers) == 2
        assert result.total == 100
        assert result.query == "test query"

    def test_search_result_empty(self):
        """Test empty SearchResult."""
        result = SearchResult(papers=[], total=0, query="no results")

        assert len(result.papers) == 0
        assert result.total == 0
