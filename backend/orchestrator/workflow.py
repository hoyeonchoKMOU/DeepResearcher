"""LangGraph workflow for research orchestration."""

from typing import Literal

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents.experiment_design import ExperimentDesignAgent
from backend.agents.imrad_structure import IMRADStructureAgent
from backend.agents.journal_writing import JournalWritingAgent
from backend.agents.literature_evaluation import LiteratureEvaluationAgent
from backend.agents.literature_search import LiteratureSearchAgent
from backend.agents.pdf_summary import PDFSummaryAgent
from backend.agents.research_discussion import ResearchDiscussionAgent
from backend.llm.gemini import GeminiLLM
from backend.orchestrator.state import ResearchState, WorkflowConfig

logger = structlog.get_logger(__name__)


class ResearchWorkflow:
    """Orchestrates the research workflow using LangGraph."""

    def __init__(
        self,
        llm: GeminiLLM | None = None,
        config: WorkflowConfig | None = None,
    ):
        """Initialize the research workflow.

        Args:
            llm: LLM instance to use for agents.
            config: Workflow configuration.
        """
        self.llm = llm or GeminiLLM()
        self.config = config or WorkflowConfig()

        # Initialize agents
        self.agents = {
            "research_discussion": ResearchDiscussionAgent(llm=self.llm),
            "literature_search": LiteratureSearchAgent(llm=self.llm),
            "pdf_summary": PDFSummaryAgent(llm=self.llm),
            "literature_evaluation": LiteratureEvaluationAgent(llm=self.llm),
            "experiment_design": ExperimentDesignAgent(llm=self.llm),
            "imrad_structure": IMRADStructureAgent(llm=self.llm),
            "journal_writing": JournalWritingAgent(llm=self.llm),
        }

        # Build workflow graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(ResearchState)

        # Add nodes
        workflow.add_node("research_discussion", self._research_discussion_node)
        workflow.add_node("literature_search", self._literature_search_node)
        workflow.add_node("pdf_summary", self._pdf_summary_node)
        workflow.add_node("literature_evaluation", self._literature_evaluation_node)
        workflow.add_node("experiment_design", self._experiment_design_node)
        workflow.add_node("imrad_structure", self._imrad_structure_node)
        workflow.add_node("journal_writing", self._journal_writing_node)
        workflow.add_node("human_review", self._human_review_node)

        # Define edges
        workflow.add_edge(START, "research_discussion")

        # After research discussion
        workflow.add_conditional_edges(
            "research_discussion",
            self._should_proceed_to_search,
            {
                "proceed": "literature_search",
                "refine": "research_discussion",
                "end": END,
            },
        )

        # Literature search -> PDF summary
        workflow.add_edge("literature_search", "pdf_summary")

        # PDF summary -> Literature evaluation
        workflow.add_edge("pdf_summary", "literature_evaluation")

        # After literature evaluation
        workflow.add_conditional_edges(
            "literature_evaluation",
            self._needs_more_literature,
            {
                "more_search": "literature_search",
                "proceed": "experiment_design",
            },
        )

        # Experiment design -> IMRAD structure
        workflow.add_edge("experiment_design", "imrad_structure")

        # IMRAD -> Journal writing
        workflow.add_edge("imrad_structure", "journal_writing")

        # Journal writing -> Human review
        workflow.add_edge("journal_writing", "human_review")

        # After human review
        workflow.add_conditional_edges(
            "human_review",
            self._review_decision,
            {
                "approved": END,
                "revision": "journal_writing",
                "major_revision": "experiment_design",
            },
        )

        return workflow

    # === Node Functions ===

    async def _research_discussion_node(self, state: ResearchState) -> dict:
        """Execute research discussion agent."""
        logger.info("Executing research discussion")

        agent = self.agents["research_discussion"]
        result = await agent.run({
            "research_topic": state.research_topic,
            "previous_feedback": state.human_feedback,
        })

        return {
            "refined_topic": result.refined_topic,
            "research_questions": result.research_questions,
            "novelty_assessment": result.novelty_assessment.model_dump(),
            "research_scope": result.research_scope,
            "potential_contributions": result.potential_contributions,
            "search_keywords": result.suggested_keywords,
            "current_phase": "research_definition",
            "messages": state.messages + [{
                "agent": "research_discussion",
                "content": result.model_dump(),
            }],
        }

    async def _literature_search_node(self, state: ResearchState) -> dict:
        """Execute literature search agent."""
        logger.info("Executing literature search")

        agent = self.agents["literature_search"]
        result = await agent.search_and_analyze(
            keywords=state.search_keywords,
            research_questions=state.research_questions,
            year_start=self.config.year_start,
            year_end=self.config.year_end,
            limit=self.config.max_papers,
        )

        return {
            "found_papers": [p.model_dump() for p in result.papers],
            "search_keywords": result.refined_keywords,
            "current_phase": "literature_search",
            "messages": state.messages + [{
                "agent": "literature_search",
                "content": {
                    "strategy": result.search_strategy,
                    "total_results": result.total_results,
                    "papers_count": len(result.papers),
                },
            }],
        }

    async def _pdf_summary_node(self, state: ResearchState) -> dict:
        """Execute PDF summary agent for found papers."""
        logger.info("Executing PDF summary")

        agent = self.agents["pdf_summary"]
        summaries = []

        # Process top papers (limit to avoid rate limits)
        for paper in state.found_papers[:10]:
            if paper.get("abstract"):
                result = await agent.run({
                    "title": paper.get("title"),
                    "abstract": paper.get("abstract"),
                    "research_questions": state.research_questions,
                })
                summaries.append({
                    "paper_id": paper.get("paper_id"),
                    "title": paper.get("title"),
                    "summary": result.model_dump(),
                })

        return {
            "paper_summaries": summaries,
            "current_phase": "pdf_summary",
            "messages": state.messages + [{
                "agent": "pdf_summary",
                "content": f"Summarized {len(summaries)} papers",
            }],
        }

    async def _literature_evaluation_node(self, state: ResearchState) -> dict:
        """Execute literature evaluation agent."""
        logger.info("Executing literature evaluation")

        agent = self.agents["literature_evaluation"]
        result = await agent.run({
            "research_questions": state.research_questions,
            "paper_summaries": state.paper_summaries,
            "research_topic": state.refined_topic,
        })

        return {
            "literature_evaluation": {
                "overall_assessment": result.overall_assessment,
                "coverage_score": result.coverage_score,
                "needs_more": result.needs_more_literature,
            },
            "research_gaps": [g.model_dump() for g in result.research_gaps],
            "research_trends": [t.model_dump() for t in result.research_trends],
            "current_phase": "literature_evaluation",
            "messages": state.messages + [{
                "agent": "literature_evaluation",
                "content": {
                    "coverage": result.coverage_score,
                    "gaps_found": len(result.research_gaps),
                },
            }],
        }

    async def _experiment_design_node(self, state: ResearchState) -> dict:
        """Execute experiment design agent."""
        logger.info("Executing experiment design")

        agent = self.agents["experiment_design"]
        result = await agent.run({
            "research_questions": state.research_questions,
            "research_topic": state.refined_topic,
            "literature_findings": str(state.literature_evaluation),
            "existing_methods": str(state.research_trends),
        })

        return {
            "experiment_design": result.model_dump(),
            "variables": {
                "independent": [v.model_dump() for v in result.independent_variables],
                "dependent": [v.model_dump() for v in result.dependent_variables],
                "control": [v.model_dump() for v in result.control_variables],
            },
            "hypotheses": [h.model_dump() for h in result.hypotheses],
            "methodology": {
                "design_type": result.design_type,
                "baselines": result.baselines,
                "metrics": result.evaluation_metrics,
            },
            "current_phase": "experiment_design",
            "messages": state.messages + [{
                "agent": "experiment_design",
                "content": f"Designed {result.design_type} experiment",
            }],
        }

    async def _imrad_structure_node(self, state: ResearchState) -> dict:
        """Execute IMRAD structure agent."""
        logger.info("Executing IMRAD structure")

        agent = self.agents["imrad_structure"]
        result = await agent.run({
            "research_topic": state.refined_topic,
            "research_questions": state.research_questions,
            "methodology": str(state.methodology),
            "contributions": state.potential_contributions,
            "literature_context": str(state.literature_evaluation),
            "target_venue": state.target_journal,
        })

        return {
            "imrad_structure": result.model_dump(),
            "draft_sections": {
                "abstract": result.abstract.model_dump(),
                "introduction": result.introduction.model_dump(),
                "methods": result.methods.model_dump(),
                "results": result.results.model_dump(),
                "discussion": result.discussion.model_dump(),
                "conclusion": result.conclusion,
            },
            "current_phase": "imrad_structure",
            "messages": state.messages + [{
                "agent": "imrad_structure",
                "content": "Paper structure created",
            }],
        }

    async def _journal_writing_node(self, state: ResearchState) -> dict:
        """Execute journal writing agent."""
        logger.info("Executing journal writing")

        agent = self.agents["journal_writing"]
        result = await agent.run({
            "target_journal": state.target_journal or "Generic CS Journal",
            "paper_structure": str(state.imrad_structure),
            "draft_content": str(state.draft_sections),
        })

        # Format the final paper
        final_paper = agent.format_full_paper(result)
        cover_letter = agent.format_cover_letter(result)

        return {
            "journal_guidelines": result.guidelines_summary.model_dump(),
            "final_paper": final_paper,
            "cover_letter": cover_letter,
            "current_phase": "journal_writing",
            "messages": state.messages + [{
                "agent": "journal_writing",
                "content": {
                    "word_count": result.total_word_count,
                    "warnings": result.warnings,
                },
            }],
        }

    async def _human_review_node(self, state: ResearchState) -> dict:
        """Handle human review (placeholder for async review)."""
        logger.info("Awaiting human review")

        # In a real implementation, this would pause and wait for human input
        # For now, we'll mark it as pending review
        return {
            "current_phase": "human_review",
            "messages": state.messages + [{
                "agent": "system",
                "content": "Paper ready for human review",
            }],
        }

    # === Conditional Edge Functions ===

    def _should_proceed_to_search(
        self, state: ResearchState
    ) -> Literal["proceed", "refine", "end"]:
        """Decide whether to proceed to literature search."""
        novelty = state.novelty_assessment
        if not novelty:
            return "refine"

        score = novelty.get("score", 0)
        needs_refinement = novelty.get("needs_refinement", True)

        if score >= 0.6 and not needs_refinement:
            logger.info("Proceeding to literature search", novelty_score=score)
            return "proceed"
        elif score < 0.3:
            logger.info("Research topic needs significant refinement", novelty_score=score)
            return "refine"
        else:
            logger.info("Research topic needs some refinement", novelty_score=score)
            return "refine"

    def _needs_more_literature(
        self, state: ResearchState
    ) -> Literal["more_search", "proceed"]:
        """Decide if more literature search is needed."""
        evaluation = state.literature_evaluation
        coverage = evaluation.get("coverage_score", 0)
        needs_more = evaluation.get("needs_more", False)

        if coverage < 0.7 or needs_more:
            logger.info("More literature needed", coverage=coverage)
            return "more_search"

        logger.info("Literature coverage sufficient", coverage=coverage)
        return "proceed"

    def _review_decision(
        self, state: ResearchState
    ) -> Literal["approved", "revision", "major_revision"]:
        """Process human review decision."""
        # Check latest human feedback
        feedback = state.human_feedback
        if not feedback:
            return "approved"  # No feedback = auto-approve for demo

        latest = feedback[-1] if feedback else {}
        decision = latest.get("decision", "approved")

        return decision

    # === Public Methods ===

    def compile(self, checkpointer: MemorySaver | None = None):
        """Compile the workflow graph.

        Args:
            checkpointer: Memory saver for state persistence.

        Returns:
            Compiled workflow.
        """
        checkpointer = checkpointer or MemorySaver()
        return self.graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        research_topic: str,
        target_journal: str = "",
        thread_id: str = "default",
    ) -> ResearchState:
        """Run the complete research workflow.

        Args:
            research_topic: Initial research topic.
            target_journal: Target journal for submission.
            thread_id: Thread ID for state persistence.

        Returns:
            Final workflow state.
        """
        compiled = self.compile()

        initial_state = ResearchState(
            research_topic=research_topic,
            target_journal=target_journal,
        )

        config = {"configurable": {"thread_id": thread_id}}

        logger.info("Starting research workflow", topic=research_topic[:50])

        final_state = await compiled.ainvoke(
            initial_state.model_dump(),
            config=config,
        )

        logger.info("Research workflow completed")

        return ResearchState(**final_state)


def create_research_workflow(
    llm: GeminiLLM | None = None,
    config: WorkflowConfig | None = None,
) -> ResearchWorkflow:
    """Factory function to create a research workflow.

    Args:
        llm: LLM instance.
        config: Workflow configuration.

    Returns:
        Configured ResearchWorkflow instance.
    """
    return ResearchWorkflow(llm=llm, config=config)
