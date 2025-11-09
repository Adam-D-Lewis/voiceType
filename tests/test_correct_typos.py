"""Unit tests for CorrectTypos pipeline stage."""

import pytest

from voicetype.pipeline import PipelineContext
from voicetype.pipeline.stages.correct_typos import CorrectTypos


class MockIconController:
    """Mock icon controller for testing."""

    def set_icon(self, state: str, duration: float = None):
        pass


def create_test_context():
    """Create a minimal PipelineContext for testing."""
    import threading

    return PipelineContext(
        config={},
        icon_controller=MockIconController(),
        trigger_event=None,
        cancel_requested=threading.Event(),
        metadata={},
    )


class TestCorrectTypos:
    """Tests for CorrectTypos stage."""

    def test_simple_correction(self):
        """Test basic typo correction."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["machinelearning", "machine learning"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("I love machinelearning", context)
        assert result == "I love machine learning"

    def test_multiple_corrections(self):
        """Test multiple typo corrections in one text."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["machinelearning", "machine learning"],
                ["air quotes", "error codes"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("I love machinelearning and air quotes", context)
        assert result == "I love machine learning and error codes"

    def test_case_insensitive_by_default(self):
        """Test that corrections are case-insensitive by default."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["python", "Python"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("I love python and PYTHON", context)
        assert result == "I love Python and Python"

    def test_case_sensitive_override(self):
        """Test case-sensitive override for specific corrections."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["python", "Python", "case_sensitive=true"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("I love python and PYTHON", context)
        # Only lowercase "python" should be replaced
        assert result == "I love Python and PYTHON"

    def test_whole_word_only_default(self):
        """Test that whole_word_only=true only matches whole words."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["test", "exam"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("This is a test and testing", context)
        # Should only replace "test", not "testing"
        assert result == "This is a exam and testing"

    def test_substring_matching_override(self):
        """Test substring matching with whole_word_only=false."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["test", "exam", "whole_word_only=false"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("This is a test and testing", context)
        # Should replace both "test" and "test" in "testing"
        assert result == "This is a exam and examing"  # typos: ignore

    def test_multiple_overrides(self):
        """Test multiple overrides in one correction."""
        config = {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [
                ["Test", "exam", "case_sensitive=true,whole_word_only=false"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        # Case-sensitive and substring matching
        result = stage.execute("Test testing test", context)
        # Should only replace "Test" with capital T (case-sensitive)
        # "testing" has lowercase 't' so won't match
        assert result == "exam testing test"

    def test_none_input(self):
        """Test that None input returns None."""
        config = {
            "corrections": [
                ["test", "exam"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute(None, context)
        assert result is None

    def test_no_corrections_configured(self):
        """Test that text passes through unchanged when no corrections."""
        config = {"corrections": []}
        stage = CorrectTypos(config)
        context = create_test_context()

        input_text = "This is some text"
        result = stage.execute(input_text, context)
        assert result == input_text

    def test_no_matches(self):
        """Test that text passes through unchanged when no matches."""
        config = {
            "corrections": [
                ["xyz", "abc"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        input_text = "This is some text"
        result = stage.execute(input_text, context)
        assert result == input_text

    def test_multi_word_correction(self):
        """Test correction of multi-word phrases."""
        config = {
            "corrections": [
                ["air quotes", "error codes"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("I hate air quotes in code", context)
        assert result == "I hate error codes in code"

    def test_regex_special_characters_escaped(self):
        """Test that regex special characters in typos are escaped."""
        config = {
            "corrections": [
                ["test.", "exam", "whole_word_only=false"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        # Should only match literal "test.", not "testa" (where . is wildcard)
        # Need whole_word_only=false since "." is not a word character
        result = stage.execute("test. testa", context)
        assert result == "exam testa"

    def test_invalid_correction_entry_skipped(self):
        """Test that invalid correction entries are skipped gracefully."""
        config = {
            "corrections": [
                ["valid", "correction"],
                ["invalid"],  # Missing correction part
                ["another", "valid"],
            ],
        }
        stage = CorrectTypos(config)
        context = create_test_context()

        result = stage.execute("valid invalid another", context)
        assert result == "correction invalid valid"
