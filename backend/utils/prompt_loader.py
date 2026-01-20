"""Prompt Loader Utility.

Loads prompts from markdown files in data/prompts/ directory.
This allows easy modification of prompts without changing code.

Directory Structure:
- data/prompts/RD/  (Research Definition)
  - system_prompt.md
  - initial_artifact.md
  - summary_prompt.md
  - initial_prompt.md
  - readiness_prompt.md
- data/prompts/ED/  (Experiment Design)
  - system_prompt.md
- data/prompts/LR/  (Literature Review - future)
- data/prompts/PW/  (Paper Writing - future)
"""

from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

# Base directory for prompts
PROMPTS_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "prompts"


class PromptLoader:
    """Loads and caches prompts from markdown files."""

    _cache: dict[str, str] = {}

    @classmethod
    def _get_prompt_path(cls, category: str, prompt_name: str) -> Path:
        """Get the full path to a prompt file.

        Args:
            category: Prompt category (RD, ED, LR, PW, etc.)
            prompt_name: Name of the prompt file (without .md extension)

        Returns:
            Path to the prompt file.
        """
        return PROMPTS_BASE_DIR / category / f"{prompt_name}.md"

    @classmethod
    def load(cls, category: str, prompt_name: str, use_cache: bool = True) -> Optional[str]:
        """Load a prompt from file.

        Args:
            category: Prompt category (RD, ED, LR, PW, etc.)
            prompt_name: Name of the prompt file (without .md extension)
            use_cache: Whether to use cached version if available.

        Returns:
            Prompt content or None if file not found.
        """
        cache_key = f"{category}/{prompt_name}"

        # Check cache
        if use_cache and cache_key in cls._cache:
            return cls._cache[cache_key]

        # Load from file
        prompt_path = cls._get_prompt_path(category, prompt_name)

        try:
            if prompt_path.exists():
                content = prompt_path.read_text(encoding="utf-8")
                cls._cache[cache_key] = content
                logger.debug("Loaded prompt", category=category, prompt=prompt_name)
                return content
            else:
                logger.warning(
                    "Prompt file not found",
                    category=category,
                    prompt=prompt_name,
                    path=str(prompt_path),
                )
                return None
        except Exception as e:
            logger.error(
                "Failed to load prompt",
                category=category,
                prompt=prompt_name,
                error=str(e),
            )
            return None

    @classmethod
    def load_or_default(cls, category: str, prompt_name: str, default: str) -> str:
        """Load a prompt from file, or return default if not found.

        Args:
            category: Prompt category (RD, ED, LR, PW, etc.)
            prompt_name: Name of the prompt file (without .md extension)
            default: Default content to return if file not found.

        Returns:
            Prompt content or default.
        """
        content = cls.load(category, prompt_name)
        if content is None:
            logger.info(
                "Using default prompt",
                category=category,
                prompt=prompt_name,
            )
            return default
        return content

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the prompt cache."""
        cls._cache.clear()
        logger.info("Prompt cache cleared")

    @classmethod
    def reload(cls, category: str, prompt_name: str) -> Optional[str]:
        """Reload a prompt from file, bypassing cache.

        Args:
            category: Prompt category (RD, ED, LR, PW, etc.)
            prompt_name: Name of the prompt file (without .md extension)

        Returns:
            Prompt content or None if file not found.
        """
        return cls.load(category, prompt_name, use_cache=False)

    @classmethod
    def list_prompts(cls, category: str) -> list[str]:
        """List all available prompts in a category.

        Args:
            category: Prompt category (RD, ED, LR, PW, etc.)

        Returns:
            List of prompt names (without .md extension).
        """
        category_dir = PROMPTS_BASE_DIR / category
        if not category_dir.exists():
            return []

        return [f.stem for f in category_dir.glob("*.md")]

    @classmethod
    def list_categories(cls) -> list[str]:
        """List all available prompt categories.

        Returns:
            List of category names.
        """
        if not PROMPTS_BASE_DIR.exists():
            return []

        return [d.name for d in PROMPTS_BASE_DIR.iterdir() if d.is_dir()]


# Convenience functions for common prompts

def load_rd_system_prompt() -> Optional[str]:
    """Load Research Definition system prompt."""
    return PromptLoader.load("RD", "system_prompt")


def load_rd_initial_artifact() -> Optional[str]:
    """Load Research Definition initial artifact template."""
    return PromptLoader.load("RD", "initial_artifact")


def load_rd_summary_prompt() -> Optional[str]:
    """Load Research Definition summary prompt."""
    return PromptLoader.load("RD", "summary_prompt")


def load_rd_initial_prompt() -> Optional[str]:
    """Load Research Definition initial prompt template."""
    return PromptLoader.load("RD", "initial_prompt")


def load_rd_readiness_prompt() -> Optional[str]:
    """Load Research Definition readiness evaluation prompt."""
    return PromptLoader.load("RD", "readiness_prompt")


def load_ed_system_prompt() -> Optional[str]:
    """Load Experiment Design system prompt."""
    return PromptLoader.load("ED", "system_prompt")


def load_ed_initial_artifact() -> Optional[str]:
    """Load Experiment Design initial artifact template."""
    return PromptLoader.load("ED", "initial_artifact")


def load_pw_system_prompt() -> Optional[str]:
    """Load Paper Writing system prompt."""
    return PromptLoader.load("PW", "system_prompt")


def load_pw_initial_artifact() -> Optional[str]:
    """Load Paper Writing initial artifact template."""
    return PromptLoader.load("PW", "initial_artifact")


def load_lr_evaluation_prompt() -> Optional[str]:
    """Load Literature Review evaluation prompt."""
    return PromptLoader.load("LR", "evaluation_prompt")
