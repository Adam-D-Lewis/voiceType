"""Strip trailing ellipsis stage for pipeline execution.

This stage removes a trailing ellipsis ("...") that speech-to-text models
sometimes append when the speaker trails off. This is useful because the
user typically continues typing after the last word and does not want the
ellipsis left behind.
"""

import re
from typing import Optional

from loguru import logger
from pydantic import BaseModel

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


# Matches a trailing ellipsis: three-or-more ASCII dots or the unicode
# horizontal ellipsis (U+2026), optionally surrounded by whitespace at the
# end of the string. Both the ellipsis and surrounding whitespace are
# removed so the user can continue typing seamlessly.
_TRAILING_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*\Z")


class StripTrailingEllipsisConfig(BaseModel):
    """Configuration for StripTrailingEllipsis stage."""


@STAGE_REGISTRY.register
class StripTrailingEllipsis(PipelineStage[Optional[str], Optional[str]]):
    """Remove a trailing ellipsis from transcribed text.

    Speech-to-text models sometimes leave a trailing "..." when the speaker
    trails off or is cut off mid-sentence. This stage removes that trailing
    ellipsis (and surrounding whitespace) so the user can continue typing
    seamlessly afterwards.

    Matches both ASCII ellipsis ("...") and Unicode horizontal ellipsis
    ("…"). Only trailing ellipses are removed; ellipses mid-sentence are
    preserved.

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (transcribed text or None)
    - Output: Optional[str] (text with trailing ellipsis removed, or None)

    This stage takes no configuration. To enable it, add it to a pipeline:

        [stage_configs.StripTrailingEllipsis_default]
        stage_class = "StripTrailingEllipsis"
    """

    required_resources = set()

    def __init__(self, config: dict):
        """Initialize the strip trailing ellipsis stage.

        Args:
            config: Stage-specific configuration dict

        Raises:
            ValidationError: If config validation fails
        """
        self.cfg = StripTrailingEllipsisConfig(**config)

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Remove trailing ellipsis from input text.

        Args:
            input_data: Transcribed text or None
            context: PipelineContext (not used)

        Returns:
            Text with trailing ellipsis removed, or None if no input
        """
        if input_data is None:
            return None

        new_text, count = _TRAILING_ELLIPSIS_RE.subn("", input_data)
        if count == 0:
            return input_data

        logger.info("Stripped trailing ellipsis from transcribed text")
        return new_text
