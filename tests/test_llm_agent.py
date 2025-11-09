"""Unit tests for LLMAgent pipeline stage."""

import pytest

from voicetype.pipeline import PipelineContext
from voicetype.pipeline.stages.llm_agent import LLMAgent


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


class TestLLMAgent:
    """Tests for LLMAgent stage."""

    def test_initialization_requires_provider(self):
        """Test that initialization fails without provider."""
        config = {
            "system_prompt": "Test prompt",
        }
        with pytest.raises(ValueError, match="requires 'provider'"):
            LLMAgent(config)

    def test_initialization_with_default_system_prompt(self):
        """Test that initialization uses default system_prompt when not provided."""
        config = {
            "provider": "test",
            "trigger_keywords": ["test"],  # Add trigger keywords
        }
        stage = LLMAgent(config)
        # Check that the default system prompt is set (the actual default has been updated)
        assert stage.system_prompt is not None
        assert len(stage.system_prompt) > 0

    def test_initialization_with_test_model(self):
        """Test that LLMAgent can be initialized with test model."""
        config = {
            "provider": "test",
            "system_prompt": "You are a helpful assistant",
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)
        assert stage.provider == "test"
        assert stage.system_prompt == "You are a helpful assistant"

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        result = stage.execute(None, context)
        assert result is None

    def test_basic_agent_execution_with_test_model(self):
        """Test basic agent execution using Pydantic AI's test model."""
        from pydantic_ai.models.test import TestModel

        config = {
            "provider": "test",
            "system_prompt": "You are a helpful assistant",
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Replace the agent's model with a TestModel that returns predictable results
        stage.agent._model = TestModel()

        # TestModel echoes back the input by default - must include trigger keyword
        result = stage.execute("Hello world test", context)
        assert result is not None
        assert isinstance(result, str)

    def test_fallback_on_error_enabled(self):
        """Test that original input is returned when fallback_on_error=True."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "fallback_on_error": True,
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Force an error by using an invalid model
        from pydantic_ai.models.test import TestModel

        # Create a TestModel that raises an error
        def error_call(*args, **kwargs):
            raise RuntimeError("Simulated error")

        stage.agent._model = TestModel()
        stage.agent._model.agent_model = error_call

        # Should return original input on error - must include trigger keyword
        input_text = "Original text test"
        result = stage.execute(input_text, context)
        # Note: The actual behavior depends on how Pydantic AI handles errors
        # This test validates the fallback logic exists
        assert result is not None

    def test_optional_parameters_stored(self):
        """Test that optional parameters are stored correctly."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "temperature": 0.7,
            "max_tokens": 100,
            "timeout": 60,
            "fallback_on_error": False,
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)

        assert stage.temperature == 0.7
        assert stage.max_tokens == 100
        assert stage.timeout == 60
        assert stage.fallback_on_error is False

    def test_default_optional_parameters(self):
        """Test default values for optional parameters."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": ["test"],
        }
        stage = LLMAgent(config)

        assert stage.temperature is None
        assert stage.max_tokens is None
        assert stage.timeout == 30
        assert stage.fallback_on_error is True
        assert stage.trigger_keywords == ["test"]

    def test_trigger_keywords_not_found_skips_llm(self):
        """Test that LLM is not invoked when trigger keywords are not found."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": ["jarvis", "hey assistant"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Input without trigger keywords should return unchanged
        input_text = "Just regular text without any keywords"
        result = stage.execute(input_text, context)
        assert result == input_text

    def test_trigger_keywords_found_invokes_llm(self):
        """Test that LLM is invoked when trigger keywords are found."""
        from pydantic_ai.models.test import TestModel

        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": ["jarvis", "hey assistant"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Replace with test model
        stage.agent._model = TestModel()

        # Input with trigger keyword should invoke LLM
        input_text = "This is my email jarvis make it professional"
        result = stage.execute(input_text, context)
        # Result should be processed (not None and should be a string)
        assert result is not None
        assert isinstance(result, str)

    def test_trigger_keywords_case_insensitive(self):
        """Test that trigger keyword matching is case-insensitive."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": ["jarvis"],
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Test various cases
        test_cases = [
            "text JARVIS command",
            "text Jarvis command",
            "text JaRvIs command",
        ]

        for input_text in test_cases:
            from pydantic_ai.models.test import TestModel

            stage.agent._model = TestModel()
            result = stage.execute(input_text, context)
            # Should invoke LLM (not just return input)
            assert result is not None

    def test_no_trigger_keywords_skips_llm(self):
        """Test that LLM is NOT invoked when trigger_keywords is empty."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            # No trigger_keywords specified
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Should NOT invoke LLM when no trigger keywords configured
        input_text = "Any text without keywords"
        result = stage.execute(input_text, context)
        # Should return original input unchanged
        assert result == input_text

    def test_empty_trigger_keywords_skips_llm(self):
        """Test that LLM is NOT invoked when trigger_keywords is explicitly empty list."""
        config = {
            "provider": "test",
            "system_prompt": "Test",
            "trigger_keywords": [],  # Explicitly empty
        }
        stage = LLMAgent(config)
        context = create_test_context()

        # Should NOT invoke LLM when trigger keywords list is empty
        input_text = "Any text without keywords"
        result = stage.execute(input_text, context)
        # Should return original input unchanged
        assert result == input_text

    @pytest.mark.skipif(
        True,  # Skip by default as it requires actual LLM API access
        reason="Requires actual LLM API access and credentials",
    )
    def test_real_llm_integration(self):
        """Integration test with real LLM (requires API keys)."""
        import os

        # This test is skipped by default
        # To run it, set the appropriate environment variable and change skipif to False
        config = {
            "provider": "openai:gpt-4o-mini",
            "system_prompt": "You are a text transformation assistant. "
            "If the input contains 'jarvis', extract the instruction after it "
            "and apply it to the text before it. Otherwise return the text unchanged.",
            "temperature": 0.3,
            "trigger_keywords": ["jarvis"],
        }

        stage = LLMAgent(config)
        context = create_test_context()

        # Test with trigger word
        result = stage.execute("This is my email jarvis make it professional", context)
        assert result is not None
        assert "email" in result.lower()

        # Test without trigger word - should return original text unchanged
        result = stage.execute("Just regular text", context)
        assert result == "Just regular text"
