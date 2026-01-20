"""Paper Writing Agent for DeepResearcher.

This agent helps users create:
1. Paper Title (5 candidates)
2. Paper Structure (IMRAD format with up to 2nd level sections)
3. Introduction section only

The agent operates in a conversational mode, maintaining dialogue history
and naturally guiding the user through the paper writing workflow.

Architecture follows ResearchDiscussionAgent pattern:
- System prompt defines all behavior
- LLM handles intent detection naturally through conversation
- Artifact is extracted from responses using <artifact> tags
"""

import structlog
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.llm.gemini import GeminiLLM
from backend.auth.token_manager import TokenManager
from backend.utils.prompt_loader import load_pw_system_prompt, load_pw_initial_artifact

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants - prompts are now loaded from data/prompts/PW/
# =============================================================================

WELCOME_MESSAGE = """## 논문 작성 도우미

안녕하세요! Research Definition과 Experiment Design을 기반으로 논문 작성을 도와드리겠습니다.

### 제공 기능
이 도우미는 다음 **3가지 기능만** 지원합니다:

1. **제목 생성** - 5개의 학술 논문 제목 후보를 제안합니다
2. **구조 설계** - IMRAD 형식의 논문 구조(2수준 절까지)를 설계합니다
3. **서론 작성** - 4단락 구조의 Introduction을 작성합니다

### 사용 방법
원하시는 작업을 말씀해주세요:
- "제목을 만들어주세요"
- "논문 구조를 잡아주세요"
- "서론을 써주세요"

또는 순서대로 진행하시려면 **"제목 생성"**부터 시작하세요.

> *참고: Methods, Results, Discussion 등 다른 섹션 작성은 지원하지 않습니다.*
"""


# =============================================================================
# Agent Class
# =============================================================================

class PaperWritingAgent:
    """Conversational agent for paper writing assistance.

    Operates in a free-form conversational mode like ResearchDiscussionAgent:
    - Maintains dialogue history
    - Uses system prompt to define all behavior
    - Extracts artifact from responses using <artifact> tags
    - LLM naturally handles intent detection through conversation
    """

    def __init__(self, model: Optional[str] = None):
        """Initialize paper writing agent.

        Args:
            model: Optional model override.
        """
        self.model = model
        self.llm: Optional[GeminiLLM] = None
        self.conversation_history: list[dict] = []

        # Load initial artifact from file
        initial_artifact = load_pw_initial_artifact()
        self.artifact: str = initial_artifact if initial_artifact else "# [논문 제목 미정]\n\n## 1. Introduction\n[작성 대기]"

        self.research_definition: str = ""
        self.experiment_design: str = ""

    async def _get_llm(self) -> GeminiLLM:
        """Get or create LLM instance."""
        if self.llm is None:
            token_manager = TokenManager()
            access_token = await token_manager.get_valid_access_token()
            if not access_token:
                raise ValueError("Not authenticated")

            self.llm = GeminiLLM(
                access_token=access_token,
                model=self.model,
                include_thoughts=False,
            )
        return self.llm

    def _build_messages(self, user_message: str) -> list:
        """Build message list for LLM including history."""
        # Load system prompt from file
        system_prompt_template = load_pw_system_prompt()
        if not system_prompt_template:
            raise ValueError("Failed to load PW system prompt from data/prompts/PW/system_prompt.md")

        system_prompt = system_prompt_template.format(
            research_definition=self.research_definition[:8000] if self.research_definition else "[미입력]",
            experiment_design=self.experiment_design[:8000] if self.experiment_design else "[미입력]",
        )

        messages = [SystemMessage(content=system_prompt)]

        # Add conversation history (last 10 exchanges)
        for msg in self.conversation_history[-10:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        # Add current message
        messages.append(HumanMessage(content=user_message))

        return messages

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
            return response, self.artifact

    def get_artifact(self) -> str:
        """Get the current paper artifact."""
        return self.artifact

    def set_artifact(self, artifact: str) -> None:
        """Set the paper artifact (for restoring from saved state)."""
        self.artifact = artifact

    def set_context(self, research_definition: str, experiment_design: str) -> None:
        """Set the research context for paper writing.

        Args:
            research_definition: Research Definition document content.
            experiment_design: Experiment Design document content.
        """
        self.research_definition = research_definition
        self.experiment_design = experiment_design

    async def chat(self, user_message: str) -> str:
        """Process user message and return response.

        Args:
            user_message: User's message.

        Returns:
            Agent's response (without artifact block - artifact is stored separately).
        """
        llm = await self._get_llm()

        # Build messages with history and context
        messages = self._build_messages(user_message)

        # Generate response
        result = await llm._agenerate(messages)
        full_response = result.generations[0].message.content

        # Extract artifact from response
        clean_response, new_artifact = self._extract_artifact(full_response)
        self.artifact = new_artifact

        # Update history (without artifact block for cleaner display)
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": clean_response})

        logger.info("Paper writing chat completed",
                   history_length=len(self.conversation_history),
                   artifact_updated=new_artifact != self.artifact)

        return clean_response

    def get_conversation_history(self) -> list[dict]:
        """Get the full conversation history."""
        return self.conversation_history.copy()

    def reset(self, reset_messages: bool = True, reset_artifact: bool = True) -> None:
        """Reset the agent.

        Args:
            reset_messages: Whether to reset conversation history.
            reset_artifact: Whether to reset the artifact.
        """
        if reset_messages:
            self.conversation_history = []
        if reset_artifact:
            self.artifact = INITIAL_ARTIFACT
        logger.info("Paper writing agent reset",
                   messages_reset=reset_messages,
                   artifact_reset=reset_artifact)

    # =========================================================================
    # Legacy API compatibility (for existing routes)
    # =========================================================================

    async def process_message(
        self,
        user_message: str,
        research_definition: str,
        experiment_design: str,
        current_artifact: str = "",
    ) -> tuple[str, str]:
        """Process user message and return response.

        This method maintains backward compatibility with existing API routes.

        Args:
            user_message: User's message.
            research_definition: Research Definition content.
            experiment_design: Experiment Design content.
            current_artifact: Current artifact content.

        Returns:
            Tuple of (response_message, updated_artifact)
        """
        # Update context
        self.set_context(research_definition, experiment_design)

        # Restore artifact if provided
        if current_artifact:
            self.artifact = current_artifact

        # Process message
        response = await self.chat(user_message)

        return response, self.artifact


# =============================================================================
# Helper functions
# =============================================================================

def get_welcome_message() -> str:
    """Get the welcome message for paper writing."""
    return WELCOME_MESSAGE


async def run_full_paper_workflow(
    research_definition: str,
    experiment_design: str,
    progress_callback=None,
) -> dict:
    """Run the full paper writing workflow.

    This runs all three steps in sequence:
    1. Generate titles (user selects first by default)
    2. Create structure
    3. Write introduction

    Args:
        research_definition: RD content.
        experiment_design: ED content.
        progress_callback: Optional async callback for progress updates.

    Returns:
        Dict with titles, structure, introduction, and full_artifact.
    """
    agent = PaperWritingAgent()
    agent.set_context(research_definition, experiment_design)

    # Step 1: Generate titles
    if progress_callback:
        await progress_callback("제목 후보를 생성하고 있습니다...")

    titles_response = await agent.chat("제목 5개를 만들어주세요.")

    # Step 2: Select first title and generate structure
    if progress_callback:
        await progress_callback("논문 구조를 설계하고 있습니다...")

    structure_response = await agent.chat("첫 번째 제목으로 결정하고, 논문 구조를 잡아주세요.")

    # Step 3: Write introduction
    if progress_callback:
        await progress_callback("서론을 작성하고 있습니다...")

    intro_response = await agent.chat("서론을 작성해주세요.")

    return {
        "titles": titles_response,
        "structure": structure_response,
        "introduction": intro_response,
        "full_artifact": agent.get_artifact(),
    }
