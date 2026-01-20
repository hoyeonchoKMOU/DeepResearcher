"""PDF Summary Agent for summarizing academic papers."""

from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.llm.gemini import GeminiLLM
from backend.tools.pdf_processor import PDFProcessor, LocalPDFScanner, ParsedPDF

logger = structlog.get_logger(__name__)

# Fast model for quick summarization (Gemini 2.0 Flash)
FAST_SUMMARY_MODEL = "gemini-2.0-flash"


class KeyContribution(BaseModel):
    """A key contribution from the paper."""

    contribution: str = Field(description="Description of the contribution")
    type: str = Field(
        description="Type: theoretical, methodological, empirical, or practical"
    )
    significance: str = Field(description="Why this contribution is significant")


class MethodologySummary(BaseModel):
    """Summary of the paper's methodology."""

    approach: str = Field(description="Overall methodological approach")
    techniques: list[str] = Field(description="Specific techniques used")
    datasets: list[str] = Field(default_factory=list, description="Datasets used")
    evaluation_metrics: list[str] = Field(
        default_factory=list,
        description="Evaluation metrics employed"
    )


class PDFSummaryOutput(BaseModel):
    """Output from PDF Summary Agent."""

    title: str = Field(description="Paper title")
    authors: list[str] = Field(description="Paper authors")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Publication venue")

    abstract_summary: str = Field(
        description="Concise summary of the abstract"
    )
    problem_statement: str = Field(
        description="The problem this paper addresses"
    )
    key_contributions: list[KeyContribution] = Field(
        description="Main contributions of the paper"
    )
    methodology: MethodologySummary = Field(
        description="Summary of methodology"
    )
    main_results: list[str] = Field(
        description="Main findings and results"
    )
    limitations: list[str] = Field(
        description="Acknowledged or identified limitations"
    )
    future_work: list[str] = Field(
        default_factory=list,
        description="Suggested future work directions"
    )
    relevance_to_research: str = Field(
        description="How this paper relates to our research"
    )
    quality_assessment: str = Field(
        description="Assessment of paper quality and rigor"
    )
    key_citations: list[str] = Field(
        default_factory=list,
        description="Important papers cited that we should also read"
    )


class PDFSummaryAgent(BaseAgent[PDFSummaryOutput]):
    """Agent for summarizing academic papers in structured format.

    This agent:
    - Extracts key information from papers
    - Identifies contributions and methodology
    - Assesses relevance to the research
    - Produces structured markdown summaries
    """

    @property
    def output_schema(self) -> type[PDFSummaryOutput]:
        return PDFSummaryOutput

    @property
    def agent_name(self) -> str:
        return "PDF Summary Agent"

    def _default_prompt_template(self) -> str:
        return """You are an expert academic reader who excels at extracting and synthesizing information from research papers. Your summaries are thorough yet concise.

## Your Approach

1. **Extract Key Information**: Identify the core contributions and findings
2. **Understand Methodology**: Break down the approach clearly
3. **Critical Assessment**: Evaluate strengths and limitations
4. **Contextualize**: Relate to the broader research context

## Summary Guidelines

For each paper, identify:

### Problem & Motivation
- What problem does this paper solve?
- Why is this problem important?
- What gap in existing work does it address?

### Contributions
- What are the main contributions?
- Are they theoretical, methodological, empirical, or practical?
- What makes them significant?

### Methodology
- What approach do they use?
- What datasets or benchmarks?
- What baselines do they compare against?
- What metrics do they use?

### Results
- What are the main findings?
- How do they compare to prior work?
- Are the results statistically significant?

### Limitations
- What limitations do the authors acknowledge?
- What other limitations do you identify?
- What assumptions might not hold?

### Relevance
- How does this relate to our research?
- What can we learn or build upon?
- Are there methods or ideas to adopt?

## Quality Assessment Criteria

Consider:
- Clarity of writing and presentation
- Rigor of methodology
- Validity of experimental design
- Reproducibility of results
- Significance of contributions"""

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "paper_text" in input_data:
            parts.append(f"## Paper Content\n{input_data['paper_text'][:15000]}")

        if "paper_sections" in input_data:
            sections = input_data["paper_sections"]
            if isinstance(sections, list):
                for section in sections:
                    parts.append(f"### {section.get('title', 'Section')}\n{section.get('content', '')[:3000]}")

        if "research_context" in input_data:
            parts.append(f"## Our Research Context\n{input_data['research_context']}")

        if "research_questions" in input_data:
            rqs = input_data["research_questions"]
            if isinstance(rqs, list):
                rqs = "\n".join(f"- {rq}" for rq in rqs)
            parts.append(f"## Our Research Questions\n{rqs}")

        if "title" in input_data:
            parts.append(f"## Paper Title\n{input_data['title']}")

        if "abstract" in input_data:
            parts.append(f"## Abstract\n{input_data['abstract']}")

        return "\n\n".join(parts)

    def format_as_markdown(self, output: PDFSummaryOutput) -> str:
        """Format the summary output as markdown.

        Args:
            output: PDF summary output.

        Returns:
            Formatted markdown string.
        """
        lines = []

        # Header
        lines.append(f"# {output.title}")
        lines.append("")

        # Metadata
        lines.append("## Metadata")
        if output.authors:
            lines.append(f"- **Authors**: {', '.join(output.authors)}")
        if output.year:
            lines.append(f"- **Year**: {output.year}")
        if output.venue:
            lines.append(f"- **Venue**: {output.venue}")
        lines.append("")

        # Abstract
        lines.append("## Summary")
        lines.append(output.abstract_summary)
        lines.append("")

        # Problem
        lines.append("## Problem Statement")
        lines.append(output.problem_statement)
        lines.append("")

        # Contributions
        lines.append("## Key Contributions")
        for contrib in output.key_contributions:
            lines.append(f"### {contrib.type.title()}")
            lines.append(f"**Contribution**: {contrib.contribution}")
            lines.append(f"**Significance**: {contrib.significance}")
            lines.append("")

        # Methodology
        lines.append("## Methodology")
        lines.append(f"**Approach**: {output.methodology.approach}")
        if output.methodology.techniques:
            lines.append(f"**Techniques**: {', '.join(output.methodology.techniques)}")
        if output.methodology.datasets:
            lines.append(f"**Datasets**: {', '.join(output.methodology.datasets)}")
        if output.methodology.evaluation_metrics:
            lines.append(f"**Metrics**: {', '.join(output.methodology.evaluation_metrics)}")
        lines.append("")

        # Results
        lines.append("## Main Results")
        for result in output.main_results:
            lines.append(f"- {result}")
        lines.append("")

        # Limitations
        lines.append("## Limitations")
        for limitation in output.limitations:
            lines.append(f"- {limitation}")
        lines.append("")

        # Relevance
        lines.append("## Relevance to Our Research")
        lines.append(output.relevance_to_research)
        lines.append("")

        # Quality
        lines.append("## Quality Assessment")
        lines.append(output.quality_assessment)
        lines.append("")

        # Key citations
        if output.key_citations:
            lines.append("## Key Citations to Follow Up")
            for citation in output.key_citations:
                lines.append(f"- {citation}")

        return "\n".join(lines)


class PDFSummaryProcessor:
    """Processor that uses PDF tools and LLM to generate summaries.

    This class bridges the PDF parsing tools with the LLM to create
    structured summaries that can be used in literature review.
    """

    SUMMARY_PROMPT = """You are an expert academic researcher analyzing a research paper.
Given the following paper content, extract and summarize the key information.

Paper Content:
{content}

Please analyze this paper and provide a detailed JSON response with the following structure:
{{
    "title": "paper title",
    "abstract_summary": "2-3 sentence summary of abstract",
    "problem_statement": "the problem this paper addresses",
    "key_contributions": [
        {{"contribution": "description", "type": "theoretical/methodological/empirical/practical", "significance": "why important"}}
    ],
    "methodology": {{
        "approach": "overall approach",
        "techniques": ["technique1", "technique2"],
        "datasets": ["dataset1"],
        "evaluation_metrics": ["metric1"]
    }},
    "main_results": ["finding1", "finding2"],
    "limitations": ["limitation1", "limitation2"],
    "future_work": ["future1"],
    "relevance_to_research": "how this relates to research topic: {research_topic}",
    "quality_assessment": "assessment of paper quality"
}}
"""

    def __init__(self, model: Optional[str] = None):
        """Initialize processor.

        Args:
            model: Gemini model to use (defaults to settings.gemini_model).
        """
        kwargs = {}
        if model is not None:
            kwargs["model"] = model
        self.llm = GeminiLLM(**kwargs)
        self.pdf_processor = PDFProcessor()
        self.pdf_scanner = LocalPDFScanner()

        logger.info("PDFSummaryProcessor initialized", model=model)

    async def process_pdf(
        self,
        pdf_path: Path,
        research_topic: str = "",
    ) -> PDFSummaryOutput:
        """Process a PDF file and generate structured summary.

        Args:
            pdf_path: Path to PDF file.
            research_topic: Research topic for relevance evaluation.

        Returns:
            Structured summary output.
        """
        logger.info("Processing PDF", path=str(pdf_path))

        # Parse PDF
        parsed = self.pdf_processor.parse_pdf(pdf_path)

        if "Error" in parsed.full_text:
            logger.error("Failed to parse PDF", path=str(pdf_path))
            return PDFSummaryOutput(
                title=pdf_path.name,
                authors=[],
                abstract_summary=f"Failed to parse PDF: {parsed.full_text}",
                problem_statement="N/A",
                key_contributions=[],
                methodology=MethodologySummary(
                    approach="N/A",
                    techniques=[],
                ),
                main_results=[],
                limitations=["Failed to parse PDF"],
                relevance_to_research="Unable to evaluate",
                quality_assessment="Unable to assess",
            )

        # Generate summary using LLM
        return await self._generate_summary(parsed, research_topic)

    async def process_pdf_url(
        self,
        pdf_url: str,
        research_topic: str = "",
    ) -> PDFSummaryOutput:
        """Download and process PDF from URL.

        Args:
            pdf_url: URL to PDF.
            research_topic: Research topic for relevance evaluation.

        Returns:
            Structured summary output.
        """
        logger.info("Downloading PDF", url=pdf_url)

        # Download PDF
        pdf_path = await self.pdf_processor.download_pdf(pdf_url)

        if not pdf_path:
            return PDFSummaryOutput(
                title="Download Failed",
                authors=[],
                abstract_summary=f"Failed to download PDF from {pdf_url}",
                problem_statement="N/A",
                key_contributions=[],
                methodology=MethodologySummary(
                    approach="N/A",
                    techniques=[],
                ),
                main_results=[],
                limitations=["Failed to download PDF"],
                relevance_to_research="Unable to evaluate",
                quality_assessment="Unable to assess",
            )

        return await self.process_pdf(pdf_path, research_topic)

    async def process_folder(
        self,
        folder_path: Path,
        research_topic: str = "",
        limit: int = 10,
    ) -> list[PDFSummaryOutput]:
        """Process all PDFs in a folder.

        Args:
            folder_path: Path to folder containing PDFs.
            research_topic: Research topic for relevance evaluation.
            limit: Maximum number of PDFs to process.

        Returns:
            List of structured summaries.
        """
        pdf_files = self.pdf_scanner.scan_folder(folder_path)
        logger.info("Processing folder", path=str(folder_path), pdf_count=len(pdf_files))

        summaries = []
        for i, pdf_path in enumerate(pdf_files[:limit]):
            try:
                summary = await self.process_pdf(pdf_path, research_topic)
                summaries.append(summary)
                logger.info(f"Processed {i+1}/{min(len(pdf_files), limit)}", title=summary.title[:50])
            except Exception as e:
                logger.error("Failed to process PDF", path=str(pdf_path), error=str(e))

        return summaries

    async def _generate_summary(
        self,
        parsed: ParsedPDF,
        research_topic: str,
    ) -> PDFSummaryOutput:
        """Generate summary using LLM.

        Args:
            parsed: Parsed PDF content.
            research_topic: Research topic for context.

        Returns:
            Structured summary.
        """
        # Prepare content
        content = f"Title: {parsed.title}\n\n"
        content += f"Authors: {', '.join(parsed.authors)}\n\n"
        content += f"Abstract: {parsed.abstract}\n\n"

        for section in parsed.sections[:6]:
            content += f"\n## {section.title}\n{section.content[:2500]}\n"

        if len(content) > 20000:
            content = content[:20000] + "\n\n[Content truncated...]"

        prompt = self.SUMMARY_PROMPT.format(
            content=content,
            research_topic=research_topic or "general academic research",
        )

        try:
            import json
            response = await self.llm.generate(prompt, max_tokens=3000)

            # Try to parse JSON response
            try:
                # Find JSON in response
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    data = json.loads(json_str)
                    return self._parse_json_response(data, parsed)
            except json.JSONDecodeError:
                pass

            # Fallback: return basic summary
            return PDFSummaryOutput(
                title=parsed.title or "Untitled",
                authors=parsed.authors,
                abstract_summary=parsed.abstract[:500] if parsed.abstract else response[:500],
                problem_statement="See abstract summary",
                key_contributions=[],
                methodology=MethodologySummary(
                    approach="See paper content",
                    techniques=[],
                ),
                main_results=[],
                limitations=[],
                relevance_to_research="Unable to extract structured data",
                quality_assessment="Manual review recommended",
            )

        except Exception as e:
            logger.error("LLM summary failed", error=str(e))
            return PDFSummaryOutput(
                title=parsed.title or "Untitled",
                authors=parsed.authors,
                abstract_summary=f"Error generating summary: {str(e)}",
                problem_statement="N/A",
                key_contributions=[],
                methodology=MethodologySummary(
                    approach="N/A",
                    techniques=[],
                ),
                main_results=[],
                limitations=[],
                relevance_to_research="Error during processing",
                quality_assessment="Unable to assess",
            )

    def _parse_json_response(
        self,
        data: dict,
        parsed: ParsedPDF,
    ) -> PDFSummaryOutput:
        """Parse JSON response into output model.

        Args:
            data: Parsed JSON data.
            parsed: Original parsed PDF.

        Returns:
            Structured summary output.
        """
        # Parse contributions
        contributions = []
        for c in data.get("key_contributions", []):
            if isinstance(c, dict):
                contributions.append(KeyContribution(
                    contribution=c.get("contribution", ""),
                    type=c.get("type", "empirical"),
                    significance=c.get("significance", ""),
                ))

        # Parse methodology
        method_data = data.get("methodology", {})
        methodology = MethodologySummary(
            approach=method_data.get("approach", "Not specified"),
            techniques=method_data.get("techniques", []),
            datasets=method_data.get("datasets", []),
            evaluation_metrics=method_data.get("evaluation_metrics", []),
        )

        return PDFSummaryOutput(
            title=data.get("title") or parsed.title or "Untitled",
            authors=parsed.authors,
            year=parsed.metadata.get("year"),
            venue=parsed.metadata.get("venue"),
            abstract_summary=data.get("abstract_summary", ""),
            problem_statement=data.get("problem_statement", ""),
            key_contributions=contributions,
            methodology=methodology,
            main_results=data.get("main_results", []),
            limitations=data.get("limitations", []),
            future_work=data.get("future_work", []),
            relevance_to_research=data.get("relevance_to_research", ""),
            quality_assessment=data.get("quality_assessment", ""),
            key_citations=data.get("key_citations", []),
        )


class FastPDFSummarizer:
    """Fast PDF summarizer using Gemini 2.0 Flash.

    This class provides a simpler, faster approach to PDF summarization:
    1. Extract full text from PDF using PyMuPDF
    2. Clean and normalize the text
    3. Send to Gemini 2.0 Flash for quick summarization

    The output is a structured markdown summary without complex JSON parsing.
    """

    SUMMARY_PROMPT = """당신은 30년 경력의 베테랑 학술 번역가이자 연구자입니다. 영어 학술 논문을 한국어로 번역하는 최고의 전문가로서, 학술적 정확성을 유지하면서도 자연스럽고 읽기 쉬운 한국어로 번역하는 것이 당신의 전문 분야입니다.

## 논문 텍스트:
{text}

## 연구 맥락:
{research_topic}

---

아래 형식에 맞춰 논문 요약을 작성해주세요. **제목(Title)은 반드시 영어 원문 그대로 유지**하고, 나머지 모든 내용은 자연스럽고 유창한 한국어로 작성해주세요.

## 메타데이터 (Metadata)

### 1. 제목 (Title)
논문 제목을 영어 원문 그대로 추출합니다. 번역하지 마세요.

### 2. 저자 (Authors)
저자 정보를 기재합니다. (예: Kim, J., Lee, S., Park, H.)

### 3. 출판 연도 (Year)
논문의 출판 연도를 추출합니다. (예: 2024)

### 4. 저널/컨퍼런스 (Venue)
게재된 저널 또는 컨퍼런스명을 영어 원문 그대로 기재합니다. (예: IEEE Transactions on Information Forensics and Security, ACM CCS 2024)

### 5. DOI
DOI가 있다면 추출합니다. 없으면 "N/A"로 표기합니다. (예: 10.1109/TIFS.2024.1234567)

---

## 내용 요약 (Content Summary)

### 6. 요약 (Summary)
논문의 핵심 내용을 3-4문장으로 자연스러운 한국어로 요약합니다.

### 7. 연구 문제 (Research Problem)
이 논문이 다루는 문제가 무엇인지 한국어로 설명합니다.

### 8. 방법론 (Methodology)
어떤 연구 방법이나 접근법을 사용했는지 한국어로 설명합니다.

### 9. 주요 결과 (Key Results)
핵심 연구 결과를 한국어로 정리합니다.

### 10. 기여점 (Contributions)
이 논문의 학술적 기여를 한국어로 설명합니다.

### 11. 한계점 (Limitations)
논문의 한계점을 한국어로 분석합니다.

---

## 평가 (Evaluation)

### 12. 연구 관련성 (Relevance to Our Research)
이 논문이 "{research_topic}"과 어떻게 관련되는지 한국어로 설명합니다.

**중요**: 관련성을 억지로 만들지 마세요. 논문이 우리 연구와 직접적인 관련이 없다면 솔직하게 "이 논문은 우리 연구와 직접적인 관련성이 낮습니다" 또는 "관련성이 제한적입니다"라고 명시하세요. 간접적이거나 약한 연결은 "간접적으로 관련될 수 있으나..." 정도로 표현하세요.

### 13. 품질 평가 (Quality Assessment)
논문의 품질과 학술적 엄밀성에 대해 한국어로 간략히 평가합니다.

---

**중요**: 제목(Title), 저널/컨퍼런스(Venue), DOI는 영어 원문을 유지하고, 그 외 모든 섹션은 30년 경력 번역가의 시각으로 학술적이면서도 자연스러운 한국어로 작성해주세요. 직역투나 어색한 표현을 피하고, 한국 학술 문서에서 일반적으로 사용되는 표현을 사용하세요.
"""

    def __init__(self):
        """Initialize fast summarizer with Gemini 2.0 Flash."""
        self.llm = GeminiLLM(model=FAST_SUMMARY_MODEL)
        self.pdf_processor = PDFProcessor()
        logger.info("FastPDFSummarizer initialized", model=FAST_SUMMARY_MODEL)

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted PDF text.

        Args:
            text: Raw text from PDF.

        Returns:
            Cleaned text.
        """
        import re

        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Remove page numbers and headers/footers (common patterns)
        text = re.sub(r'\n\d+\n', '\n', text)  # Standalone page numbers
        text = re.sub(r'Page \d+ of \d+', '', text)

        # Remove URLs that got broken across lines
        text = re.sub(r'hps?://', 'https://', text)  # Fix broken https

        # Clean up common PDF artifacts
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)  # Control characters

        # Trim to reasonable length for LLM (about 30k chars max)
        if len(text) > 30000:
            # Try to keep abstract and key sections
            text = text[:30000]
            logger.info("Text truncated to 30k characters")

        return text.strip()

    def _extract_metadata_from_response(self, response: str) -> dict:
        """Extract structured metadata from LLM response.

        Args:
            response: LLM response text.

        Returns:
            Dictionary with extracted metadata.
        """
        import re

        metadata = {
            "title": "",
            "authors": [],
            "summary": "",
        }

        # Extract title
        title_match = re.search(r'### 1\. 제목.*?\n([^\n#]+)', response, re.DOTALL)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        # Extract authors
        authors_match = re.search(r'### 2\. 저자.*?\n([^\n#]+)', response, re.DOTALL)
        if authors_match:
            authors_text = authors_match.group(1).strip()
            # Try to parse author names
            if ',' in authors_text:
                metadata["authors"] = [a.strip() for a in authors_text.split(',') if a.strip()]
            elif 'et al' in authors_text.lower():
                metadata["authors"] = [authors_text.strip()]

        # Extract summary
        summary_match = re.search(r'### 3\. 요약.*?\n(.*?)(?=### \d|$)', response, re.DOTALL)
        if summary_match:
            metadata["summary"] = summary_match.group(1).strip()

        return metadata

    async def summarize_pdf(
        self,
        pdf_path: Path,
        research_topic: str = "",
        research_definition: str = "",
    ) -> tuple[str, dict]:
        """Summarize a PDF file quickly.

        Args:
            pdf_path: Path to PDF file.
            research_topic: Research topic for context.
            research_definition: Full Research Definition content for relevance analysis.

        Returns:
            Tuple of (markdown_summary, metadata_dict).
        """
        logger.info("Fast summarizing PDF", path=str(pdf_path))

        # Parse PDF to extract text
        parsed = self.pdf_processor.parse_pdf(pdf_path)

        if "Error" in parsed.full_text:
            error_msg = f"# PDF 처리 실패\n\n오류: {parsed.full_text}"
            return error_msg, {"title": pdf_path.name, "authors": [], "summary": "PDF 파싱 실패"}

        # Clean the extracted text
        clean_text = self._clean_text(parsed.full_text)

        if not clean_text or len(clean_text) < 100:
            error_msg = "# PDF 처리 실패\n\n텍스트를 추출할 수 없습니다."
            return error_msg, {"title": pdf_path.name, "authors": [], "summary": "텍스트 추출 실패"}

        # Use RD content if available for better relevance analysis
        if research_definition and len(research_definition.strip()) > 100:
            rd_context = research_definition[:5000]
        else:
            rd_context = research_topic or "학술 연구"

        # Generate prompt
        prompt = self.SUMMARY_PROMPT.format(
            text=clean_text,
            research_topic=rd_context,
        )

        try:
            # Call Gemini 2.0 Flash for fast summarization
            response = await self.llm.generate(prompt, max_tokens=4000)

            # Extract metadata from response
            metadata = self._extract_metadata_from_response(response)

            # Use parsed PDF metadata as fallback
            if not metadata["title"]:
                metadata["title"] = parsed.title or pdf_path.stem
            if not metadata["authors"] and parsed.authors:
                metadata["authors"] = parsed.authors

            # Build final markdown
            from datetime import datetime

            final_md = f"""# {metadata['title']}

## 메타데이터
- **저자**: {', '.join(metadata['authors']) if metadata['authors'] else 'Unknown'}
- **페이지 수**: {parsed.page_count}
- **처리 모델**: {FAST_SUMMARY_MODEL}

---

{response}

---
*FastPDFSummarizer로 처리됨 ({datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC)*
"""

            logger.info("PDF fast summarization complete",
                       title=metadata['title'][:50] if metadata['title'] else "Unknown")

            return final_md, metadata

        except Exception as e:
            logger.error("Fast summarization failed", error=str(e))
            error_md = f"# 요약 생성 실패\n\n오류: {str(e)}\n\n## 추출된 텍스트 (처음 2000자)\n\n{clean_text[:2000]}..."
            return error_md, {"title": pdf_path.name, "authors": parsed.authors, "summary": f"오류: {str(e)}"}

    async def summarize_text(
        self,
        text: str,
        title: str = "",
        research_topic: str = "",
        research_definition: str = "",
    ) -> str:
        """Summarize raw text (for papers without PDF).

        Args:
            text: Paper text (abstract, etc).
            title: Paper title.
            research_topic: Research topic for context.
            research_definition: Full Research Definition content for relevance analysis.

        Returns:
            Markdown summary.
        """
        # Use RD content if available, otherwise fall back to topic
        if research_definition and len(research_definition.strip()) > 100:
            research_context = f"""## 우리 연구의 Research Definition:
{research_definition[:5000]}"""
        else:
            research_context = f"연구 주제: {research_topic or '학술 연구'}"

        prompt = f"""당신은 30년 경력의 베테랑 학술 연구자이자 번역가입니다. 아래 논문 정보를 바탕으로 심층 분석을 제공해주세요.

## 논문 제목:
{title}

## 논문 텍스트:
{text[:15000]}

{research_context}

---

아래 형식에 맞춰 **모든 내용을 한국어로** 작성해주세요. 학술적이면서도 자연스럽고 읽기 쉬운 문체를 사용하세요.

### 1. 요약 (Summary)
이 논문의 핵심 내용을 3-4문장으로 요약합니다.

### 2. 연구 문제 (Research Problem)
이 논문이 해결하고자 하는 문제가 무엇인지 설명합니다.

### 3. 방법론 (Methodology)
어떤 연구 방법이나 접근법을 사용했는지 설명합니다. (텍스트에서 파악 가능한 경우)

### 4. 주요 결과 (Key Results)
논문의 핵심 연구 결과를 정리합니다. (텍스트에서 파악 가능한 경우)

### 5. 연구 관련성 (Relevance to Our Research)
위에 제시된 우리 연구의 Research Definition을 참고하여, 이 논문이 우리 연구와 어떻게 관련되는지 구체적으로 분석합니다. 우리 연구의 목표, 연구 질문, 방법론에 비추어 이 논문이 제공할 수 있는 인사이트와 참고점을 설명하세요.

**중요 - 정직한 평가**: 관련성을 억지로 만들지 마세요. 논문이 우리 연구와 직접적인 관련이 없다면 솔직하게 "이 논문은 우리 연구와 직접적인 관련성이 낮습니다" 또는 "관련성이 제한적입니다"라고 명시하세요. 관련성의 정도를 다음과 같이 표현하세요:
- **직접적 관련성**: 연구 주제, 방법론, 목표가 직접 관련됨
- **간접적 관련성**: 일부 방법론이나 개념이 참고할 만함
- **제한적 관련성**: 매우 제한적인 연결만 있음
- **관련성 없음**: 연구 분야나 접근법이 다름

---

**중요**: 모든 내용은 반드시 한국어로 작성하세요. 직역투가 아닌 자연스러운 한국어 학술 문체를 사용하세요.
"""

        try:
            response = await self.llm.generate(prompt, max_tokens=3000)
            return response
        except Exception as e:
            logger.error("Text summarization failed", error=str(e))
            return f"요약 생성 실패: {str(e)}"
