"""Literature Evaluation Agent for systematic review and gap analysis."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.utils.prompt_loader import load_lr_evaluation_prompt


class PaperEvaluation(BaseModel):
    """Evaluation of a single paper."""

    paper_id: str = Field(description="Paper identifier")
    title: str = Field(description="Paper title")
    methodology_rigor: float = Field(
        ge=0.0, le=1.0,
        description="Methodology rigor score (0-1)"
    )
    contribution_significance: float = Field(
        ge=0.0, le=1.0,
        description="Contribution significance score (0-1)"
    )
    relevance_to_research: float = Field(
        ge=0.0, le=1.0,
        description="Relevance to our research (0-1)"
    )
    strengths: list[str] = Field(description="Paper strengths")
    weaknesses: list[str] = Field(description="Paper weaknesses")
    key_insights: list[str] = Field(
        description="Key insights we can use"
    )


class ResearchGap(BaseModel):
    """Identified gap in the literature."""

    gap_description: str = Field(description="Description of the gap")
    gap_type: str = Field(
        description="Type: methodological, theoretical, empirical, or application"
    )
    opportunity: str = Field(
        description="Research opportunity this gap presents"
    )
    supporting_evidence: list[str] = Field(
        description="Evidence from papers supporting this gap"
    )
    priority: str = Field(
        description="Priority: high, medium, or low"
    )


class ResearchTrend(BaseModel):
    """Identified trend in the literature."""

    trend_description: str = Field(description="Description of the trend")
    direction: str = Field(
        description="Direction: emerging, established, or declining"
    )
    key_papers: list[str] = Field(
        description="Papers exemplifying this trend"
    )
    implications: str = Field(
        description="Implications for our research"
    )


class LiteratureEvaluationOutput(BaseModel):
    """Output from Literature Evaluation Agent."""

    overall_assessment: str = Field(
        description="Overall assessment of the literature"
    )
    coverage_score: float = Field(
        ge=0.0, le=1.0,
        description="How well the literature covers our topic (0-1)"
    )
    paper_evaluations: list[PaperEvaluation] = Field(
        description="Individual paper evaluations"
    )
    comparative_matrix: dict = Field(
        description="Comparison matrix of papers by criteria"
    )
    research_gaps: list[ResearchGap] = Field(
        description="Identified gaps in the literature"
    )
    research_trends: list[ResearchTrend] = Field(
        description="Current trends in the field"
    )
    methodological_patterns: list[str] = Field(
        description="Common methodological approaches"
    )
    theoretical_foundations: list[str] = Field(
        description="Theoretical frameworks used"
    )
    recommendations: list[str] = Field(
        description="Recommendations for our research"
    )
    needs_more_literature: bool = Field(
        default=False,
        description="Whether we need to search for more papers"
    )
    suggested_searches: list[str] = Field(
        default_factory=list,
        description="Suggested additional searches if needed"
    )


class LiteratureEvaluationAgent(BaseAgent[LiteratureEvaluationOutput]):
    """Agent for systematic evaluation of literature.

    This agent:
    - Evaluates papers systematically
    - Creates comparison matrices
    - Identifies research gaps
    - Analyzes trends in the field
    """

    @property
    def output_schema(self) -> type[LiteratureEvaluationOutput]:
        return LiteratureEvaluationOutput

    @property
    def agent_name(self) -> str:
        return "Literature Evaluation Agent"

    def _default_prompt_template(self) -> str:
        # Load prompt from file
        prompt = load_lr_evaluation_prompt()
        if not prompt:
            raise ValueError("Failed to load LR evaluation prompt from data/prompts/LR/evaluation_prompt.md")
        return prompt

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "research_questions" in input_data:
            rqs = input_data["research_questions"]
            if isinstance(rqs, list):
                rqs = "\n".join(f"- {rq}" for rq in rqs)
            parts.append(f"## Our Research Questions\n{rqs}")

        if "paper_summaries" in input_data:
            summaries = input_data["paper_summaries"]
            if isinstance(summaries, list):
                for i, summary in enumerate(summaries, 1):
                    parts.append(f"### Paper {i}: {summary.get('title', 'Unknown')}")
                    parts.append(summary.get('content', str(summary))[:4000])
            else:
                parts.append(f"## Paper Summaries\n{summaries}")

        if "research_topic" in input_data:
            parts.append(f"## Research Topic\n{input_data['research_topic']}")

        if "evaluation_focus" in input_data:
            parts.append(f"## Evaluation Focus\n{input_data['evaluation_focus']}")

        return "\n\n".join(parts)

    def format_comparison_matrix(
        self,
        output: LiteratureEvaluationOutput,
    ) -> str:
        """Format evaluation as a comparison matrix in markdown.

        Args:
            output: Literature evaluation output.

        Returns:
            Markdown formatted comparison matrix.
        """
        lines = ["# Literature Comparison Matrix", ""]

        # Header
        headers = ["Paper", "Rigor", "Significance", "Relevance", "Key Strength", "Key Weakness"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Rows
        for eval in output.paper_evaluations:
            row = [
                eval.title[:30] + "..." if len(eval.title) > 30 else eval.title,
                f"{eval.methodology_rigor:.1f}",
                f"{eval.contribution_significance:.1f}",
                f"{eval.relevance_to_research:.1f}",
                eval.strengths[0] if eval.strengths else "-",
                eval.weaknesses[0] if eval.weaknesses else "-",
            ]
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")

        # Gaps
        lines.append("## Research Gaps")
        for gap in output.research_gaps:
            lines.append(f"### {gap.gap_type.title()} Gap (Priority: {gap.priority})")
            lines.append(f"**Gap**: {gap.gap_description}")
            lines.append(f"**Opportunity**: {gap.opportunity}")
            lines.append("")

        # Trends
        lines.append("## Research Trends")
        for trend in output.research_trends:
            lines.append(f"### {trend.direction.title()}: {trend.trend_description}")
            lines.append(f"**Implications**: {trend.implications}")
            lines.append("")

        return "\n".join(lines)
