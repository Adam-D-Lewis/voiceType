"""LLM Agent stage for pipeline execution.

This stage processes text through an LLM agent using LiteLLM.
Supports both local (Ollama) and remote (OpenAI, Anthropic, etc.) providers.
"""

from typing import Optional

from loguru import logger

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


@STAGE_REGISTRY.register
class LLMAgent(PipelineStage[Optional[str], Optional[str]]):
    """Process text through an LLM agent.

    Uses LiteLLM to send text to an LLM for processing. Supports any
    provider that LiteLLM supports (OpenAI, Anthropic, Gemini, Ollama, etc.).

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (text to process or None)
    - Output: Optional[str] (LLM-processed text or None)

    Config parameters:
    - model: Model string (e.g., "gpt-4", "claude-3-5-sonnet-20241022", "ollama/llama3.2")
    - system_prompt: Optional instructions for the LLM (default: Jarvis assistant prompt)
    - trigger_keywords: List of keywords that must be present to invoke LLM (case-insensitive).
                       If not configured or empty, LLM will NOT be invoked and original text is returned.
    - temperature: Optional float controlling randomness (0.0-2.0, default: provider default)
    - max_tokens: Optional int limiting response length
    - timeout: Optional int for request timeout in seconds (default: 30)
    - fallback_on_error: If True, returns original input on error; if False, returns None (default: True)
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict):
        """Initialize the LLM agent stage.

        Args:
            config: Stage-specific configuration
        """
        self.config = config

        # Required parameters
        if "model" not in config:
            raise ValueError("LLMAgent stage requires 'model' in config")

        self.model = config["model"]
        self.system_prompt = config.get(
            "system_prompt",
            """You are Jarvis.  You are a part of a speech to text pipeline where a user speaks, the audio is transcribed, and eventually typed out on the keyboard. The user has left a message for you to modify the text that he said in some way before it is typed.  Modify the text as requested and output the modified text.  Output nothing else b/c exactly what you output is what will be typed.  Make sure to remove references to yourself from the output.  The instructions for you should not be part of the output.

        e.g.
        User: Hello, Administrator. Okay, uh, actually, Jarvis, make this sound like, um, a cockney accent and spell it as if I had a heavy cockney accent.
        Output: 'Ello Admin.'""",
        )

        # Optional parameters
        self.trigger_keywords = config.get("trigger_keywords", [])
        self.temperature = config.get("temperature")
        self.max_tokens = config.get("max_tokens")
        self.timeout = config.get("timeout", 30)
        self.fallback_on_error = config.get("fallback_on_error", True)

        # Warn if trigger keywords are not configured
        if not self.trigger_keywords:
            logger.warning(
                "LLMAgent configured without trigger_keywords. "
                "The LLM will not be invoked. Please configure trigger_keywords "
                "to enable LLM processing (e.g., trigger_keywords = ['jarvis', 'hey assistant'])"
            )

        logger.debug(
            f"Initialized LLM agent with model={self.model}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens}"
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

        # Check for trigger keywords - return unchanged if not configured or not found
        if not self.trigger_keywords:
            logger.debug("No trigger_keywords configured, skipping LLM processing")
            return input_data

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

        logger.debug(f"Trigger keyword found in input, proceeding with LLM processing")

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
