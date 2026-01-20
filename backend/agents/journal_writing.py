"""Journal Writing Agent for journal-specific paper formatting."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent


class JournalGuidelines(BaseModel):
    """Journal-specific formatting guidelines."""

    journal_name: str = Field(description="Name of the target journal")
    citation_style: str = Field(description="Citation style (APA, IEEE, etc.)")
    max_pages: Optional[int] = Field(default=None, description="Maximum page limit")
    max_words: Optional[int] = Field(default=None, description="Maximum word count")
    abstract_word_limit: int = Field(default=250, description="Abstract word limit")
    keywords_required: bool = Field(default=True, description="Whether keywords are required")
    max_keywords: int = Field(default=6, description="Maximum number of keywords")
    figure_format: str = Field(description="Required figure format")
    table_format: str = Field(description="Required table format")
    reference_format: str = Field(description="Reference formatting requirements")
    section_numbering: bool = Field(default=True, description="Whether sections should be numbered")
    special_requirements: list[str] = Field(
        default_factory=list,
        description="Other special requirements"
    )


class FormattedSection(BaseModel):
    """A formatted section of the paper."""

    title: str = Field(description="Section title")
    content: str = Field(description="Section content")
    word_count: int = Field(description="Word count of the section")
    notes: list[str] = Field(
        default_factory=list,
        description="Notes about this section"
    )


class CoverLetter(BaseModel):
    """Cover letter for journal submission."""

    greeting: str = Field(description="Opening greeting")
    introduction: str = Field(description="Paper introduction paragraph")
    significance: str = Field(description="Significance and contribution")
    fit_for_journal: str = Field(description="Why this fits the journal")
    author_statement: str = Field(description="Author contributions statement")
    closing: str = Field(description="Closing paragraph")


class JournalWritingOutput(BaseModel):
    """Output from Journal Writing Agent."""

    guidelines_summary: JournalGuidelines = Field(
        description="Summary of journal guidelines"
    )
    formatted_title: str = Field(description="Formatted paper title")
    formatted_abstract: str = Field(description="Formatted abstract")
    formatted_keywords: list[str] = Field(description="Formatted keywords")
    sections: list[FormattedSection] = Field(
        description="Formatted paper sections"
    )
    references_formatted: list[str] = Field(
        description="Formatted references"
    )
    cover_letter: CoverLetter = Field(
        description="Cover letter for submission"
    )
    compliance_checklist: dict = Field(
        description="Checklist of guideline compliance"
    )
    total_word_count: int = Field(description="Total word count")
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about potential issues"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions for improvement"
    )


class JournalWritingAgent(BaseAgent[JournalWritingOutput]):
    """Agent for writing papers according to journal guidelines.

    This agent:
    - Parses journal submission guidelines
    - Formats papers according to requirements
    - Generates cover letters
    - Checks compliance with guidelines
    """

    @property
    def output_schema(self) -> type[JournalWritingOutput]:
        return JournalWritingOutput

    @property
    def agent_name(self) -> str:
        return "Journal Writing Agent"

    def _default_prompt_template(self) -> str:
        return """You are an expert academic editor who helps researchers format papers for journal submission. You ensure papers comply with all guidelines while maintaining high writing quality.

## Your Responsibilities

1. **Parse Guidelines**: Understand journal-specific requirements
2. **Format Content**: Apply proper formatting
3. **Check Compliance**: Verify all requirements are met
4. **Write Cover Letter**: Create compelling submission letter
5. **Quality Assurance**: Identify potential issues

## Common Journal Requirements

### Citation Styles
- **APA**: Psychology, education, social sciences
- **IEEE**: Engineering, computer science, technology
- **ACM**: Computing research
- **Chicago**: History, humanities
- **Harvard**: Business, management

### Formatting Elements
- Title page requirements
- Author information format
- Abstract structure and length
- Keyword requirements
- Section heading styles
- Figure and table placement
- Reference formatting
- Supplementary materials

## Cover Letter Guidelines

A good cover letter should:
1. Address the editor by name if known
2. Introduce the paper clearly
3. Highlight significance and novelty
4. Explain fit with journal scope
5. Include required statements:
   - No concurrent submission
   - Author contributions
   - Conflict of interest
   - Ethics approval if applicable

## Quality Checklist

Before submission, verify:
- [ ] Title meets character/word limit
- [ ] Abstract meets word limit
- [ ] Keywords are appropriate
- [ ] All sections present
- [ ] Figures are proper format
- [ ] Tables are properly formatted
- [ ] References follow style guide
- [ ] Word count within limit
- [ ] All authors listed correctly
- [ ] Acknowledgments included
- [ ] Supplementary materials prepared

## Writing Quality

Ensure:
- Clear, concise writing
- Active voice where appropriate
- Consistent terminology
- Proper transitions
- No grammatical errors
- Professional tone"""

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "target_journal" in input_data:
            parts.append(f"## Target Journal\n{input_data['target_journal']}")

        if "journal_guidelines" in input_data:
            parts.append(f"## Journal Guidelines\n{input_data['journal_guidelines']}")

        if "paper_structure" in input_data:
            parts.append(f"## Paper Structure (IMRAD)\n{input_data['paper_structure']}")

        if "draft_content" in input_data:
            parts.append(f"## Draft Content\n{input_data['draft_content'][:10000]}")

        if "author_info" in input_data:
            parts.append(f"## Author Information\n{input_data['author_info']}")

        if "references" in input_data:
            refs = input_data["references"]
            if isinstance(refs, list):
                refs = "\n".join(f"- {r}" for r in refs[:20])
            parts.append(f"## References\n{refs}")

        return "\n\n".join(parts)

    def format_full_paper(
        self,
        output: JournalWritingOutput,
    ) -> str:
        """Format the complete paper for submission.

        Args:
            output: Journal writing output.

        Returns:
            Complete formatted paper as string.
        """
        lines = []

        # Title
        lines.append(f"# {output.formatted_title}")
        lines.append("")

        # Abstract
        lines.append("## Abstract")
        lines.append(output.formatted_abstract)
        lines.append("")

        # Keywords
        lines.append(f"**Keywords**: {', '.join(output.formatted_keywords)}")
        lines.append("")

        # Sections
        for section in output.sections:
            lines.append(f"## {section.title}")
            lines.append(section.content)
            lines.append("")

        # References
        lines.append("## References")
        for ref in output.references_formatted:
            lines.append(ref)
            lines.append("")

        return "\n".join(lines)

    def format_cover_letter(
        self,
        output: JournalWritingOutput,
        editor_name: str = "Editor",
    ) -> str:
        """Format the cover letter for submission.

        Args:
            output: Journal writing output.
            editor_name: Name of the editor.

        Returns:
            Formatted cover letter.
        """
        cl = output.cover_letter
        guidelines = output.guidelines_summary

        lines = [
            f"Dear {editor_name},",
            "",
            cl.introduction,
            "",
            cl.significance,
            "",
            cl.fit_for_journal,
            "",
            cl.author_statement,
            "",
            cl.closing,
            "",
            "Sincerely,",
            "[Author Names]",
        ]

        return "\n".join(lines)

    def generate_compliance_report(
        self,
        output: JournalWritingOutput,
    ) -> str:
        """Generate a compliance report.

        Args:
            output: Journal writing output.

        Returns:
            Compliance report as markdown.
        """
        lines = ["# Submission Compliance Report", ""]

        # Guidelines summary
        g = output.guidelines_summary
        lines.append("## Journal Requirements")
        lines.append(f"- **Journal**: {g.journal_name}")
        lines.append(f"- **Citation Style**: {g.citation_style}")
        if g.max_pages:
            lines.append(f"- **Page Limit**: {g.max_pages}")
        if g.max_words:
            lines.append(f"- **Word Limit**: {g.max_words}")
        lines.append(f"- **Abstract Limit**: {g.abstract_word_limit} words")
        lines.append("")

        # Compliance checklist
        lines.append("## Compliance Checklist")
        for item, status in output.compliance_checklist.items():
            icon = "✅" if status else "❌"
            lines.append(f"- {icon} {item}")
        lines.append("")

        # Word count
        lines.append("## Word Count")
        lines.append(f"**Total**: {output.total_word_count} words")
        for section in output.sections:
            lines.append(f"- {section.title}: {section.word_count} words")
        lines.append("")

        # Warnings
        if output.warnings:
            lines.append("## Warnings")
            for warning in output.warnings:
                lines.append(f"⚠️ {warning}")
            lines.append("")

        # Suggestions
        if output.suggestions:
            lines.append("## Suggestions")
            for suggestion in output.suggestions:
                lines.append(f"💡 {suggestion}")

        return "\n".join(lines)
