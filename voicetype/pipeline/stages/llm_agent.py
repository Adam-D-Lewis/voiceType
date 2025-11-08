"""LLM Agent stage for pipeline execution.

This stage processes text through an LLM agent using Pydantic AI.
Supports both local (Ollama) and remote (OpenAI, Anthropic, etc.) providers.
"""

from typing import Optional

from loguru import logger
from pydantic_ai import Agent

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


@STAGE_REGISTRY.register
class LLMAgent(PipelineStage[Optional[str], Optional[str]]):
    """Process text through an LLM agent.

    Uses Pydantic AI to send text to an LLM for processing. Supports any
    provider that Pydantic AI supports (OpenAI, Anthropic, Gemini, Ollama, etc.).

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (text to process or None)
    - Output: Optional[str] (LLM-processed text or None)

    Config parameters:
    - provider: Model string in format "provider:model" (e.g., "openai:gpt-4", "ollama:llama3.2")
    - system_prompt: Instructions for the LLM on how to process the text
    - trigger_keywords: Optional list of keywords that must be present to invoke LLM (case-insensitive)
    - temperature: Optional float controlling randomness (0.0-2.0, default: provider default)
    - max_tokens: Optional int limiting response length
    - timeout: Optional int for request timeout in seconds (default: 30)
    - fallback_on_error: If True, returns original input on error; if False, returns None (default: True)
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict, metadata: dict):
        """Initialize the LLM agent stage.

        Args:
            config: Stage-specific configuration
            metadata: Shared pipeline metadata (unused for this stage)
        """
        self.config = config

        # Required parameters
        if "provider" not in config:
            raise ValueError("LLMAgent stage requires 'provider' in config")
        if "system_prompt" not in config:
            raise ValueError("LLMAgent stage requires 'system_prompt' in config")

        self.provider = config["provider"]
        self.system_prompt = config["system_prompt"]

        # Optional parameters
        self.trigger_keywords = config.get("trigger_keywords", [])
        self.temperature = config.get("temperature")
        self.max_tokens = config.get("max_tokens")
        self.timeout = config.get("timeout", 30)
        self.fallback_on_error = config.get("fallback_on_error", True)

        # Create the agent
        try:
            self.agent = Agent(
                model=self.provider,
                system_prompt=self.system_prompt,
            )
            logger.debug(
                f"Initialized LLM agent with provider={self.provider}, "
                f"temperature={self.temperature}, max_tokens={self.max_tokens}"
            )
        except Exception as e:
            raise ValueError(
                f"Failed to initialize LLM agent with provider '{self.provider}': {e}"
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

        # Check for trigger keywords if configured
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
                f"Trigger keyword found in input, proceeding with LLM processing"
            )

        # Update icon to processing state
        context.icon_controller.set_icon("processing")
        logger.debug(f"Processing text through LLM: {input_data[:100]}...")

        try:
            # Build run kwargs
            run_kwargs = {}
            if self.temperature is not None:
                run_kwargs["model_settings"] = {"temperature": self.temperature}
            if self.max_tokens is not None:
                if "model_settings" not in run_kwargs:
                    run_kwargs["model_settings"] = {}
                run_kwargs["model_settings"]["max_tokens"] = self.max_tokens

            # Run the agent synchronously
            result = self.agent.run_sync(input_data, **run_kwargs)

            # Extract the text from the result
            output_text = result.data

            if output_text:
                logger.info(f"LLM processing complete: {output_text[:100]}...")
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
