"""Correct typos stage for pipeline execution.

This stage corrects common typos or speech-to-text errors by replacing
configured typos with their correct spellings.
"""

import re
from typing import Optional

from loguru import logger

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


@STAGE_REGISTRY.register
class CorrectTypos(PipelineStage[Optional[str], Optional[str]]):
    """Replace configured typos with correct spellings.

    This stage allows you to fix common speech-to-text errors, correct
    capitalization, or standardize terminology before text is typed.

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (transcribed text or None)
    - Output: Optional[str] (corrected text or None)

    Config parameters:
    - case_sensitive: Default case sensitivity for matching (default: false)
    - whole_word_only: Default whole-word matching (default: true)
    - corrections: List of correction rules. Each rule is a list with:
      [typo, correction] or [typo, correction, "overrides"]
      where overrides can be "case_sensitive=true" or "whole_word_only=false"
      or both separated by comma: "case_sensitive=true,whole_word_only=false"

    Example config:
        [correct_typos_stage]
        case_sensitive = false
        whole_word_only = true
        corrections = [
            ["machinelearning", "machine learning"],
            ["air quotes", "error codes"],
            ["Python", "python", "case_sensitive=true"],
            ["machine", "machine", "whole_word_only=false"],
        ]
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict):
        """Initialize the correct typos stage.

        Args:
            config: Stage-specific configuration
        """
        self.config = config

        # Default settings
        self.case_sensitive = config.get("case_sensitive", False)
        self.whole_word_only = config.get("whole_word_only", True)

        # Parse and compile correction patterns
        self._patterns = self._parse_and_compile_corrections()

    def _parse_correction_entry(self, entry: list) -> tuple:
        """Parse a correction entry from config.

        Args:
            entry: List with [typo, correction] or [typo, correction, overrides]

        Returns:
            Tuple of (typo, correction, case_sensitive, whole_word_only)
        """
        typo = entry[0]
        correction = entry[1]

        # Start with defaults
        case_sensitive = self.case_sensitive
        whole_word_only = self.whole_word_only

        # Parse overrides if present
        if len(entry) > 2:
            overrides_str = entry[2]
            for pair in overrides_str.split(","):
                pair = pair.strip()
                if "=" not in pair:
                    logger.warning(
                        f"Invalid override format '{pair}' for typo '{typo}'. "
                        f"Expected 'key=value'. Skipping."
                    )
                    continue

                key, value = pair.split("=", 1)
                key = key.strip()
                value = value.strip().lower()

                if key == "case_sensitive":
                    case_sensitive = value == "true"
                elif key == "whole_word_only":
                    whole_word_only = value == "true"
                else:
                    logger.warning(
                        f"Unknown override option '{key}' for typo '{typo}'. Skipping."
                    )

        return typo, correction, case_sensitive, whole_word_only

    def _compile_pattern(
        self, typo: str, case_sensitive: bool, whole_word_only: bool
    ) -> re.Pattern:
        """Compile a regex pattern for a typo.

        Args:
            typo: The typo text to match
            case_sensitive: Whether matching is case sensitive
            whole_word_only: Whether to match only whole words

        Returns:
            Compiled regex pattern
        """
        # Escape special regex characters
        escaped_typo = re.escape(typo)

        # Add word boundaries if needed
        if whole_word_only:
            pattern_str = rf"\b{escaped_typo}\b"
        else:
            pattern_str = escaped_typo

        # Compile with appropriate flags
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.compile(pattern_str, flags)

    def _parse_and_compile_corrections(self) -> list:
        """Parse corrections from config and compile regex patterns.

        Returns:
            List of tuples: (compiled_pattern, replacement_text, original_typo)
        """
        patterns = []

        # Get corrections from config
        corrections_list = self.config.get("corrections", [])

        for entry in corrections_list:
            if not isinstance(entry, list) or len(entry) < 2:
                logger.warning(
                    f"Invalid correction entry format: {entry}. "
                    f"Expected [typo, correction] or [typo, correction, overrides]. "
                    f"Skipping."
                )
                continue

            typo, correction, case_sensitive, whole_word_only = (
                self._parse_correction_entry(entry)
            )

            pattern = self._compile_pattern(typo, case_sensitive, whole_word_only)
            patterns.append((pattern, correction, typo))

        logger.debug(f"Loaded {len(patterns)} typo correction(s)")
        return patterns

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Apply typo corrections to input text.

        Args:
            input_data: Transcribed text or None
            context: PipelineContext (not used)

        Returns:
            Corrected text or None if no input
        """
        if input_data is None:
            logger.debug("No input to correct")
            return None

        if not self._patterns:
            logger.debug("No corrections configured, passing through unchanged")
            return input_data

        result = input_data
        corrections_made = []

        # Apply each correction pattern
        for pattern, replacement, original_typo in self._patterns:
            matches = pattern.findall(result)
            if matches:
                result = pattern.sub(replacement, result)
                # Log the first match found
                corrections_made.append(f"'{matches[0]}' → '{replacement}'")

        if corrections_made:
            logger.info(
                f"Applied {len(corrections_made)} correction(s): {', '.join(corrections_made)}"
            )
        else:
            logger.debug("No corrections needed")

        return result
