"""
Tests for prompt construction.
"""

from etter.parser import GeoFilterParser


class MockLLM:
    """Minimal mock LLM for prompt-construction tests (no API calls)."""

    def with_structured_output(self, _schema, **kwargs):  # noqa: ARG002
        return self


def test_additional_instructions_in_prompt():
    """additional_instructions appear as a system message before the examples."""
    instructions = "Use French endonyms for Swiss locations."
    mock_llm = MockLLM()
    parser = GeoFilterParser(llm=mock_llm, additional_instructions=instructions)

    messages = parser.prompt.format_messages(query="near Lake Geneva")
    message_contents = [m.content for m in messages]

    assert any(instructions in content for content in message_contents), (
        "additional_instructions should be present in the prompt messages"
    )

    instructions_idx = next(i for i, c in enumerate(message_contents) if instructions in c)
    examples_idx = next((i for i, c in enumerate(message_contents) if "EXAMPLES" in c), None)
    if examples_idx is not None:
        assert instructions_idx < examples_idx, "additional_instructions should appear before the few-shot examples"
