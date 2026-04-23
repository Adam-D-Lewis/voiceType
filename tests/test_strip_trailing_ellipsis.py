"""Unit tests for StripTrailingEllipsis pipeline stage."""

import threading

from voicetype.pipeline import PipelineContext
from voicetype.pipeline.stages.strip_trailing_ellipsis import StripTrailingEllipsis


class MockIconController:
    def set_icon(self, state: str, duration: float = None):
        pass


def create_test_context():
    return PipelineContext(
        config={},
        icon_controller=MockIconController(),
        trigger_event=None,
        cancel_requested=threading.Event(),
    )


class TestStripTrailingEllipsis:
    def test_strips_ascii_trailing_ellipsis(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world...", create_test_context())
        assert result == "hello world"

    def test_strips_unicode_trailing_ellipsis(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world…", create_test_context())
        assert result == "hello world"

    def test_strips_ellipsis_with_surrounding_whitespace(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world ... ", create_test_context())
        assert result == "hello world"

    def test_strips_more_than_three_dots(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world....", create_test_context())
        assert result == "hello world"

    def test_preserves_midsentence_ellipsis(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("well... I think so", create_test_context())
        assert result == "well... I think so"

    def test_only_strips_trailing_when_midsentence_also_present(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("well... I think so...", create_test_context())
        assert result == "well... I think so"

    def test_does_not_strip_single_period(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world.", create_test_context())
        assert result == "hello world."

    def test_does_not_strip_two_dots(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world..", create_test_context())
        assert result == "hello world.."

    def test_passes_through_empty_string(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("", create_test_context())
        assert result == ""

    def test_passes_through_none(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute(None, create_test_context())
        assert result is None

    def test_passes_through_text_without_ellipsis(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("hello world", create_test_context())
        assert result == "hello world"

    def test_handles_ellipsis_only_string(self):
        stage = StripTrailingEllipsis({})
        result = stage.execute("...", create_test_context())
        assert result == ""
