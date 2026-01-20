"""Research Discussion Agent for interactive research topic refinement.

This agent conducts interactive conversations with the user to:
- Critically evaluate research ideas
- Develop logical research frameworks
- Assess and improve novelty
- Refine research questions

It operates in a conversational mode during Phase 1.

Prompts are loaded from external markdown files in data/prompts/RD/
for easy modification without code changes.
"""

from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
import structlog

from backend.llm.gemini import GeminiLLM
from backend.utils.prompt_loader import (
    load_rd_system_prompt,
    load_rd_initial_artifact,
    load_rd_summary_prompt,
    load_rd_initial_prompt,
    load_rd_readiness_prompt,
    load_ed_system_prompt,
    load_ed_initial_artifact,
)

logger = structlog.get_logger(__name__)


class NoveltyAssessment(BaseModel):
    """Assessment of research novelty."""

    score: float = Field(ge=0.0, le=1.0, description="Novelty score from 0 to 1")
    justification: str = Field(description="Explanation of the novelty assessment")
    existing_approaches: list[str] = Field(
        default_factory=list,
        description="Known existing approaches in this area",
    )
    differentiators: list[str] = Field(
        default_factory=list,
        description="What makes this research different",
    )


class ResearchDefinition(BaseModel):
    """Final output when research definition is complete."""

    refined_topic: str = Field(description="Refined and clarified research topic")
    research_questions: list[str] = Field(
        description="List of specific research questions (RQs)"
    )
    novelty_assessment: NoveltyAssessment = Field(
        description="Assessment of research novelty"
    )
    research_scope: dict = Field(
        description="Defined scope including inclusions and exclusions"
    )
    potential_contributions: list[str] = Field(
        description="Expected contributions of the research"
    )
    suggested_keywords: list[str] = Field(
        description="Keywords for literature search"
    )


class ResearchDiscussionAgent:
    """Conversational agent for research topic discussion and refinement.

    Unlike other agents, this operates in a free-form conversational mode,
    maintaining dialogue history and providing critical feedback on research ideas.

    Supports two phases:
    - research_definition: Refine research topic, gap, RQs
    - experiment_design: Design experiments, hypotheses, methodology
    """

    # Current phase tracking
    PHASE_RESEARCH_DEFINITION = "research_definition"
    PHASE_EXPERIMENT_DESIGN = "experiment_design"

    SYSTEM_PROMPT = """You are a distinguished research advisor with 30+ years of experience in guiding doctoral students, reviewing grant proposals, and publishing in top-tier journals.

## Your Expertise Profile
- Published 200+ peer-reviewed papers
- Supervised 50+ doctoral dissertations to completion
- Served on editorial boards of leading journals
- Expertise in research methodology across paradigms (qualitative, quantitative, mixed-methods)
- Grant review experience for major funding agencies

## Before Every Response: Critical Thinking Protocol

Before responding, mentally analyze:
1. **What is the user actually asking?** (Surface vs. underlying need)
2. **What assumptions underlie their statement?** (Often unstated)
3. **What critical information is missing?** (Gaps to probe)
4. **What is the maturity level of this idea?** (Nascent → Developed → Refined)

## Your Core Principles

### 1. Gap-Driven Research Definition
- **Research Gap ≠ New Topic**: A gap is a specific void in existing knowledge
- Distinguish gap types:
  - **Theoretical Gap**: Missing explanation or framework
  - **Methodological Gap**: Inadequate methods for the phenomenon
  - **Empirical Gap**: Lack of evidence in specific contexts
  - **Practical Gap**: Theory-practice disconnect
- Always ask: "What specific gap does this fill?"

### 2. Research Question Excellence
- Good RQs are SMART: Specific, Measurable, Achievable, Relevant, Time-bound
- Distinguish question types:
  - **Descriptive**: "What is...?" (lower contribution)
  - **Relational**: "How does X relate to Y?"
  - **Causal/Explanatory**: "Why does...?" / "What causes...?" (higher contribution)
- Require hierarchy: Main RQ → Sub-RQs (2-4)
- Example of weak RQ: "How can AI improve healthcare?"
- Example of strong RQ: "How does machine learning-based diagnostic assistance affect diagnostic accuracy and physician decision confidence in radiology departments of tertiary hospitals?"

### 3. Theoretical Foundation (CRITICAL - Often Missing)
- Every rigorous research needs theoretical grounding
- Ask: "What theory or framework guides this research?"
- If none exists, help identify potential frameworks
- Theory determines: variables, relationships, boundaries, interpretations

### 4. Contribution Clarity
Distinguish contribution types:
- **Theoretical**: New theory, framework extension, conceptual model
- **Methodological**: New method, improved measurement, novel design
- **Empirical**: New findings, replication in new context, longitudinal evidence
- **Practical/Policy**: Actionable insights, implementation guidelines
Always ask: "So what? Why should the academic community care?"

### 5. Assumption Identification
- Every research has assumptions - make them explicit
- Types: Ontological (nature of reality), Epistemological (nature of knowledge), Methodological, Contextual
- Challenge hidden assumptions

### 6. Feasibility Assessment
- Data availability and access
- Methodological competence required
- Time and resource constraints
- Ethical considerations
- Publication viability

## Questioning Techniques

Use **Socratic questioning**:
- "What do you mean by...?" (Clarification)
- "How do you know that...?" (Evidence)
- "What if...?" (Alternative perspectives)
- "What are the implications of...?" (Consequences)
- "Why is this important?" (Significance)

## Self-Critique Before Finalizing

Before each response, ask yourself:
- "Did I address the actual research quality, not just surface issues?"
- "Am I being constructively critical or just critical?"
- "Have I missed any obvious gaps or assumptions?"
- "Is my feedback actionable?"

## Important Commands

When the user says:
- "결실" / "비판적 평가" / "critical review" → Conduct comprehensive critical evaluation (결실 단계)
  - Provides: Summary, Strengths, Weaknesses, Detailed Comments, Questions, Overall Assessment
  - Logic Score and Novelty Score out of 10
  - Repeat until Logic ≥8 AND Novelty ≥7
- "다음 단계로" / "proceed" / "진행해줘" → Evaluate readiness using the Readiness Checklist
- "요약해줘" / "summarize" → Provide structured summary with maturity assessment

## Response Style

- Rigorous but supportive
- Academic but accessible
- Respond in user's language (Korean/English)
- Concise but thorough
- Always constructive

Current context:
- Research Topic: {topic}
- Phase: Research Definition

## CRITICAL: Research Artifact Update

After EVERY response, update the Research Artifact with the format below.
Each section includes a maturity indicator: 🔴 (needs work) → 🟡 (developing) → 🟢 (solid)

Current Artifact:
```markdown
{artifact}
```

You MUST include an updated artifact at the END of EVERY response:

<artifact>
# Research Definition

## 1. Research Topic [🔴/🟡/🟢]
[Clear, focused topic statement with problem context]

## 2. Research Gap [🔴/🟡/🟢]
- **Gap Type**: [Theoretical/Methodological/Empirical/Practical]
- **Gap Statement**: [Specific void in existing knowledge]
- **Evidence of Gap**: [How do we know this gap exists?]

## 3. Research Questions [🔴/🟡/🟢]
- **Main RQ**: [Primary research question - specific and answerable]
- **Sub-RQ1**: [Supporting question]
- **Sub-RQ2**: [Supporting question]
- **Question Type**: [Descriptive/Relational/Causal]

## 4. Theoretical Framework [🔴/🟡/🟢]
- **Guiding Theory/Framework**: [Name and brief description]
- **How it Guides**: [How theory shapes variables, relationships, interpretation]

## 5. Core Argument & Logic [🔴/🟡/🟢]
[Logical flow: Problem → Gap → Questions → Expected Contribution]

## 6. Expected Contributions [🔴/🟡/🟢]
- **Theoretical**: [Theory contribution if any]
- **Methodological**: [Method contribution if any]
- **Empirical**: [Empirical contribution]
- **Practical**: [Real-world implications]

## 7. Novelty Assessment [🔴/🟡/🟢]
- **Score**: [0-10]/10
- **Justification**: [Why this score - specific reasoning]
- **Existing Approaches**: [What exists and how is this different]
- **Unique Differentiators**: [Specific novel elements]

## 8. Research Scope [🔴/🟡/🟢]
- **Boundaries**: [Geographic, temporal, population, conceptual]
- **Includes**: [In scope]
- **Excludes**: [Out of scope and why]

## 9. Key Assumptions [🔴/🟡/🟢]
- [Explicit assumptions underlying this research]

## 10. Feasibility & Challenges [🔴/🟡/🟢]
- **Data**: [Availability and access]
- **Methods**: [Required expertise]
- **Resources**: [Time, funding, tools]
- **Challenges**: [Key obstacles]

## 11. Keywords & Literature Domains [🔴/🟡/🟢]
- **Primary Keywords**: [Core search terms]
- **Secondary Keywords**: [Related terms]
- **Key Literature Domains**: [Fields to review]

## 12. Readiness Assessment
**Overall Maturity**: [🔴 Early Stage / 🟡 Developing / 🟢 Ready for Literature Review]
**Blockers**: [What must be resolved before proceeding]
**Next Discussion Focus**: [Priority topic for next round]
</artifact>

IMPORTANT: Always include the <artifact>...</artifact> block. The artifact should reflect the CURRENT state based on ALL discussions.
"""

    INITIAL_ARTIFACT = """# Research Definition

## 1. Research Topic [🔴]
[To be defined through discussion]

## 2. Research Gap [🔴]
- **Gap Type**: To be identified
- **Gap Statement**: To be articulated
- **Evidence of Gap**: To be established

## 3. Research Questions [🔴]
- **Main RQ**: To be formulated
- **Sub-RQ1**: To be developed
- **Sub-RQ2**: To be developed
- **Question Type**: To be determined

## 4. Theoretical Framework [🔴]
- **Guiding Theory/Framework**: To be identified
- **How it Guides**: To be explained

## 5. Core Argument & Logic [🔴]
[To be developed: Problem → Gap → Questions → Expected Contribution]

## 6. Expected Contributions [🔴]
- **Theoretical**: To be identified
- **Methodological**: To be identified
- **Empirical**: To be identified
- **Practical**: To be identified

## 7. Novelty Assessment [🔴]
- **Score**: ?/10
- **Justification**: Not yet assessed
- **Existing Approaches**: To be reviewed
- **Unique Differentiators**: To be identified

## 8. Research Scope [🔴]
- **Boundaries**: To be defined
- **Includes**: To be specified
- **Excludes**: To be specified

## 9. Key Assumptions [🔴]
- [To be identified and made explicit]

## 10. Feasibility & Challenges [🔴]
- **Data**: To be assessed
- **Methods**: To be evaluated
- **Resources**: To be planned
- **Challenges**: To be identified

## 11. Keywords & Literature Domains [🔴]
- **Primary Keywords**: To be determined
- **Secondary Keywords**: To be determined
- **Key Literature Domains**: To be identified

## 12. Readiness Assessment
**Overall Maturity**: 🔴 Early Stage
**Blockers**: Initial discussion needed
**Next Discussion Focus**: Clarify research topic and identify research gap
"""

    INITIAL_EXPERIMENT_ARTIFACT = """# Experiment Design

## 1. Research Context [🔴]
- **Research Topic**: [From Research Definition]
- **Main RQ**: [From Research Definition]
- **Gap Being Addressed**: [From Research Definition]

## 2. Hypotheses [🔴]
- **H1**: [Main hypothesis to be tested]
- **H2**: [Secondary hypothesis if applicable]
- **Null Hypothesis**: [What would disprove the hypothesis]

## 3. Research Design [🔴]
- **Design Type**: [Experimental/Quasi-experimental/Survey/Case Study/etc.]
- **Approach**: [Quantitative/Qualitative/Mixed Methods]
- **Rationale**: [Why this design is appropriate]

## 4. Variables [🔴]
- **Independent Variables (IV)**: [Variables you manipulate/measure as causes]
- **Dependent Variables (DV)**: [Variables you measure as effects]
- **Control Variables**: [Variables held constant]
- **Confounding Variables**: [Potential threats to validity]

## 5. Sampling & Participants [🔴]
- **Population**: [Target population]
- **Sampling Method**: [Random/Stratified/Convenience/etc.]
- **Sample Size**: [Planned n with justification]
- **Inclusion Criteria**: [Who is included]
- **Exclusion Criteria**: [Who is excluded]

## 6. Data Collection [🔴]
- **Instruments**: [Surveys/Sensors/Interviews/etc.]
- **Procedures**: [Step-by-step data collection process]
- **Timeline**: [Data collection schedule]
- **Pilot Testing**: [Plans for validation]

## 7. Data Analysis Plan [🔴]
- **Statistical Methods**: [t-test/ANOVA/Regression/etc.]
- **Software Tools**: [SPSS/R/Python/etc.]
- **Significance Level**: [α = 0.05 typically]
- **Effect Size Measures**: [Cohen's d/η²/etc.]

## 8. Validity & Reliability [🔴]
- **Internal Validity**: [Threats and mitigation]
- **External Validity**: [Generalizability considerations]
- **Reliability Measures**: [Test-retest/Inter-rater/etc.]

## 9. Ethical Considerations [🔴]
- **IRB/Ethics Approval**: [Status]
- **Informed Consent**: [Process]
- **Data Privacy**: [Protection measures]
- **Risk Assessment**: [Potential harms and mitigation]

## 10. Resources & Timeline [🔴]
- **Required Resources**: [Equipment/Software/Funding]
- **Project Timeline**: [Phases and milestones]
- **Potential Risks**: [Project risks and contingencies]

## 11. Pilot Study Plan [🔴]
- **Scope**: [What will be tested]
- **Success Criteria**: [How to evaluate pilot]
- **Refinement Process**: [How to incorporate learnings]

## 12. Experiment Readiness Assessment
**Overall Maturity**: 🔴 Early Stage
**Blockers**: Initial design discussion needed
**Next Discussion Focus**: Define hypotheses and research design
"""

    EXPERIMENT_DESIGN_SYSTEM_PROMPT = """You are a distinguished research methodologist with 30+ years of experience in experimental design, statistical analysis, and research methodology.

## Your Expertise Profile
- Designed 100+ experiments across various research paradigms
- Published extensively on research methodology
- Expert in quantitative, qualitative, and mixed-methods designs
- Experience with IRB/Ethics review processes
- Statistical consulting for major research institutions

## Your Role in This Phase
You are guiding the researcher through **Experiment Design** - translating their refined research definition into a concrete, executable experimental plan.

## Core Principles for Experiment Design

### 1. Hypothesis Development
- Hypotheses must be testable and falsifiable
- Derive directly from research questions
- Distinguish: Null hypothesis (H0) vs Alternative hypothesis (H1)
- Ensure logical connection: RQ → Theory → Hypothesis

### 2. Research Design Selection
Choose appropriate design based on:
- **Experimental**: True randomization, control groups (highest internal validity)
- **Quasi-experimental**: No random assignment but has comparison groups
- **Survey/Correlational**: Measures relationships without manipulation
- **Case Study**: In-depth analysis of specific cases
- **Mixed Methods**: Combining quantitative and qualitative approaches

### 3. Variable Operationalization
- **Independent Variables (IV)**: What you manipulate/compare
- **Dependent Variables (DV)**: What you measure as outcomes
- **Control Variables**: What you hold constant
- **Confounding Variables**: Threats to internal validity
- Ensure clear operational definitions for each variable

### 4. Sampling Strategy
- Population definition
- Sampling method (random, stratified, convenience, purposive)
- Sample size justification (power analysis)
- Inclusion/exclusion criteria

### 5. Data Collection Planning
- Instruments selection/development
- Validity and reliability of measures
- Pilot testing procedures
- Data collection timeline

### 6. Analysis Plan
- Match analysis to research questions
- Statistical tests appropriate for data types
- Effect size measures
- Handling of missing data

### 7. Validity Considerations
- **Internal Validity**: Cause-effect confidence
- **External Validity**: Generalizability
- **Construct Validity**: Measurement accuracy
- **Statistical Conclusion Validity**: Analysis appropriateness

### 8. Ethical Considerations
- Informed consent requirements
- Risk-benefit analysis
- Data privacy and protection
- IRB/Ethics approval process

## Response Guidelines

When discussing experiment design:
1. Always connect back to the Research Definition
2. Question assumptions about causality
3. Suggest alternatives when designs are weak
4. Be specific about statistical requirements
5. Anticipate reviewer concerns

## Important Commands

When the user says:
- "결실" / "비판적 평가" / "critical review" → Comprehensive experiment design evaluation
- "다음 단계로" / "proceed" → Evaluate readiness for data collection
- "요약해줘" / "summarize" → Structured experiment design summary

## Response Style

- Methodologically rigorous but practical
- Focus on feasibility alongside rigor
- Respond in user's language (Korean/English)
- Always constructive

Current context:
- Research Topic: {topic}
- Phase: Experiment Design

## CRITICAL: Experiment Design Artifact Update

After EVERY response, update the Experiment Design Artifact with the format below.
Each section includes a maturity indicator: 🔴 (needs work) → 🟡 (developing) → 🟢 (solid)

Current Artifact:
```markdown
{artifact}
```

You MUST include an updated artifact at the END of EVERY response:

<artifact>
# Experiment Design

## 1. Research Context [🔴/🟡/🟢]
- **Research Topic**: [From Research Definition]
- **Main RQ**: [From Research Definition]
- **Gap Being Addressed**: [From Research Definition]

## 2. Hypotheses [🔴/🟡/🟢]
- **H1**: [Main hypothesis to be tested]
- **H2**: [Secondary hypothesis if applicable]
- **Null Hypothesis**: [What would disprove the hypothesis]

## 3. Research Design [🔴/🟡/🟢]
- **Design Type**: [Experimental/Quasi-experimental/Survey/Case Study/etc.]
- **Approach**: [Quantitative/Qualitative/Mixed Methods]
- **Rationale**: [Why this design is appropriate]

## 4. Variables [🔴/🟡/🟢]
- **Independent Variables (IV)**: [Variables you manipulate/measure as causes]
- **Dependent Variables (DV)**: [Variables you measure as effects]
- **Control Variables**: [Variables held constant]
- **Confounding Variables**: [Potential threats to validity]

## 5. Sampling & Participants [🔴/🟡/🟢]
- **Population**: [Target population]
- **Sampling Method**: [Random/Stratified/Convenience/etc.]
- **Sample Size**: [Planned n with justification]
- **Inclusion Criteria**: [Who is included]
- **Exclusion Criteria**: [Who is excluded]

## 6. Data Collection [🔴/🟡/🟢]
- **Instruments**: [Surveys/Sensors/Interviews/etc.]
- **Procedures**: [Step-by-step data collection process]
- **Timeline**: [Data collection schedule]
- **Pilot Testing**: [Plans for validation]

## 7. Data Analysis Plan [🔴/🟡/🟢]
- **Statistical Methods**: [t-test/ANOVA/Regression/etc.]
- **Software Tools**: [SPSS/R/Python/etc.]
- **Significance Level**: [α = 0.05 typically]
- **Effect Size Measures**: [Cohen's d/η²/etc.]

## 8. Validity & Reliability [🔴/🟡/🟢]
- **Internal Validity**: [Threats and mitigation]
- **External Validity**: [Generalizability considerations]
- **Reliability Measures**: [Test-retest/Inter-rater/etc.]

## 9. Ethical Considerations [🔴/🟡/🟢]
- **IRB/Ethics Approval**: [Status]
- **Informed Consent**: [Process]
- **Data Privacy**: [Protection measures]
- **Risk Assessment**: [Potential harms and mitigation]

## 10. Resources & Timeline [🔴/🟡/🟢]
- **Required Resources**: [Equipment/Software/Funding]
- **Project Timeline**: [Phases and milestones]
- **Potential Risks**: [Project risks and contingencies]

## 11. Pilot Study Plan [🔴/🟡/🟢]
- **Scope**: [What will be tested]
- **Success Criteria**: [How to evaluate pilot]
- **Refinement Process**: [How to incorporate learnings]

## 12. Experiment Readiness Assessment
**Overall Maturity**: [🔴 Early Stage / 🟡 Developing / 🟢 Ready for Execution]
**Blockers**: [What must be resolved before proceeding]
**Next Discussion Focus**: [Priority topic for next round]
</artifact>

IMPORTANT: Always include the <artifact>...</artifact> block. The artifact should reflect the CURRENT experiment design state based on ALL discussions. DO NOT modify the Research Definition artifact - only update the Experiment Design artifact.
"""

    CRITICAL_EVALUATION_PROMPT = """## 결실 단계: 비판적 종합 평가 (Critical Fruition Evaluation)

You are now conducting a rigorous, publication-ready critical evaluation of the research definition.
This is the "fruition stage" where we assess whether the research is ready to proceed with near-perfect logic and novelty.

Based on ALL discussions and the current Research Artifact, provide a comprehensive critical evaluation.

---

## 1. Summary (요약)
Provide a concise 3-5 sentence summary of:
- The core research problem and gap
- The proposed research approach
- The expected contribution

## 2. Strengths (강점) 💪
List the key strengths of this research definition:
- **Logical coherence**: Is the argument flow clear and compelling?
- **Gap clarity**: Is the research gap well-defined and evidence-based?
- **Novelty elements**: What makes this genuinely new?
- **Methodological soundness**: Is the approach feasible and appropriate?
- **Contribution clarity**: Are contributions clear and significant?

Rate each strength: ⭐ (Moderate) / ⭐⭐ (Strong) / ⭐⭐⭐ (Exceptional)

## 3. Weaknesses (약점) ⚠️
Identify weaknesses that MUST be addressed:
- **Logical gaps**: Any flaws in the argument chain?
- **Novelty concerns**: Is this truly novel or incremental?
- **Scope issues**: Too broad? Too narrow?
- **Feasibility risks**: Can this actually be done?
- **Theoretical gaps**: Is the theoretical foundation solid?

Rate each weakness: 🔴 (Critical - must fix) / 🟡 (Important - should address) / 🟢 (Minor - can proceed)

## 4. Detailed Comments (상세 코멘트) 📝
For each section of the Research Artifact, provide specific feedback:

### 4.1 Research Topic & Gap
- Is the gap type correctly identified?
- Is there sufficient evidence of the gap?

### 4.2 Research Questions
- Are RQs SMART (Specific, Measurable, Achievable, Relevant, Time-bound)?
- Is the question hierarchy logical?
- Are the question types appropriate for the contribution?

### 4.3 Theoretical Framework
- Is the chosen theory appropriate?
- Does it adequately guide the research design?
- Are alternative frameworks considered?

### 4.4 Core Argument & Logic
- Is the logical flow: Problem → Gap → Questions → Contribution clear?
- Are there any logical leaps or unstated assumptions?

### 4.5 Novelty & Contribution
- Is the novelty score justified?
- Are differentiators clearly articulated?
- Will the academic community care about this contribution?

### 4.6 Scope & Feasibility
- Are boundaries realistic?
- Have key risks been identified?

## 5. Probing Questions (추가 질문) ❓
Ask 3-5 critical questions that the researcher MUST be able to answer:
- Questions that test the depth of understanding
- Questions that probe potential blind spots
- Questions a reviewer might ask

## 6. Overall Assessment (종합 평가) 📊

### Logic Score: __/10
- **10**: Flawless logical flow, no gaps
- **7-9**: Strong logic, minor refinements needed
- **4-6**: Logic present but significant gaps
- **1-3**: Fundamental logical issues

### Novelty Score: __/10
- **10**: Paradigm-shifting contribution
- **7-9**: Significant novel contribution
- **4-6**: Incremental contribution
- **1-3**: Minimal novelty

### Readiness Level:
- 🟢 **READY**: Logic ≥8 AND Novelty ≥7 - Proceed to Literature Review
- 🟡 **ALMOST**: (Logic ≥7 AND Novelty ≥6) OR (Logic ≥6 AND Novelty ≥7) - One more iteration
- 🔴 **NOT READY**: Logic <6 OR Novelty <5 - Significant refinement needed

### Recommended Actions:
If not ready, provide specific, prioritized actions:
1. [Priority 1: Most critical issue to address]
2. [Priority 2: ...]
3. [Priority 3: ...]

---

**IMPORTANT**: Be rigorous but constructive. The goal is to help refine the research to publication quality.
If not ready, continue the dialogue focusing on the identified gaps.

End with:
- Clear readiness verdict
- Specific next steps
- Encouragement for the researcher
"""

    SUMMARY_PROMPT = """Based on our discussion, provide a comprehensive research definition summary.

## Required Sections (with Maturity Assessment):

### 1. Research Topic & Problem Statement
- Clear, focused statement of what is being studied
- Why is this important?

### 2. Research Gap Analysis
- Gap Type (Theoretical/Methodological/Empirical/Practical)
- Specific gap statement
- Evidence that this gap exists

### 3. Research Questions
- Main RQ (must be SMART: Specific, Measurable, Achievable, Relevant, Time-bound)
- Sub-RQs (2-3 supporting questions)
- Question type (Descriptive/Relational/Causal)

### 4. Theoretical Framework
- What theory or framework guides this research?
- How does it shape the research design?

### 5. Expected Contributions
- Theoretical contribution (if any)
- Methodological contribution (if any)
- Empirical contribution
- Practical implications

### 6. Novelty Assessment
- Score (0-10) with detailed justification
- Existing approaches and how this differs
- Unique differentiators

### 7. Research Scope & Boundaries
- What's included and excluded
- Geographic, temporal, population, conceptual boundaries

### 8. Key Assumptions
- Explicit assumptions underlying this research

### 9. Feasibility Assessment
- Data availability
- Methodological requirements
- Resource needs
- Key challenges

### 10. Keywords for Literature Search
- Primary keywords (5-7)
- Secondary keywords (5-7)
- Key literature domains

## Readiness Assessment

Evaluate readiness for Literature Review phase using this checklist:
- [ ] Research gap is clearly articulated
- [ ] Main RQ is specific and answerable
- [ ] Theoretical framework is identified
- [ ] Contributions are distinguishable
- [ ] Scope boundaries are defined
- [ ] Key assumptions are explicit
- [ ] Feasibility is assessed

**Overall Readiness**: 🔴 Not Ready / 🟡 Almost Ready / 🟢 Ready

If NOT ready, specify:
- What must be resolved before proceeding
- Recommended next discussion topics

Format this as a clear, actionable summary.
"""

    def __init__(
        self,
        llm: Optional[GeminiLLM] = None,
        model: Optional[str] = None,  # Uses settings.gemini_model by default
        temperature: Optional[float] = None,  # Uses settings.gemini_temperature by default
    ):
        """Initialize the Research Discussion Agent.

        Args:
            llm: LLM instance. Creates new one if not provided.
            model: Model name for Gemini (defaults to settings.gemini_model).
            temperature: Temperature for generation (defaults to settings.gemini_temperature).
        """
        if llm:
            self.llm = llm
        else:
            kwargs = {}
            if model is not None:
                kwargs["model"] = model
            if temperature is not None:
                kwargs["temperature"] = temperature
            self.llm = GeminiLLM(**kwargs)
        self.conversation_history: list[dict] = []
        self.topic: str = ""
        self.is_ready_for_next_phase: bool = False
        self.current_phase: str = self.PHASE_RESEARCH_DEFINITION  # Default to research definition

        # Load prompts from files (with fallback to class defaults)
        self._load_prompts()

        self.research_artifact: str = self._initial_artifact  # 연구 아티팩트

        logger.info("ResearchDiscussionAgent initialized", model=model)

    def _load_prompts(self) -> None:
        """Load prompts from external files, with fallback to defaults."""
        # Research Definition prompts
        loaded_system = load_rd_system_prompt()
        self._system_prompt = loaded_system if loaded_system else self.SYSTEM_PROMPT

        loaded_artifact = load_rd_initial_artifact()
        self._initial_artifact = loaded_artifact if loaded_artifact else self.INITIAL_ARTIFACT

        loaded_summary = load_rd_summary_prompt()
        self._summary_prompt = loaded_summary if loaded_summary else self.SUMMARY_PROMPT

        loaded_initial = load_rd_initial_prompt()
        self._initial_prompt_template = loaded_initial if loaded_initial else None

        loaded_readiness = load_rd_readiness_prompt()
        self._readiness_prompt = loaded_readiness if loaded_readiness else None

        # Experiment Design prompts
        loaded_ed_system = load_ed_system_prompt()
        self._ed_system_prompt = loaded_ed_system if loaded_ed_system else self.EXPERIMENT_DESIGN_SYSTEM_PROMPT

        loaded_ed_artifact = load_ed_initial_artifact()
        self._ed_initial_artifact = loaded_ed_artifact if loaded_ed_artifact else self.INITIAL_EXPERIMENT_ARTIFACT

        logger.debug("Prompts loaded",
                    rd_system_from_file=loaded_system is not None,
                    rd_artifact_from_file=loaded_artifact is not None,
                    rd_summary_from_file=loaded_summary is not None,
                    rd_initial_from_file=loaded_initial is not None,
                    rd_readiness_from_file=loaded_readiness is not None,
                    ed_system_from_file=loaded_ed_system is not None,
                    ed_artifact_from_file=loaded_ed_artifact is not None)

    def reload_prompts(self) -> None:
        """Reload prompts from files. Useful for hot-reloading during development."""
        from backend.utils.prompt_loader import PromptLoader
        PromptLoader.clear_cache()
        self._load_prompts()
        logger.info("Prompts reloaded from files")

    def _build_messages(self, user_message: str) -> list:
        """Build message list for LLM including history.

        Uses phase-specific system prompt based on current_phase.
        Prompts are loaded from external files via _load_prompts().
        """
        # Select system prompt based on current phase
        if self.current_phase == self.PHASE_EXPERIMENT_DESIGN:
            system_prompt = self._ed_system_prompt.format(
                topic=self.topic,
                artifact=self.research_artifact
            )
        else:
            # Default to research definition prompt
            system_prompt = self._system_prompt.format(
                topic=self.topic,
                artifact=self.research_artifact
            )

        messages = [SystemMessage(content=system_prompt)]

        # Add conversation history
        for msg in self.conversation_history[-10:]:  # Keep last 10 exchanges
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        # Add current message
        messages.append(HumanMessage(content=user_message))

        return messages

    def set_phase(self, phase: str) -> None:
        """Set the current phase of the agent.

        Args:
            phase: Either PHASE_RESEARCH_DEFINITION or PHASE_EXPERIMENT_DESIGN
        """
        if phase in (self.PHASE_RESEARCH_DEFINITION, self.PHASE_EXPERIMENT_DESIGN):
            old_phase = self.current_phase
            self.current_phase = phase
            logger.info("Agent phase changed", old_phase=old_phase, new_phase=phase)
        else:
            logger.warning("Invalid phase", phase=phase)

    def get_phase(self) -> str:
        """Get the current phase of the agent."""
        return self.current_phase

    def _extract_artifact(self, response: str) -> tuple[str, str]:
        """Extract artifact from response and return (clean_response, artifact).

        Args:
            response: Full response from LLM

        Returns:
            Tuple of (response without artifact, extracted artifact)
        """
        import re

        # Find artifact block
        artifact_match = re.search(r'<artifact>(.*?)</artifact>', response, re.DOTALL)

        if artifact_match:
            artifact_content = artifact_match.group(1).strip()
            # Remove artifact block from response
            clean_response = re.sub(r'<artifact>.*?</artifact>', '', response, flags=re.DOTALL).strip()
            return clean_response, artifact_content
        else:
            # No artifact found, keep existing
            return response, self.research_artifact

    def get_artifact(self) -> str:
        """Get the current research artifact."""
        return self.research_artifact

    def set_artifact(self, artifact: str) -> None:
        """Set the research artifact (for restoring from saved state)."""
        self.research_artifact = artifact

    async def start_discussion(self, topic: str) -> str:
        """Start a new research discussion with the given topic.

        Args:
            topic: Initial research topic from user.

        Returns:
            Agent's initial response evaluating the topic.
        """
        self.topic = topic
        self.conversation_history = []
        self.is_ready_for_next_phase = False
        self.research_artifact = self._initial_artifact  # Reset artifact

        # Use loaded initial prompt template if available
        if self._initial_prompt_template:
            initial_prompt = self._initial_prompt_template.format(topic=topic)
        else:
            # Fallback to hardcoded prompt
            initial_prompt = f"""A researcher has proposed the following research topic:

"{topic}"

## Your Initial Assessment Protocol:

### Step 1: Understand the Surface & Underlying Intent
- What is the researcher actually trying to study?
- What might be the underlying motivation?

### Step 2: Initial Gap Diagnosis
- Does this appear to address a genuine research gap?
- What type of gap might this be targeting? (Theoretical/Methodological/Empirical/Practical)

### Step 3: Research Question Potential
- Can this evolve into a specific, answerable research question?
- What would a strong RQ look like for this topic?

### Step 4: Critical Assessment
- What are the immediate strengths of this idea?
- What are the potential weaknesses or risks?
- What assumptions might the researcher be making?

### Step 5: Clarifying Questions (Socratic Approach)
Ask 3-4 probing questions to:
- Clarify the specific phenomenon of interest
- Understand the intended contribution
- Identify the theoretical grounding
- Assess feasibility constraints

## Response Format:
1. Acknowledge and paraphrase the topic (show understanding)
2. Provide initial assessment (strengths & concerns)
3. Identify the potential research gap type
4. Ask clarifying questions (prioritized)
5. Suggest possible directions for strengthening the idea

Be rigorous but supportive. This is the beginning of a collaborative refinement process.

Remember to include the updated <artifact>...</artifact> block at the end of your response."""

        messages = [
            SystemMessage(content=self._system_prompt.format(
                topic=topic,
                artifact=self.research_artifact
            )),
            HumanMessage(content=initial_prompt),
        ]

        result = await self.llm._agenerate(messages)
        full_response = result.generations[0].message.content

        # Extract artifact from response
        clean_response, new_artifact = self._extract_artifact(full_response)
        self.research_artifact = new_artifact

        # Store in history (without artifact block for cleaner display)
        self.conversation_history.append({"role": "user", "content": f"Research topic: {topic}"})
        self.conversation_history.append({"role": "assistant", "content": clean_response})

        logger.info("Research discussion started", topic=topic[:50])

        return clean_response

    async def chat(self, user_message: str) -> str:
        """Continue the research discussion with a user message.

        Args:
            user_message: User's message in the discussion.

        Returns:
            Agent's response (without artifact block - artifact is stored separately).
        """
        # Check for critical evaluation (결실 단계) commands
        critical_commands = ["결실", "비판적 평가", "critical review", "critical evaluation", "fruition"]
        if any(cmd in user_message.lower() for cmd in critical_commands):
            return await self._generate_critical_evaluation()

        # Check for phase transition commands
        transition_commands = ["다음 단계로", "proceed", "진행해줘", "phase 2", "next phase"]
        if any(cmd in user_message.lower() for cmd in transition_commands):
            return await self._prepare_for_next_phase()

        # Check for summary request
        summary_commands = ["요약해줘", "summarize", "summary", "정리해줘"]
        if any(cmd in user_message.lower() for cmd in summary_commands):
            return await self._generate_summary()

        # Regular conversation
        messages = self._build_messages(user_message)
        result = await self.llm._agenerate(messages)
        full_response = result.generations[0].message.content

        # Extract artifact from response
        clean_response, new_artifact = self._extract_artifact(full_response)
        self.research_artifact = new_artifact

        # Update history (without artifact block)
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": clean_response})

        return clean_response

    async def _generate_summary(self) -> str:
        """Generate a summary of the current research definition."""
        messages = self._build_messages(self._summary_prompt)
        result = await self.llm._agenerate(messages)
        summary = result.generations[0].message.content

        self.conversation_history.append({"role": "user", "content": "[Summary requested]"})
        self.conversation_history.append({"role": "assistant", "content": summary})

        return summary

    async def _generate_critical_evaluation(self) -> str:
        """Generate a critical evaluation at the fruition stage (결실 단계).

        This provides a comprehensive assessment of:
        - Summary
        - Strengths
        - Weaknesses
        - Detailed Comments
        - Questions
        - Overall Assessment (Logic & Novelty scores)

        Returns:
            Critical evaluation response with scores and recommendations.
        """
        import re

        messages = self._build_messages(self.CRITICAL_EVALUATION_PROMPT)
        result = await self.llm._agenerate(messages)
        full_response = result.generations[0].message.content

        # Extract artifact if present
        clean_response, new_artifact = self._extract_artifact(full_response)
        self.research_artifact = new_artifact

        # Parse logic and novelty scores from response
        logic_match = re.search(r'Logic Score[:\s]*(\d+)[/\s]*10', clean_response, re.IGNORECASE)
        novelty_match = re.search(r'Novelty Score[:\s]*(\d+)[/\s]*10', clean_response, re.IGNORECASE)

        logic_score = int(logic_match.group(1)) if logic_match else 0
        novelty_score = int(novelty_match.group(1)) if novelty_match else 0

        # Determine if ready based on scores
        is_ready = logic_score >= 8 and novelty_score >= 7
        is_almost = (logic_score >= 7 and novelty_score >= 6) or (logic_score >= 6 and novelty_score >= 7)

        if is_ready:
            self.is_ready_for_next_phase = True
            clean_response += "\n\n---\n🟢 **결실 단계 평가 완료**: 논리성과 novelty가 충분합니다. Literature Review로 진행할 수 있습니다."
        elif is_almost:
            clean_response += f"\n\n---\n🟡 **결실 단계 평가**: 거의 완성되었습니다. Logic: {logic_score}/10, Novelty: {novelty_score}/10\n한 번 더 개선 후 다시 '결실' 평가를 요청하세요."
        else:
            clean_response += f"\n\n---\n🔴 **결실 단계 평가**: 추가 개선이 필요합니다. Logic: {logic_score}/10, Novelty: {novelty_score}/10\n위에 제시된 약점과 질문들을 검토하고 연구 정의를 수정해 주세요."

        self.conversation_history.append({"role": "user", "content": "[Critical Evaluation - 결실 단계]"})
        self.conversation_history.append({"role": "assistant", "content": clean_response})

        logger.info("Critical evaluation generated",
                   logic_score=logic_score,
                   novelty_score=novelty_score,
                   is_ready=is_ready)

        return clean_response

    async def _prepare_for_next_phase(self) -> str:
        """Prepare for transition to Phase 2 (Literature Review).

        Returns:
            Summary and confirmation message.
        """
        # Use loaded readiness prompt if available
        if self._readiness_prompt:
            readiness_prompt = f"{self._summary_prompt}\n\n{self._readiness_prompt}"
        else:
            # Fallback to hardcoded prompt
            readiness_prompt = f"""{self._summary_prompt}

## Phase Transition Evaluation

Based on the current state of the research definition, conduct a rigorous readiness assessment.

### Readiness Checklist (Mark each as ✅ Ready / ⚠️ Needs Work / ❌ Missing):

1. **Research Gap**: Is there a clearly articulated gap with evidence?
2. **Main Research Question**: Is it SMART (Specific, Measurable, Achievable, Relevant, Time-bound)?
3. **Theoretical Framework**: Is there an identified guiding theory or framework?
4. **Expected Contributions**: Are contributions clearly distinguishable (theoretical/methodological/empirical/practical)?
5. **Research Scope**: Are boundaries clearly defined (what's in/out)?
6. **Key Assumptions**: Are assumptions explicitly stated?
7. **Feasibility**: Has feasibility been assessed (data, methods, resources)?

### Decision Matrix:
- **🟢 READY**: All items are ✅ or at most 1-2 are ⚠️
- **🟡 ALMOST READY**: 1-2 items are ❌ but can proceed with caveats
- **🔴 NOT READY**: 3+ items are ❌ or critical items (Gap, RQ, Framework) are ❌

### Your Assessment:

1. Provide the completed checklist
2. State the overall readiness level (🟢/🟡/🔴)
3. If 🟢 or 🟡: Confirm readiness and summarize key points for Literature Review
4. If 🔴: Specify what must be resolved and suggest next discussion topics

Be honest in your assessment. It's better to refine now than struggle later."""

        messages = self._build_messages(readiness_prompt)
        result = await self.llm._agenerate(messages)
        response = result.generations[0].message.content

        # Check if ready (improved heuristic based on emoji indicators)
        is_green = "🟢" in response and ("ready" in response.lower() or "준비" in response or "진행" in response)
        is_yellow = "🟡" in response and ("almost" in response.lower() or "거의" in response)
        self.is_ready_for_next_phase = is_green or is_yellow

        if self.is_ready_for_next_phase:
            if is_green:
                response += "\n\n---\n**✅ Phase 1 Complete. Research Definition is solid. Ready to proceed to Literature Review.**"
            else:
                response += "\n\n---\n**⚠️ Phase 1 Complete with Caveats. Proceeding to Literature Review, but note the areas needing attention.**"
        else:
            response += "\n\n---\n**❌ Research Definition needs further refinement before proceeding. Please address the identified gaps.**"

        self.conversation_history.append({"role": "user", "content": "[Proceed to next phase]"})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    async def extract_research_definition(self) -> Optional[ResearchDefinition]:
        """Extract structured research definition from the discussion.

        Returns:
            ResearchDefinition if extraction succeeds, None otherwise.
        """
        extraction_prompt = """Based on our entire discussion, extract the research definition in the following JSON format:

{
    "refined_topic": "...",
    "research_questions": ["RQ1: ...", "RQ2: ..."],
    "novelty_assessment": {
        "score": 0.0-1.0,
        "justification": "...",
        "existing_approaches": ["..."],
        "differentiators": ["..."]
    },
    "research_scope": {
        "includes": ["..."],
        "excludes": ["..."]
    },
    "potential_contributions": ["..."],
    "suggested_keywords": ["..."]
}

Provide ONLY the JSON, no additional text."""

        messages = self._build_messages(extraction_prompt)
        result = await self.llm._agenerate(messages)
        text = result.generations[0].message.content

        try:
            import json
            import re

            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                data = json.loads(json_match.group())
                return ResearchDefinition(**data)
        except Exception as e:
            logger.error("Failed to extract research definition", error=str(e))

        return None

    def get_conversation_history(self) -> list[dict]:
        """Get the full conversation history."""
        return self.conversation_history.copy()

    def reset(self) -> None:
        """Reset the agent for a new discussion."""
        self.conversation_history = []
        self.topic = ""
        self.is_ready_for_next_phase = False
        self.research_artifact = self._initial_artifact
