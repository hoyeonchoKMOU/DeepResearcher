"""Base Agent class for all research agents."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

import structlog
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from backend.llm.gemini import GeminiLLM

logger = structlog.get_logger(__name__)

TOutput = TypeVar("TOutput", bound=BaseModel)


class BaseAgent(ABC, Generic[TOutput]):
    """Abstract base class for all research agents.

    Provides common functionality for LLM-based agents including:
    - Prompt template loading
    - Output parsing with Pydantic models
    - Tool integration
    - Standardized execution interface
    """

    def __init__(
        self,
        llm: Optional[GeminiLLM] = None,
        model: Optional[str] = None,  # Uses settings.gemini_model by default
        temperature: Optional[float] = None,  # Uses settings.gemini_temperature by default
    ):
        """Initialize base agent.

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
        self.prompt = self._load_prompt()
        self.output_parser = PydanticOutputParser(pydantic_object=self.output_schema)
        self.tools = self._get_tools()

        logger.info(
            "Agent initialized",
            agent=self.__class__.__name__,
            model=model,
        )

    @property
    @abstractmethod
    def output_schema(self) -> type[TOutput]:
        """Define the Pydantic model for agent output.

        Returns:
            Pydantic model class for output validation.
        """
        pass

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Agent name for logging and identification.

        Returns:
            Human-readable agent name.
        """
        pass

    @property
    def prompt_file(self) -> str:
        """Get prompt file name.

        Override this to use a custom prompt file name.

        Returns:
            Prompt file name without extension.
        """
        # Convert class name to snake_case
        name = self.__class__.__name__
        # Remove 'Agent' suffix if present
        if name.endswith("Agent"):
            name = name[:-5]
        # Convert to snake_case
        import re
        name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()
        return name

    def _load_prompt(self) -> ChatPromptTemplate:
        """Load prompt template from file or return default.

        Returns:
            ChatPromptTemplate instance.
        """
        prompt_path = (
            Path(__file__).parent.parent / "config" / "prompts" / f"{self.prompt_file}.txt"
        )

        if prompt_path.exists():
            with open(prompt_path) as f:
                template = f.read()
            logger.debug("Loaded prompt from file", path=str(prompt_path))
        else:
            template = self._default_prompt_template()
            logger.debug("Using default prompt template", agent=self.agent_name)

        return ChatPromptTemplate.from_messages([
            ("system", template),
            ("human", "{input}"),
        ])

    @abstractmethod
    def _default_prompt_template(self) -> str:
        """Default prompt template if file not found.

        Returns:
            Default system prompt string.
        """
        pass

    def _get_tools(self) -> list:
        """Get tools for this agent.

        Override this to provide custom tools.

        Returns:
            List of LangChain tools.
        """
        return []

    def _format_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Format input data for the prompt.

        Override this to customize input formatting.

        Args:
            input_data: Raw input data.

        Returns:
            Formatted input data for prompt.
        """
        # Add format instructions for output parser
        format_instructions = self.output_parser.get_format_instructions()
        input_str = self._input_to_string(input_data)

        return {
            "input": f"{input_str}\n\nPlease respond in the following format:\n{format_instructions}",
        }

    def _input_to_string(self, input_data: dict[str, Any]) -> str:
        """Convert input data to string representation.

        Override this for custom input formatting.

        Args:
            input_data: Input data dictionary.

        Returns:
            String representation of input.
        """
        parts = []
        for key, value in input_data.items():
            if isinstance(value, list):
                value = "\n".join(f"  - {item}" for item in value)
            parts.append(f"{key}:\n{value}")
        return "\n\n".join(parts)

    async def run(self, input_data: dict[str, Any]) -> TOutput:
        """Execute the agent with given input.

        Args:
            input_data: Input data for the agent.

        Returns:
            Parsed output according to output_schema.

        Raises:
            Exception: If LLM call or parsing fails.
        """
        logger.info("Agent executing", agent=self.agent_name, input_keys=list(input_data.keys()))

        formatted_input = self._format_input(input_data)

        # Build chain
        chain = self.prompt | self.llm | self.output_parser

        try:
            result = await chain.ainvoke(formatted_input)
            logger.info("Agent completed", agent=self.agent_name)
            return result
        except Exception as e:
            logger.error("Agent execution failed", agent=self.agent_name, error=str(e))
            raise

    def run_sync(self, input_data: dict[str, Any]) -> TOutput:
        """Execute the agent synchronously.

        Args:
            input_data: Input data for the agent.

        Returns:
            Parsed output according to output_schema.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.run(input_data))

    async def run_with_tools(self, input_data: dict[str, Any]) -> TOutput:
        """Execute the agent with tool support.

        For agents that use tools, this method runs the agent in a loop
        allowing tool calls until a final answer is produced.

        Args:
            input_data: Input data for the agent.

        Returns:
            Final output after tool execution.
        """
        if not self.tools:
            return await self.run(input_data)

        # For agents with tools, we need ReAct-style execution
        # This is a simplified version; full implementation would use LangGraph
        from langchain_core.messages import HumanMessage

        formatted_input = self._format_input(input_data)
        messages = [HumanMessage(content=formatted_input["input"])]

        # Simple single-turn for now
        # Full tool loop would be implemented in LangGraph orchestrator
        result = await self.llm._agenerate(messages)
        text = result.generations[0].message.content

        try:
            return self.output_parser.parse(text)
        except Exception:
            # If parsing fails, try to extract JSON from response
            import json
            import re

            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                data = json.loads(json_match.group())
                return self.output_schema(**data)
            raise


class AgentMessage(BaseModel):
    """Standard message format for agent communication."""

    agent_name: str
    content: Any
    metadata: dict[str, Any] = {}


class AgentState(BaseModel):
    """Base state for agent workflow."""

    messages: list[AgentMessage] = []
    current_agent: Optional[str] = None
    phase: str = "init"
    error: Optional[str] = None
