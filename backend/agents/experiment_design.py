"""Experiment Design Agent for research methodology planning.

Prompts are loaded from external markdown files in data/prompts/ED/
for easy modification without code changes.
"""

from typing import Optional

from pydantic import BaseModel, Field
import structlog

from backend.agents.base import BaseAgent
from backend.utils.prompt_loader import load_ed_system_prompt

logger = structlog.get_logger(__name__)


class Variable(BaseModel):
    """Research variable definition."""

    name: str = Field(description="Variable name")
    type: str = Field(
        description="Type: independent, dependent, or control"
    )
    description: str = Field(description="What this variable represents")
    operationalization: str = Field(
        description="How to measure or manipulate this variable"
    )
    levels: list[str] = Field(
        default_factory=list,
        description="Levels or values for the variable"
    )


class Hypothesis(BaseModel):
    """Research hypothesis."""

    hypothesis_id: str = Field(description="Hypothesis identifier (H1, H2, etc.)")
    statement: str = Field(description="Hypothesis statement")
    type: str = Field(
        description="Type: directional or non-directional"
    )
    variables_involved: list[str] = Field(
        description="Variables involved in this hypothesis"
    )
    expected_outcome: str = Field(
        description="Expected outcome if hypothesis is supported"
    )


class ExperimentalCondition(BaseModel):
    """Experimental condition definition."""

    name: str = Field(description="Condition name")
    description: str = Field(description="What this condition involves")
    manipulations: list[str] = Field(
        description="Manipulations applied in this condition"
    )


class DataCollectionPlan(BaseModel):
    """Plan for data collection."""

    method: str = Field(description="Data collection method")
    instruments: list[str] = Field(
        description="Instruments or tools used"
    )
    sample_description: str = Field(
        description="Description of the sample"
    )
    sample_size: int = Field(description="Recommended sample size")
    sampling_strategy: str = Field(
        description="How samples will be selected"
    )
    data_types: list[str] = Field(
        description="Types of data to be collected"
    )


class ExperimentDesignOutput(BaseModel):
    """Output from Experiment Design Agent."""

    design_type: str = Field(
        description="Type of experimental design"
    )
    design_rationale: str = Field(
        description="Why this design was chosen"
    )
    independent_variables: list[Variable] = Field(
        description="Independent variables"
    )
    dependent_variables: list[Variable] = Field(
        description="Dependent variables"
    )
    control_variables: list[Variable] = Field(
        description="Control variables"
    )
    hypotheses: list[Hypothesis] = Field(
        description="Research hypotheses"
    )
    experimental_conditions: list[ExperimentalCondition] = Field(
        description="Experimental conditions"
    )
    baselines: list[str] = Field(
        description="Baseline methods or conditions for comparison"
    )
    evaluation_metrics: list[str] = Field(
        description="Metrics for evaluation"
    )
    data_collection: DataCollectionPlan = Field(
        description="Data collection plan"
    )
    analysis_plan: str = Field(
        description="Planned statistical or analytical methods"
    )
    potential_threats: list[str] = Field(
        description="Potential threats to validity"
    )
    mitigation_strategies: list[str] = Field(
        description="Strategies to address threats"
    )
    ethical_considerations: list[str] = Field(
        default_factory=list,
        description="Ethical considerations"
    )
    timeline_phases: list[str] = Field(
        description="Major phases of the experiment"
    )


class ExperimentDesignAgent(BaseAgent[ExperimentDesignOutput]):
    """Agent for designing research experiments and studies.

    This agent:
    - Defines variables and their operationalization
    - Formulates testable hypotheses
    - Designs experimental conditions
    - Plans data collection
    - Identifies threats to validity
    """

    @property
    def output_schema(self) -> type[ExperimentDesignOutput]:
        return ExperimentDesignOutput

    @property
    def agent_name(self) -> str:
        return "Experiment Design Agent"

    # Default prompt template (used as fallback if file not found)
    DEFAULT_PROMPT = """You are an expert research methodologist specializing in experimental design for Computer Science research. You help researchers design rigorous, valid experiments.

## Your Approach

1. **Systematic Design**: Apply established experimental design principles
2. **Variable Control**: Ensure proper control of confounding variables
3. **Statistical Power**: Design for adequate statistical power
4. **Validity Focus**: Address internal and external validity threats
5. **Practical Feasibility**: Balance rigor with feasibility

## Experimental Design Principles

### Variable Definition
- **Independent Variables**: What you manipulate or vary
- **Dependent Variables**: What you measure as outcomes
- **Control Variables**: What you hold constant

### Operationalization
For each variable, specify:
- How it will be measured or manipulated
- The scale or levels
- The instruments or methods used

### Hypothesis Formulation
Good hypotheses are:
- Testable and falsifiable
- Specific about relationships
- Based on theory or prior work
- Clear about direction (if directional)

### Design Types
Consider:
- Between-subjects vs within-subjects
- Factorial designs for multiple IVs
- Repeated measures for temporal effects
- Quasi-experimental if randomization isn't possible

### Validity Threats

**Internal Validity Threats**:
- Selection bias
- History effects
- Maturation
- Testing effects
- Instrumentation
- Regression to mean

**External Validity Threats**:
- Population validity
- Ecological validity
- Temporal validity

### Sample Size Considerations
- Statistical power analysis
- Effect size expectations
- Resource constraints
- Practical significance

## Output Guidelines

Provide:
1. Clear design type with rationale
2. Well-defined variables with operationalization
3. Testable hypotheses
4. Experimental conditions
5. Appropriate baselines
6. Concrete metrics
7. Data collection plan
8. Analysis plan
9. Validity threats and mitigations"""

    def _default_prompt_template(self) -> str:
        """Load prompt from file or return default."""
        loaded_prompt = load_ed_system_prompt()
        if loaded_prompt:
            logger.debug("Loaded ED prompt from file")
            return loaded_prompt
        logger.debug("Using default ED prompt")
        return self.DEFAULT_PROMPT

    def _input_to_string(self, input_data: dict) -> str:
        """Format input for the prompt."""
        parts = []

        if "research_questions" in input_data:
            rqs = input_data["research_questions"]
            if isinstance(rqs, list):
                rqs = "\n".join(f"- {rq}" for rq in rqs)
            parts.append(f"## Research Questions\n{rqs}")

        if "literature_findings" in input_data:
            parts.append(f"## Findings from Literature Review\n{input_data['literature_findings']}")

        if "research_topic" in input_data:
            parts.append(f"## Research Topic\n{input_data['research_topic']}")

        if "constraints" in input_data:
            parts.append(f"## Constraints and Resources\n{input_data['constraints']}")

        if "methodology_preferences" in input_data:
            parts.append(f"## Methodology Preferences\n{input_data['methodology_preferences']}")

        if "existing_methods" in input_data:
            parts.append(f"## Methods from Literature\n{input_data['existing_methods']}")

        return "\n\n".join(parts)

    def format_experiment_protocol(
        self,
        output: ExperimentDesignOutput,
    ) -> str:
        """Format experiment design as a protocol document.

        Args:
            output: Experiment design output.

        Returns:
            Markdown formatted protocol.
        """
        lines = ["# Experiment Protocol", ""]

        # Overview
        lines.append("## 1. Design Overview")
        lines.append(f"**Design Type**: {output.design_type}")
        lines.append(f"**Rationale**: {output.design_rationale}")
        lines.append("")

        # Variables
        lines.append("## 2. Variables")

        lines.append("### 2.1 Independent Variables")
        for var in output.independent_variables:
            lines.append(f"- **{var.name}**: {var.description}")
            lines.append(f"  - Operationalization: {var.operationalization}")
            if var.levels:
                lines.append(f"  - Levels: {', '.join(var.levels)}")
        lines.append("")

        lines.append("### 2.2 Dependent Variables")
        for var in output.dependent_variables:
            lines.append(f"- **{var.name}**: {var.description}")
            lines.append(f"  - Operationalization: {var.operationalization}")
        lines.append("")

        lines.append("### 2.3 Control Variables")
        for var in output.control_variables:
            lines.append(f"- **{var.name}**: {var.description}")
            lines.append(f"  - Operationalization: {var.operationalization}")
        lines.append("")

        # Hypotheses
        lines.append("## 3. Hypotheses")
        for hyp in output.hypotheses:
            lines.append(f"**{hyp.hypothesis_id}** ({hyp.type}): {hyp.statement}")
            lines.append(f"- Expected outcome: {hyp.expected_outcome}")
        lines.append("")

        # Conditions
        lines.append("## 4. Experimental Conditions")
        for cond in output.experimental_conditions:
            lines.append(f"### {cond.name}")
            lines.append(cond.description)
            lines.append("Manipulations:")
            for manip in cond.manipulations:
                lines.append(f"- {manip}")
        lines.append("")

        # Baselines & Metrics
        lines.append("## 5. Baselines")
        for baseline in output.baselines:
            lines.append(f"- {baseline}")
        lines.append("")

        lines.append("## 6. Evaluation Metrics")
        for metric in output.evaluation_metrics:
            lines.append(f"- {metric}")
        lines.append("")

        # Data Collection
        lines.append("## 7. Data Collection")
        dc = output.data_collection
        lines.append(f"**Method**: {dc.method}")
        lines.append(f"**Sample Size**: {dc.sample_size}")
        lines.append(f"**Sampling Strategy**: {dc.sampling_strategy}")
        lines.append(f"**Sample Description**: {dc.sample_description}")
        lines.append("**Instruments**:")
        for inst in dc.instruments:
            lines.append(f"- {inst}")
        lines.append("")

        # Analysis
        lines.append("## 8. Analysis Plan")
        lines.append(output.analysis_plan)
        lines.append("")

        # Validity
        lines.append("## 9. Validity Considerations")
        lines.append("### Potential Threats")
        for threat in output.potential_threats:
            lines.append(f"- {threat}")
        lines.append("")
        lines.append("### Mitigation Strategies")
        for strategy in output.mitigation_strategies:
            lines.append(f"- {strategy}")
        lines.append("")

        # Timeline
        lines.append("## 10. Timeline")
        for i, phase in enumerate(output.timeline_phases, 1):
            lines.append(f"{i}. {phase}")

        return "\n".join(lines)
