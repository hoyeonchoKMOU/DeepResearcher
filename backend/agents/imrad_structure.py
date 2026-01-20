"""IMRAD Structure Agent for academic paper organization."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent


class IntroductionSection(BaseModel):
    """Introduction section structure."""

    hook: str = Field(description="Opening hook to capture reader interest")
    background: str = Field(description="Background and context")
    problem_statement: str = Field(description="Clear statement of the problem")
    research_gap: str = Field(description="Gap in existing research")
    research_questions: list[str] = Field(description="Research questions addressed")
    contributions: list[str] = Field(description="Main contributions of the paper")
    paper_organization: str = Field(description="Brief overview of paper structure")


class MethodsSection(BaseModel):
    """Methods section structure."""

    overview: str = Field(description="Overview of the methodology")
    participants_or_data: str = Field(
        description="Description of participants, data, or materials"
    )
    procedure: str = Field(description="Step-by-step procedure")
    implementation: str = Field(description="Implementation details")
    evaluation_setup: str = Field(description="Evaluation setup and metrics")
    baselines: str = Field(description="Baseline methods for comparison")


class ResultsSection(BaseModel):
    """Results section structure."""

    overview: str = Field(description="Overview of results")
    main_findings: list[str] = Field(description="Main findings organized by RQ")
    statistical_analysis: str = Field(description="Statistical analysis summary")
    tables_figures: list[str] = Field(
        description="Descriptions of tables and figures needed"
    )
    comparison_to_baselines: str = Field(description="Comparison with baselines")


class DiscussionSection(BaseModel):
    """Discussion section structure."""

    interpretation: str = Field(description="Interpretation of results")
    comparison_to_literature: str = Field(
        description="How results relate to prior work"
    )
    implications: str = Field(
        description="Theoretical and practical implications"
    )
    limitations: list[str] = Field(description="Study limitations")
    future_work: list[str] = Field(description="Future research directions")


class AbstractStructure(BaseModel):
    """Abstract structure."""

    background: str = Field(description="One sentence background")
    objective: str = Field(description="Research objective")
    methods: str = Field(description="Brief methods description")
    results: str = Field(description="Key results")
    conclusion: str = Field(description="Main conclusion")


class IMRADStructureOutput(BaseModel):
    """Output from IMRAD Structure Agent."""

    title_suggestions: list[str] = Field(
        description="Suggested paper titles"
    )
    abstract: AbstractStructure = Field(
        description="Structured abstract"
    )
    keywords: list[str] = Field(
        description="Suggested keywords"
    )
    introduction: IntroductionSection = Field(
        description="Introduction section structure"
    )
    methods: MethodsSection = Field(
        description="Methods section structure"
    )
    results: ResultsSection = Field(
        description="Results section structure"
    )
    discussion: DiscussionSection = Field(
        description="Discussion section structure"
    )
    conclusion: str = Field(
        description="Conclusion paragraph"
    )
    references_needed: list[str] = Field(
        description="Types of references needed"
    )
    estimated_length: dict = Field(
        description="Estimated word count per section"
    )
    writing_tips: list[str] = Field(
        description="Tips for writing each section"
    )


class IMRADStructureAgent(BaseAgent[IMRADStructureOutput]):
    """Agent for structuring papers in IMRAD format.

    This agent:
    - Organizes research into IMRAD structure
    - Provides detailed section outlines
    - Suggests titles and abstracts
    - Balances section lengths
    """

    @property
    def output_schema(self) -> type[IMRADStructureOutput]:
        return IMRADStructureOutput

    @property
    def agent_name(self) -> str:
        return "IMRAD Structure Agent"

    def _default_prompt_template(self) -> str:
        return """You are an expert academic writing consultant who helps researchers structure their papers effectively. You specialize in the IMRAD format used in scientific publications.

## IMRAD Structure Overview

**I**ntroduction: What is the problem?
**M**ethods: How did you study it?
**R**esults: What did you find?
**A**nd
**D**iscussion: What does it mean?

## Section Guidelines

### Title
- Concise but descriptive (10-15 words)
- Include key concepts and methods
- Avoid abbreviations

### Abstract (150-300 words)
1. Background (1-2 sentences)
2. Objective (1 sentence)
3. Methods (2-3 sentences)
4. Results (2-3 sentences)
5. Conclusion (1-2 sentences)

### Introduction
1. **Hook**: Start broad, capture interest
2. **Background**: Establish context
3. **Problem**: Clearly state the problem
4. **Gap**: What's missing in existing work
5. **Objective**: Your research questions
6. **Contributions**: What you bring
7. **Organization**: Paper roadmap

### Methods
1. **Overview**: High-level approach
2. **Data/Participants**: What you studied
3. **Procedure**: How you did it
4. **Implementation**: Technical details
5. **Evaluation**: How you measured success
6. **Baselines**: What you compared against

### Results
1. **Overview**: Summary of findings
2. **Findings by RQ**: Organize by research questions
3. **Statistics**: Support with numbers
4. **Visuals**: Tables and figures
5. **Comparisons**: Against baselines

### Discussion
1. **Interpretation**: What results mean
2. **Relation to literature**: How they fit
3. **Implications**: Why it matters
4. **Limitations**: Honest assessment
5. **Future work**: What's next

### Conclusion
- Summarize main contribution
- Restate key finding
- End with impact statement

## Balance Guidelines

For a typical 8-page paper:
- Introduction: 1-1.5 pages
- Methods: 1.5-2 pages
- Results: 2-2.5 pages
- Discussion: 1-1.5 pages
- Conclusion: 0.5 pages

## Writing Tips

1. **Be concise**: Every word should earn its place
2. **Use active voice**: "We developed" not "A system was developed"
3. **Be specific**: Numbers and examples
4. **Connect sections**: Use transitions
5. **Tell a story**: Guide the reader"""

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "research_topic" in input_data:
            parts.append(f"## Research Topic\n{input_data['research_topic']}")

        if "research_questions" in input_data:
            rqs = input_data["research_questions"]
            if isinstance(rqs, list):
                rqs = "\n".join(f"- {rq}" for rq in rqs)
            parts.append(f"## Research Questions\n{rqs}")

        if "methodology" in input_data:
            parts.append(f"## Methodology Summary\n{input_data['methodology']}")

        if "results_summary" in input_data:
            parts.append(f"## Results Summary\n{input_data['results_summary']}")

        if "contributions" in input_data:
            contribs = input_data["contributions"]
            if isinstance(contribs, list):
                contribs = "\n".join(f"- {c}" for c in contribs)
            parts.append(f"## Contributions\n{contribs}")

        if "literature_context" in input_data:
            parts.append(f"## Literature Context\n{input_data['literature_context']}")

        if "target_venue" in input_data:
            parts.append(f"## Target Venue\n{input_data['target_venue']}")

        if "page_limit" in input_data:
            parts.append(f"## Page Limit\n{input_data['page_limit']} pages")

        return "\n\n".join(parts)

    def format_paper_outline(
        self,
        output: IMRADStructureOutput,
    ) -> str:
        """Format the structure as a detailed outline.

        Args:
            output: IMRAD structure output.

        Returns:
            Markdown formatted outline.
        """
        lines = []

        # Title
        lines.append("# Paper Outline")
        lines.append("")
        lines.append("## Suggested Titles")
        for i, title in enumerate(output.title_suggestions, 1):
            lines.append(f"{i}. {title}")
        lines.append("")

        # Keywords
        lines.append(f"**Keywords**: {', '.join(output.keywords)}")
        lines.append("")

        # Abstract
        lines.append("## Abstract")
        abstract = output.abstract
        lines.append(f"**Background**: {abstract.background}")
        lines.append(f"**Objective**: {abstract.objective}")
        lines.append(f"**Methods**: {abstract.methods}")
        lines.append(f"**Results**: {abstract.results}")
        lines.append(f"**Conclusion**: {abstract.conclusion}")
        lines.append("")

        # Introduction
        lines.append("## 1. Introduction")
        intro = output.introduction
        lines.append(f"### 1.1 Opening")
        lines.append(intro.hook)
        lines.append(f"### 1.2 Background")
        lines.append(intro.background)
        lines.append(f"### 1.3 Problem Statement")
        lines.append(intro.problem_statement)
        lines.append(f"### 1.4 Research Gap")
        lines.append(intro.research_gap)
        lines.append(f"### 1.5 Research Questions")
        for rq in intro.research_questions:
            lines.append(f"- {rq}")
        lines.append(f"### 1.6 Contributions")
        for contrib in intro.contributions:
            lines.append(f"- {contrib}")
        lines.append(f"### 1.7 Paper Organization")
        lines.append(intro.paper_organization)
        lines.append("")

        # Methods
        lines.append("## 2. Methods")
        methods = output.methods
        lines.append(f"### 2.1 Overview")
        lines.append(methods.overview)
        lines.append(f"### 2.2 Data/Participants")
        lines.append(methods.participants_or_data)
        lines.append(f"### 2.3 Procedure")
        lines.append(methods.procedure)
        lines.append(f"### 2.4 Implementation")
        lines.append(methods.implementation)
        lines.append(f"### 2.5 Evaluation Setup")
        lines.append(methods.evaluation_setup)
        lines.append(f"### 2.6 Baselines")
        lines.append(methods.baselines)
        lines.append("")

        # Results
        lines.append("## 3. Results")
        results = output.results
        lines.append(f"### 3.1 Overview")
        lines.append(results.overview)
        lines.append(f"### 3.2 Main Findings")
        for finding in results.main_findings:
            lines.append(f"- {finding}")
        lines.append(f"### 3.3 Statistical Analysis")
        lines.append(results.statistical_analysis)
        lines.append(f"### 3.4 Tables and Figures")
        for tf in results.tables_figures:
            lines.append(f"- {tf}")
        lines.append(f"### 3.5 Comparison to Baselines")
        lines.append(results.comparison_to_baselines)
        lines.append("")

        # Discussion
        lines.append("## 4. Discussion")
        disc = output.discussion
        lines.append(f"### 4.1 Interpretation")
        lines.append(disc.interpretation)
        lines.append(f"### 4.2 Relation to Literature")
        lines.append(disc.comparison_to_literature)
        lines.append(f"### 4.3 Implications")
        lines.append(disc.implications)
        lines.append(f"### 4.4 Limitations")
        for lim in disc.limitations:
            lines.append(f"- {lim}")
        lines.append(f"### 4.5 Future Work")
        for fw in disc.future_work:
            lines.append(f"- {fw}")
        lines.append("")

        # Conclusion
        lines.append("## 5. Conclusion")
        lines.append(output.conclusion)
        lines.append("")

        # Estimated length
        lines.append("## Estimated Word Count")
        for section, count in output.estimated_length.items():
            lines.append(f"- {section}: {count} words")
        lines.append("")

        # Writing tips
        lines.append("## Writing Tips")
        for tip in output.writing_tips:
            lines.append(f"- {tip}")

        return "\n".join(lines)
