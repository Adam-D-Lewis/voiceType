"""LLM Agent stage for pipeline execution.

This stage processes text through an LLM agent using LiteLLM.
Supports both local (Ollama) and remote (OpenAI, Anthropic, etc.) providers.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage

DEFAULT_JARVIS_PROMPT = """You are Jarvis, an assistant in a speech-to-text pipeline. The user speaks, their audio is transcribed, and your output will be typed directly into their active application.

Your task: Modify the transcribed text according to the user's instructions, then output ONLY the modified text. Your entire response will be typed verbatim, so include nothing extra—no explanations, acknowledgments, or meta-commentary.

Guidelines:
- Remove all references to yourself (Jarvis, assistant, etc.) from the output
- Remove the user's instructions to you from the output
- Clean up speech artifacts (um, uh, like, you know) unless they're part of the requested style
- If no clear modification is requested, clean up the text and return it naturally
- Preserve the user's intended meaning and tone

Examples:

User: Hey Jarvis, make this formal: gonna send the report tomorrow probably
Output: I will send the report tomorrow.

User: Hello, Administrator. Okay, uh, actually, Jarvis, make this sound like a cockney accent.
Output: 'Ello, Admin.

User: Jarvis, translate to Spanish: The meeting is at three o'clock
Output: La reunión es a las tres en punto.

User: Um, I think we should, uh, schedule the meeting for next Tuesday, Jarvis just clean this up
Output: I think we should schedule the meeting for next Tuesday.

Counter Examples (Wrong!):
User: Hello, Administrator. Okay, uh, actually, Jarvis, make this sound like a cockney accent.
Output: That would be "'Ello Admin."
Why?: It's wrong b/c the output should not contain anything except for the transformed version of the original text, e.g. 'Ello Admin.
"""


class LLMAgentConfig(BaseModel):
    """Configuration for LLMAgent stage."""

    model: str = Field(
        description="Model string (e.g., 'gpt-4', 'claude-3-5-sonnet-20241022', 'ollama/llama3.2')",
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Custom API base URL (e.g., 'http://myserver:11434' for remote Ollama)",
    )
    system_prompt: str = Field(
        default=DEFAULT_JARVIS_PROMPT,
        description="Instructions for the LLM",
    )
    trigger_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords that must be present to invoke LLM (case-insensitive)",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Controls randomness (0.0-2.0)",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum response length in tokens",
    )
    timeout: int = Field(
        default=30,
        gt=0,
        description="Request timeout in seconds",
    )
    fallback_on_error: bool = Field(
        default=True,
        description="Return original input on error (True) or None (False)",
    )


@STAGE_REGISTRY.register
class LLMAgent(PipelineStage[Optional[str], Optional[str]]):
    """Process text through an LLM agent.

    Uses LiteLLM to send text to an LLM for processing. Supports any
    provider that LiteLLM supports (OpenAI, Anthropic, Gemini, Ollama, etc.).  See https://docs.litellm.ai/docs/providers to determine appropriate values for specific providers.

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (text to process or None)
    - Output: Optional[str] (LLM-processed text or None)

    Config parameters:
    - model: Model string (e.g., "gpt-4", "claude-3-5-sonnet-20241022", "ollama/llama3.2")
    - system_prompt: Optional instructions for the LLM (default: Jarvis assistant prompt)
    - trigger_keywords: List of keywords that must be present to invoke LLM (case-insensitive).
                       If empty, LLM is always invoked.
    - temperature: Optional float controlling randomness (0.0-2.0, default: provider default)
    - max_tokens: Optional int limiting response length
    - timeout: Optional int for request timeout in seconds (default: 30)
    - fallback_on_error: If True, returns original input on error; if False, returns None (default: True)
    """

    required_resources = set()  # No exclusive resources needed

    # Class-level state for capturing LLM interactions
    _last_interaction: Optional[dict] = None
    _interaction_lock = threading.Lock()

    def __init__(self, config: dict):
        """Initialize the LLM agent stage.

        Args:
            config: Stage-specific configuration dict

        Raises:
            ValidationError: If config validation fails (e.g., model not provided)
        """
        # Parse and validate config
        self.cfg = LLMAgentConfig(**config)

        # Keep attributes accessible for compatibility
        self.model = self.cfg.model
        self.api_base = self.cfg.api_base
        self.system_prompt = self.cfg.system_prompt
        self.trigger_keywords = self.cfg.trigger_keywords
        self.temperature = self.cfg.temperature
        self.max_tokens = self.cfg.max_tokens
        self.timeout = self.cfg.timeout
        self.fallback_on_error = self.cfg.fallback_on_error

        if not self.trigger_keywords:
            logger.info(
                "LLMAgent configured without trigger_keywords — LLM will always be invoked."
            )

        logger.debug(
            f"Initialized LLM agent with model={self.model}, "
            f"api_base={self.api_base}, temperature={self.temperature}, max_tokens={self.max_tokens}"
        )

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Execute LLM processing.

        Args:
            input_data: Text to process or None
            context: PipelineContext with config

        Returns:
            Processed text or None if no input or error
        """
        if input_data is None:
            logger.info("No text to process (input is None)")
            return None

        # Check for trigger keywords - if configured, only invoke LLM when a keyword is found
        if self.trigger_keywords:
            input_lower = input_data.lower()
            keyword_found = any(
                keyword.lower() in input_lower for keyword in self.trigger_keywords
            )
            if not keyword_found:
                logger.debug(
                    f"No trigger keywords {self.trigger_keywords} found in input, "
                    "skipping LLM processing"
                )
                return input_data
            logger.debug(
                "Trigger keyword found in input, proceeding with LLM processing"
            )
        else:
            logger.debug("No trigger_keywords configured, always invoking LLM")

        # Update icon to processing state
        context.icon_controller.set_icon("processing")
        logger.debug(f"Processing text through LLM: {input_data[:100]}...")

        try:
            import litellm

            # Build completion kwargs
            completion_kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": input_data},
                ],
                "timeout": self.timeout,
            }

            if self.api_base is not None:
                completion_kwargs["api_base"] = self.api_base
            if self.temperature is not None:
                completion_kwargs["temperature"] = self.temperature
            if self.max_tokens is not None:
                completion_kwargs["max_tokens"] = self.max_tokens

            # Call LiteLLM completion
            response = litellm.completion(**completion_kwargs)

            # Extract the text from the response
            output_text = response.choices[0].message.content

            if output_text:
                logger.info(f"LLM processing complete: {output_text[:100]}...")
                with LLMAgent._interaction_lock:
                    LLMAgent._last_interaction = {
                        "input": input_data,
                        "output": output_text,
                        "model": self.model,
                        "system_prompt": self.system_prompt,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
            else:
                logger.warning("LLM returned empty response")
                if self.fallback_on_error:
                    logger.info("Using original input as fallback")
                    output_text = input_data

            return output_text

        except Exception as e:
            logger.error(f"Error during LLM processing: {e}")
            if self.fallback_on_error:
                logger.info("Falling back to original input due to error")
                return input_data
            else:
                logger.info("Returning None due to error (fallback disabled)")
                return None

    @classmethod
    def get_menu_items(cls) -> List[Tuple[str, callable]]:
        """Return menu items contributed by this stage for the system tray."""
        with cls._interaction_lock:
            if cls._last_interaction is not None:
                return [("Capture Wrong LLM Output", cls._capture_wrong_output)]
        return []

    @classmethod
    def _capture_wrong_output(cls) -> None:
        """Save the last LLM interaction as an incorrect example."""
        from voicetype.utils import get_app_data_dir

        with cls._interaction_lock:
            interaction = cls._last_interaction
            if interaction is None:
                logger.warning("No recent LLM interaction to capture")
                return
            cls._last_interaction = None

        output_path = Path(get_app_data_dir()) / "wrong_llm_outputs.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {"label": "incorrect", **interaction}
        with open(output_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        logger.info(f"Captured wrong LLM output to {output_path}")
