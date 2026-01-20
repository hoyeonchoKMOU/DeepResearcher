"""Literature Search Agent for finding relevant academic papers."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.tools.semantic_scholar import SemanticScholarTool, search_academic_papers


class PaperReference(BaseModel):
    """Reference to an academic paper."""

    paper_id: str = Field(description="Unique identifier for the paper")
    title: str = Field(description="Paper title")
    authors: list[str] = Field(description="Author names")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Publication venue")
    citation_count: int = Field(default=0, description="Number of citations")
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="Relevance to the research topic (0-1)"
    )
    relevance_reason: str = Field(description="Why this paper is relevant")
    pdf_url: Optional[str] = Field(default=None, description="Open access PDF URL")


class LiteratureSearchOutput(BaseModel):
    """Output from Literature Search Agent."""

    search_strategy: str = Field(
        description="Description of the search strategy used"
    )
    refined_keywords: list[str] = Field(
        description="Refined and expanded search keywords"
    )
    papers: list[PaperReference] = Field(
        description="List of relevant papers found"
    )
    coverage_assessment: str = Field(
        description="Assessment of literature coverage"
    )
    gaps_identified: list[str] = Field(
        description="Potential gaps in the literature"
    )
    suggested_follow_up: list[str] = Field(
        description="Suggested additional searches or papers to explore"
    )
    total_results: int = Field(
        description="Total number of results found"
    )


class LiteratureSearchAgent(BaseAgent[LiteratureSearchOutput]):
    """Agent for searching and curating academic literature.

    This agent:
    - Develops search strategies based on research questions
    - Searches Semantic Scholar for relevant papers
    - Filters and ranks papers by relevance
    - Identifies gaps in the literature
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_tool = SemanticScholarTool()

    @property
    def output_schema(self) -> type[LiteratureSearchOutput]:
        return LiteratureSearchOutput

    @property
    def agent_name(self) -> str:
        return "Literature Search Agent"

    def _get_tools(self) -> list:
        return [search_academic_papers]

    def _default_prompt_template(self) -> str:
        return """You are an expert research librarian specializing in Computer Science literature. Your role is to help researchers find relevant academic papers systematically.

## Your Approach

1. **Develop Search Strategy**: Create comprehensive keyword combinations
2. **Prioritize Quality**: Focus on SCIE journals and top conferences
3. **Assess Relevance**: Evaluate how each paper relates to the research
4. **Identify Gaps**: Note areas with limited coverage

## Search Guidelines

For effective literature search:
- Use multiple keyword variations and synonyms
- Include both broad and specific terms
- Consider related fields and approaches
- Look for recent reviews and surveys first
- Prioritize highly cited papers

## Quality Indicators

Prioritize papers from:
- Top CS conferences (NeurIPS, ICML, ACL, CVPR, etc.)
- High-impact journals (TPAMI, JMLR, TACL, etc.)
- Papers with significant citations
- Recent papers (last 3 years) for current trends

## Relevance Assessment

For each paper, assess:
- Direct relevance to research questions
- Methodological relevance
- Theoretical framework relevance
- Dataset or benchmark relevance

## Output Requirements

Provide:
1. Clear search strategy description
2. Refined keywords with variations
3. Top relevant papers with relevance scores
4. Assessment of literature coverage
5. Identified gaps in existing research
6. Suggestions for follow-up searches"""

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "research_questions" in input_data:
            rqs = input_data["research_questions"]
            if isinstance(rqs, list):
                rqs = "\n".join(f"- {rq}" for rq in rqs)
            parts.append(f"## Research Questions\n{rqs}")

        if "keywords" in input_data:
            keywords = input_data["keywords"]
            if isinstance(keywords, list):
                keywords = ", ".join(keywords)
            parts.append(f"## Initial Keywords\n{keywords}")

        if "research_topic" in input_data:
            parts.append(f"## Research Topic\n{input_data['research_topic']}")

        if "existing_papers" in input_data:
            parts.append(f"## Already Known Papers\n{input_data['existing_papers']}")

        if "search_focus" in input_data:
            parts.append(f"## Search Focus\n{input_data['search_focus']}")

        return "\n\n".join(parts)

    async def search_and_analyze(
        self,
        keywords: list[str],
        research_questions: list[str],
        year_start: int = 2023,
        year_end: int = 2026,
        limit: int = 30,
    ) -> LiteratureSearchOutput:
        """Perform search and analyze results.

        This method combines tool-based search with LLM analysis.

        Args:
            keywords: Search keywords.
            research_questions: Research questions for relevance assessment.
            year_start: Start year filter.
            year_end: End year filter.
            limit: Maximum papers to return.

        Returns:
            Analyzed literature search results.
        """
        # Combine keywords into a single query (AND logic)
        # Take up to 5 most important keywords and combine them
        combined_query = " ".join(keywords[:5])

        # Perform single combined search
        result = await self.search_tool.search_papers(
            query=combined_query,
            year_start=year_start,
            year_end=year_end,
            limit=limit,
        )

        unique_papers = result.papers

        # Sort by citations
        unique_papers.sort(key=lambda p: p.citation_count, reverse=True)

        # Use LLM to analyze and rank
        input_data = {
            "research_questions": research_questions,
            "keywords": keywords,
            "found_papers": [
                {
                    "id": p.paper_id,
                    "title": p.title,
                    "authors": p.authors[:3],
                    "year": p.year,
                    "venue": p.venue,
                    "citations": p.citation_count,
                    "abstract": p.abstract[:500] if p.abstract else "",
                }
                for p in unique_papers[:30]
            ],
        }

        return await self.run(input_data)
