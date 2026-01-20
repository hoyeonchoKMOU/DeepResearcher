"""Gemini Code Assist OAuth-based LLM wrapper for LangChain.

This uses Google's Gemini Code Assist API (cloudcode-pa.googleapis.com)
with OAuth 2.0 + PKCE authentication.
"""

import uuid
from typing import Any, Iterator, List, Optional

import httpx
import structlog
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from backend.auth.token_manager import TokenManager
from backend.config import get_settings

logger = structlog.get_logger(__name__)

# Gemini Code Assist API headers
CODE_ASSIST_HEADERS = {
    "User-Agent": "google-api-nodejs-client/9.15.1",
    "X-Goog-Api-Client": "gl-node/22.17.0",
    "Client-Metadata": "ideType=IDE_UNSPECIFIED,platform=PLATFORM_UNSPECIFIED,pluginType=GEMINI",
}


class GeminiLLM(BaseChatModel):
    """OAuth-based Gemini Chat Model for LangChain.

    Uses Gemini Code Assist API (cloudcode-pa.googleapis.com) with OAuth authentication.

    Available models:
    - gemini-3-pro-preview (with thinking support)
    - gemini-2.5-flash
    - gemini-2.0-flash
    - gemini-1.5-pro
    - gemini-1.5-flash

    Configuration is loaded from settings by default:
    - GEMINI_MODEL: Model name
    - GEMINI_TEMPERATURE: Temperature for generation
    - GEMINI_MAX_OUTPUT_TOKENS: Maximum output tokens
    - GEMINI_THINKING_LEVEL: Thinking level for Gemini 3 models
    - GEMINI_INCLUDE_THOUGHTS: Include thoughts in response
    """

    model: Optional[str] = Field(default=None)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, gt=0)

    # Thinking configuration for Gemini 3 models
    thinking_level: Optional[str] = Field(default=None, description="Thinking level: 'low' or 'high'")
    include_thoughts: Optional[bool] = Field(default=None, description="Include thinking in response")

    token_manager: Optional[TokenManager] = Field(default=None, exclude=True)
    project_id: Optional[str] = Field(default=None)

    _http_client: Optional[httpx.AsyncClient] = None
    _discovered_project_id: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        # Load defaults from settings if not provided
        settings = get_settings()
        if self.model is None:
            self.model = settings.gemini_model
        if self.temperature is None:
            self.temperature = settings.gemini_temperature
        if self.max_output_tokens is None:
            self.max_output_tokens = settings.gemini_max_output_tokens
        if self.thinking_level is None:
            self.thinking_level = settings.gemini_thinking_level
        if self.include_thoughts is None:
            self.include_thoughts = settings.gemini_include_thoughts

        if self.token_manager is None:
            self.token_manager = TokenManager()

        # Try to load project_id from saved tokens
        if not self.project_id:
            token_data = self.token_manager.load_tokens()
            if token_data and token_data.project_id:
                self.project_id = token_data.project_id
                logger.debug("Loaded project_id from tokens", project_id=self.project_id)

    @property
    def _llm_type(self) -> str:
        """Return LLM type identifier."""
        return "gemini-cli"

    @property
    def _endpoint(self) -> str:
        """Get the Gemini API endpoint for non-streaming."""
        base = get_settings().gemini_endpoint
        return f"{base}/v1internal:generateContent"

    @property
    def _stream_endpoint(self) -> str:
        """Get the streaming API endpoint."""
        base = get_settings().gemini_endpoint
        return f"{base}/v1internal:streamGenerateContent?alt=sse"

    async def _discover_project_id(self, access_token: str) -> str:
        """Discover the project ID via loadCodeAssist API.

        Args:
            access_token: Valid OAuth access token.

        Returns:
            Discovered project ID.
        """
        if self._discovered_project_id:
            return self._discovered_project_id

        if self.project_id:
            return self.project_id

        settings = get_settings()
        endpoint = settings.gemini_endpoint

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **CODE_ASSIST_HEADERS,
        }

        body = {
            "metadata": {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                url = f"{endpoint}/v1internal:loadCodeAssist"
                response = await client.post(url, headers=headers, json=body)

                if response.status_code == 200:
                    data = response.json()
                    project = data.get("cloudaicompanionProject")
                    if project:
                        self._discovered_project_id = project
                        logger.info("Discovered project ID", project_id=project)
                        # Save project_id to tokens for future use
                        self._save_project_id(project)
                        return project

                    # Try onboarding if no project found
                    logger.info("No project found, attempting onboarding...")
                    project = await self._onboard_project(access_token, data)
                    if project:
                        self._discovered_project_id = project
                        return project
                else:
                    logger.warning(
                        "loadCodeAssist failed",
                        status=response.status_code,
                        response=response.text[:200],
                    )
            except Exception as e:
                logger.error("loadCodeAssist error", error=str(e))

        raise ValueError(
            "Failed to discover project ID. Please set GCP_PROJECT_ID in your environment."
        )

    async def _onboard_project(self, access_token: str, load_payload: dict) -> Optional[str]:
        """Onboard a managed project for the user.

        Args:
            access_token: Valid OAuth access token.
            load_payload: Response from loadCodeAssist.

        Returns:
            Managed project ID or None.
        """
        settings = get_settings()
        endpoint = settings.gemini_endpoint

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **CODE_ASSIST_HEADERS,
        }

        # Get default tier
        allowed_tiers = load_payload.get("allowedTiers", [])
        tier_id = "FREE"
        for tier in allowed_tiers:
            if tier.get("isDefault"):
                tier_id = tier.get("id", "FREE")
                break
        if not tier_id and allowed_tiers:
            tier_id = allowed_tiers[0].get("id", "FREE")

        body = {
            "tierId": tier_id,
            "metadata": {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(5):
                try:
                    url = f"{endpoint}/v1internal:onboardUser"
                    response = await client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("done"):
                            project = data.get("response", {}).get("cloudaicompanionProject", {}).get("id")
                            if project:
                                logger.info("Onboarded project", project_id=project)
                                return project
                except Exception as e:
                    logger.debug("Onboard attempt failed", attempt=attempt, error=str(e))

                import asyncio
                await asyncio.sleep(3)

        return None

    def _save_project_id(self, project_id: str) -> None:
        """Save discovered project_id to token storage.

        Args:
            project_id: The discovered project ID.
        """
        try:
            token_data = self.token_manager.load_tokens()
            if token_data:
                token_data.project_id = project_id
                self.token_manager.save_tokens(token_data)
                logger.info("Saved project_id to tokens", project_id=project_id)
        except Exception as e:
            logger.warning("Failed to save project_id", error=str(e))

    def _convert_messages_to_gemini_format(
        self, messages: List[BaseMessage]
    ) -> tuple[Optional[str], List[dict]]:
        """Convert LangChain messages to Gemini API format.

        Args:
            messages: List of LangChain messages.

        Returns:
            Tuple of (system_instruction, contents list).
        """
        system_instruction = None
        contents = []

        for message in messages:
            if isinstance(message, SystemMessage):
                system_instruction = message.content
            elif isinstance(message, HumanMessage):
                contents.append({
                    "role": "user",
                    "parts": [{"text": message.content}],
                })
            elif isinstance(message, AIMessage):
                contents.append({
                    "role": "model",
                    "parts": [{"text": message.content}],
                })

        return system_instruction, contents

    def _build_request_body(
        self,
        messages: List[BaseMessage],
        project_id: str,
    ) -> dict:
        """Build Gemini CLI API request body.

        Args:
            messages: List of messages.
            project_id: GCP project ID.

        Returns:
            Request body dictionary in Gemini CLI format.
        """
        system_instruction, contents = self._convert_messages_to_gemini_format(messages)

        # Build generation config
        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_output_tokens,
            "topP": self.top_p,
            "topK": self.top_k,
        }

        # Add thinkingConfig for Gemini 3 models
        if "gemini-3" in self.model:
            generation_config["thinkingConfig"] = {
                "thinkingLevel": self.thinking_level.upper(),
                "includeThoughts": self.include_thoughts,
            }

        # Inner request payload (standard Gemini format)
        request_payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        if system_instruction:
            request_payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Wrap in Gemini CLI format
        return {
            "project": project_id,
            "model": self.model,
            "request": request_payload,
        }

    async def _get_headers(self, access_token: str, streaming: bool = False) -> dict[str, str]:
        """Get request headers with valid access token.

        Args:
            access_token: OAuth access token.
            streaming: Whether this is a streaming request.

        Returns:
            Headers dictionary.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **CODE_ASSIST_HEADERS,
        }

        if streaming:
            headers["Accept"] = "text/event-stream"

        return headers

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response synchronously.

        This wraps the async implementation.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._agenerate(messages, stop, run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response asynchronously.

        Args:
            messages: List of messages.
            stop: Stop sequences (not fully supported).
            run_manager: Callback manager.
            **kwargs: Additional arguments.

        Returns:
            Chat result with generated response.
        """
        access_token = await self.token_manager.get_valid_access_token()
        if not access_token:
            raise ValueError(
                "No valid access token. Please authenticate first."
            )

        project_id = await self._discover_project_id(access_token)
        headers = await self._get_headers(access_token)
        body = self._build_request_body(messages, project_id)

        logger.debug(
            "Sending request to Gemini CLI",
            endpoint=self._endpoint,
            model=self.model,
            project=project_id,
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self._endpoint, headers=headers, json=body)

            if response.status_code == 429:
                logger.warning("Rate limit exceeded")
                raise Exception("Rate limit exceeded. Please wait and try again.")

            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(
                    "API request failed",
                    status=response.status_code,
                    response=error_text,
                )
                raise Exception(f"API error {response.status_code}: {error_text}")

            data = response.json()

            # Gemini CLI wraps the response in a "response" field
            if "response" in data:
                data = data["response"]

            # Parse response - standard Gemini format
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError(f"No response candidates returned from API: {data}")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            text = "".join(part.get("text", "") for part in parts)

            # Get usage metadata
            usage_metadata = data.get("usageMetadata", {})

            message = AIMessage(
                content=text,
                additional_kwargs={
                    "finish_reason": candidates[0].get("finishReason"),
                    "usage": {
                        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                        "total_tokens": usage_metadata.get("totalTokenCount", 0),
                    },
                },
            )

            return ChatResult(
                generations=[ChatGeneration(message=message)],
                llm_output={
                    "model": self.model,
                    "usage": usage_metadata,
                    "project_id": project_id,
                },
            )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream response synchronously."""
        import asyncio

        async def async_stream():
            async for chunk in self._astream(messages, stop, run_manager, **kwargs):
                yield chunk

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async_gen = async_stream()
        while True:
            try:
                yield loop.run_until_complete(async_gen.__anext__())
            except StopAsyncIteration:
                break

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ):
        """Stream response asynchronously using SSE.

        Args:
            messages: List of messages.
            stop: Stop sequences.
            run_manager: Callback manager.
            **kwargs: Additional arguments.

        Yields:
            Chat generation chunks.
        """
        access_token = await self.token_manager.get_valid_access_token()
        if not access_token:
            raise ValueError(
                "No valid access token. Please authenticate first."
            )

        project_id = await self._discover_project_id(access_token)
        headers = await self._get_headers(access_token, streaming=True)
        body = self._build_request_body(messages, project_id)

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", self._stream_endpoint, headers=headers, json=body) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # SSE format: data: {...}
                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix

                    if line == "[DONE]":
                        break

                    # Parse streaming response (JSON)
                    import json
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Gemini CLI may wrap response
                    if "response" in data:
                        data = data["response"]

                    # Standard Gemini response format
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue

                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    text = "".join(part.get("text", "") for part in parts)

                    if text:
                        chunk = ChatGenerationChunk(
                            message=AIMessageChunk(content=text)
                        )
                        yield chunk

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters."""
        params = {
            "model": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "project_id": self.project_id or self._discovered_project_id,
        }
        # Include thinking config for Gemini 3 models
        if "gemini-3" in self.model:
            params["thinking_level"] = self.thinking_level
            params["include_thoughts"] = self.include_thoughts
        return params

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Simple method to generate a response from a prompt.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.
            max_tokens: Override max output tokens.

        Returns:
            Generated text response.
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        # Temporarily override max tokens if specified
        original_max_tokens = self.max_output_tokens
        if max_tokens:
            self.max_output_tokens = max_tokens

        try:
            result = await self._agenerate(messages)
            return result.generations[0].message.content
        finally:
            self.max_output_tokens = original_max_tokens
