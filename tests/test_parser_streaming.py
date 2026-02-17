"""
Tests for streaming parser functionality.
"""

import pytest

from geollm.exceptions import ParsingError
from geollm.models import BufferConfig, ConfidenceScore, GeoQuery, ReferenceLocation, SpatialRelation
from geollm.parser import GeoFilterParser

# Configure pytest to use anyio for async tests
pytestmark = pytest.mark.anyio


class MockLLM:
    """Mock LLM for testing without API calls."""

    def __init__(self, return_valid=True):
        self.return_valid = return_valid

    def with_structured_output(self, _schema, **kwargs):  # noqa: ARG002
        """Mock with_structured_output method."""
        self.include_raw = kwargs.get("include_raw", False)
        return self

    def invoke(self, _messages):  # noqa: ARG002
        """Mock invoke method."""
        if not self.return_valid:
            return {"parsed": None, "raw": "Invalid response", "parsing_error": Exception("Parse failed")}

        # Return a valid GeoQuery object
        geo_query = GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(
                relation="near",
                category="buffer",
                explicit_distance=None,
            ),
            reference_location=ReferenceLocation(
                name="Lake Geneva",
                type="lake",
                type_confidence=0.9,
            ),
            buffer_config=BufferConfig(
                distance_m=5000,
                buffer_from="boundary",
                ring_only=False,
                inferred=True,
            ),
            confidence_breakdown=ConfidenceScore(
                overall=0.92,
                location_confidence=0.95,
                relation_confidence=0.90,
                reasoning="Clear location and spatial relation identified",
            ),
            original_query="near Lake Geneva",
        )

        if self.include_raw:
            return {"parsed": geo_query}
        return geo_query


async def test_parse_stream_success():
    """Test successful streaming with all event types."""
    mock_llm = MockLLM(return_valid=True)
    parser = GeoFilterParser(llm=mock_llm)

    query = "near Lake Geneva"
    events = []

    async for event in parser.parse_stream(query):
        events.append(event)

    event_types = [e["type"] for e in events]

    assert "start" in event_types, "Should emit 'start' event"
    assert "reasoning" in event_types, "Should emit 'reasoning' events"
    assert "data-response" in event_types, "Should emit 'data-response' event"
    assert "finish" in event_types, "Should emit 'finish' event"

    assert event_types[0] == "start", "First event should be 'start'"
    assert event_types[-1] == "finish", "Last event should be 'finish'"

    data_events = [e for e in events if e["type"] == "data-response"]
    assert len(data_events) == 1, "Should have exactly one data-response event"

    data = data_events[0]["content"]
    assert data["reference_location"]["name"] == "Lake Geneva"
    assert data["spatial_relation"]["relation"] == "near"
    assert data["spatial_relation"]["category"] == "buffer"


async def test_parse_stream_reasoning_events():
    """Test that reasoning events contain expected processing steps."""
    mock_llm = MockLLM(return_valid=True)
    parser = GeoFilterParser(llm=mock_llm)

    query = "near Lake Geneva"
    reasoning_events = []

    async for event in parser.parse_stream(query):
        if event["type"] == "reasoning":
            reasoning_events.append(event["content"])

    assert any("Preparing query" in r for r in reasoning_events), "Should have query preparation step"
    assert any("Analyzing spatial" in r for r in reasoning_events), "Should have analysis step"
    assert any("Parsing LLM response" in r for r in reasoning_events), "Should have parsing step"
    assert any("Validating" in r for r in reasoning_events), "Should have validation step"
    assert any("completed successfully" in r for r in reasoning_events), "Should have completion step"


async def test_parse_stream_error_handling():
    """Test that errors are properly emitted as error events."""
    mock_llm = MockLLM(return_valid=False)
    parser = GeoFilterParser(llm=mock_llm)

    query = "near Lake Geneva"
    events = []

    with pytest.raises(ParsingError):
        async for event in parser.parse_stream(query):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "error" in event_types, "Should emit error event on failure"

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) > 0, "Should have at least one error event"
    assert "content" in error_events[0], "Error event should have content"


async def test_parse_stream_llm_reasoning():
    """Test that LLM's reasoning is included in stream."""
    mock_llm = MockLLM(return_valid=True)
    parser = GeoFilterParser(llm=mock_llm)

    query = "near Lake Geneva"
    reasoning_contents = []

    async for event in parser.parse_stream(query):
        if event["type"] == "reasoning":
            reasoning_contents.append(event["content"])

    # The mock LLM returns a reasoning in confidence_breakdown
    # It should be included in the stream
    assert any("LLM reasoning:" in r for r in reasoning_contents), "Should include LLM's own reasoning"


async def test_parse_stream_event_order():
    """Test that events are emitted in the correct order."""
    mock_llm = MockLLM(return_valid=True)
    parser = GeoFilterParser(llm=mock_llm)

    query = "near Lake Geneva"
    events = []

    async for event in parser.parse_stream(query):
        events.append(event)

    event_types = [e["type"] for e in events]

    start_idx = event_types.index("start")
    data_idx = event_types.index("data-response")
    finish_idx = event_types.index("finish")

    assert start_idx < data_idx < finish_idx, "Events should be in order: start < data-response < finish"

    for i, event_type in enumerate(event_types):
        if event_type == "reasoning":
            assert start_idx < i < finish_idx, "Reasoning events should be between start and finish"
