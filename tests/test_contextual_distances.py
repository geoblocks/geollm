"""
Tests for context-dependent distance handling.

These tests verify that etter correctly recognizes and converts contextual
distance expressions like "walking distance" and "biking distance" into
explicit buffer distances.
"""

import os

import pytest
from langchain.chat_models import init_chat_model

from etter import GeoFilterParser


@pytest.fixture
def parser():
    """Create parser with OpenAI LLM for testing."""
    # Skip tests if no API key is available
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    llm = init_chat_model(model="gpt-4o", model_provider="openai", temperature=0)
    return GeoFilterParser(llm=llm)


def test_walking_distance(parser):
    """Test that 'walking distance' is converted to 1km."""
    result = parser.parse("Walking distance from Zurich main railway station")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    assert result.spatial_relation.explicit_distance == 1000
    assert result.buffer_config.distance_m == 1000
    assert result.buffer_config.inferred is False
    assert result.reference_location.name == "Zurich main railway station"


def test_biking_distance(parser):
    """Test that 'biking distance' is converted to 5km."""
    result = parser.parse("Biking distance from Lake Geneva")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    assert result.spatial_relation.explicit_distance == 5000
    assert result.buffer_config.distance_m == 5000
    assert result.buffer_config.inferred is False
    assert result.reference_location.name == "Lake Geneva"


def test_cycling_distance_synonym(parser):
    """Test that 'cycling distance' (synonym) is also converted to 5km."""
    result = parser.parse("Cycling distance from Bern")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    assert result.spatial_relation.explicit_distance == 5000
    assert result.buffer_config.distance_m == 5000
    assert result.buffer_config.inferred is False


def test_walking_distance_case_insensitive(parser):
    """Test that contextual distances are case-insensitive."""
    queries = [
        "walking distance from Lausanne",
        "Walking distance from Lausanne",
        "WALKING DISTANCE from Lausanne",
    ]

    for query in queries:
        result = parser.parse(query)
        assert result.buffer_config.distance_m == 1000


def test_contextual_distance_different_locations(parser):
    """Test contextual distances work with various location types."""
    test_cases = [
        ("Walking distance from Geneva Airport", 1000),
        ("Biking distance from Rhine River", 5000),
        ("Walking distance from Matterhorn", 1000),
    ]

    for query, expected_distance in test_cases:
        result = parser.parse(query)
        assert result.buffer_config.distance_m == expected_distance
        assert result.buffer_config.inferred is False


def test_explicit_distance_overrides_context(parser):
    """Test that explicit distance overrides contextual distance."""
    result = parser.parse("Walking distance within 3km from Zurich")

    # Explicit "3km" should take precedence over "walking distance"
    assert result.spatial_relation.explicit_distance == 3000
    assert result.buffer_config.distance_m == 3000


def test_contextual_vs_generic_near(parser):
    """Test that contextual distances differ from generic 'near'."""
    walking_result = parser.parse("Walking distance from Zurich")
    near_result = parser.parse("Near Zurich")

    # Walking should be 1km
    assert walking_result.buffer_config.distance_m == 1000
    assert walking_result.buffer_config.inferred is False

    # Generic "near" should be 5km default
    assert near_result.buffer_config.distance_m == 5000
    assert near_result.buffer_config.inferred is True


def test_confidence_scores_for_contextual_distances(parser):
    """Test that confidence scores are reasonable for contextual distances."""
    result = parser.parse("Walking distance from Lausanne")

    assert result.confidence_breakdown.overall >= 0.8
    assert result.confidence_breakdown.location_confidence >= 0.8
    assert result.confidence_breakdown.relation_confidence >= 0.8
    assert "walking" in result.confidence_breakdown.reasoning.lower() or "1" in result.confidence_breakdown.reasoning


def test_10_minute_walk(parser):
    """Test that '10 minutes walk' is converted to ~800m (5km/h speed)."""
    result = parser.parse("10 minutes walk from Zurich main railway station")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    # 10 min * (5000m / 60 min) = 833m, accept 800-833m range
    assert 800 <= result.spatial_relation.explicit_distance <= 833
    assert 800 <= result.buffer_config.distance_m <= 833
    assert result.buffer_config.inferred is False


def test_5_minute_walk(parser):
    """Test that '5 minutes walk' is converted to ~400m (5km/h speed)."""
    result = parser.parse("5 minutes walk from Bern")

    assert result.spatial_relation.relation == "near"
    # 5 min * (5000m / 60 min) = 417m, accept 400-420m range
    assert 400 <= result.spatial_relation.explicit_distance <= 420
    assert 400 <= result.buffer_config.distance_m <= 420
    assert result.buffer_config.inferred is False


def test_15_minute_walk(parser):
    """Test that '15 minutes walk' is converted to ~1200m (5km/h speed)."""
    result = parser.parse("15 minutes walk from Geneva")

    assert result.spatial_relation.relation == "near"
    # 15 min * (5000m / 60 min) = 1250m, accept 1200-1300m range
    assert 1200 <= result.spatial_relation.explicit_distance <= 1300
    assert 1200 <= result.buffer_config.distance_m <= 1300


def test_30_minute_walk(parser):
    """Test that '30 minutes walk' is converted to ~2400m (5km/h speed)."""
    result = parser.parse("30 minutes walk from Lausanne")

    assert result.spatial_relation.relation == "near"
    # 30 min * (5000m / 60 min) = 2500m, accept 2400-2500m range
    assert 2400 <= result.spatial_relation.explicit_distance <= 2500
    assert 2400 <= result.buffer_config.distance_m <= 2500


def test_10_minute_bike(parser):
    """Test that '10 minutes bike' is converted to ~3300m (20km/h speed)."""
    result = parser.parse("10 minutes bike from Lake Geneva")

    assert result.spatial_relation.relation == "near"
    # 10 min * (20000m / 60 min) = 3333m, accept 3300-3400m range
    assert 3300 <= result.spatial_relation.explicit_distance <= 3400
    assert 3300 <= result.buffer_config.distance_m <= 3400
    assert result.buffer_config.inferred is False


def test_15_minute_bike(parser):
    """Test that '15 minutes bike' is converted to ~5000m (20km/h speed)."""
    result = parser.parse("15 minutes bike from Bern")

    assert result.spatial_relation.relation == "near"
    # 15 min * (20000m / 60 min) = 5000m
    assert result.spatial_relation.explicit_distance == 5000
    assert result.buffer_config.distance_m == 5000


def test_30_minute_bike(parser):
    """Test that '30 minutes bike' is converted to ~10000m (20km/h speed)."""
    result = parser.parse("30 minutes cycling from Zurich")

    assert result.spatial_relation.relation == "near"
    # 30 min * (20000m / 60 min) = 10000m
    assert result.spatial_relation.explicit_distance == 10000
    assert result.buffer_config.distance_m == 10000


def test_time_based_minute_variations(parser):
    """Test that time-based distances work with different minute formats."""
    queries = [
        ("10 minute walk from Zurich", (800, 833)),  # Range for rounding
        ("10-minute walk from Zurich", (800, 833)),
        ("10 min walk from Zurich", (800, 833)),
    ]

    for query, (min_dist, max_dist) in queries:
        result = parser.parse(query)
        assert min_dist <= result.buffer_config.distance_m <= max_dist, f"Failed for query: {query}"
