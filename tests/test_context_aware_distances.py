"""
Tests for context-aware distance inference by LLM.

These tests verify that the LLM intelligently infers appropriate buffer distances
based on feature scale context, query intent signals, and erosion context.

These tests require an LLM with the updated context-aware prompt.
"""

import pytest


@pytest.mark.parametrize(
    "query,min_dist,max_dist",
    [
        # Small feature (~1km)
        ("Near Zurich main railway station", 500, 2000),
        # Medium feature (~5km)
        ("Near Lausanne", 3000, 7000),
        # Large feature (~10-15km)
        ("Near the Valais canton", 8000, 20000),
        # Intent: tight proximity
        ("Next to Zurich main station", 300, 2000),
        # Intent: wide area
        ("In the region of Lausanne", 8000, 20000),
        # Combined: small feature + close intent
        ("Close to Zurich train station", 300, 2000),
        # Combined: large feature + wide intent
        ("In the area of the Matterhorn", 10000, 25000),
    ],
)
def test_near_buffer_inferred(parser, query, min_dist, max_dist):
    """Test that near/buffer distances are inferred correctly from context."""
    result = parser.parse(query)
    assert result.spatial_relation.relation == "near"
    assert min_dist <= result.buffer_config.distance_m <= max_dist


@pytest.mark.parametrize(
    "query,min_dist,max_dist",
    [
        ("In the heart of Lausanne old town", -800, -300),  # small area: ~-500m
        ("In the heart of Zurich", -1500, -700),  # medium area: ~-1000m
        ("In the heart of Valais", -3000, -1500),  # large area: ~-2000m
    ],
)
def test_in_the_heart_of_erosion(parser, query, min_dist, max_dist):
    """Test that in_the_heart_of erosion distances are inferred from area size."""
    result = parser.parse(query)
    assert result.spatial_relation.relation == "in_the_heart_of"
    assert min_dist <= result.buffer_config.distance_m <= max_dist


@pytest.mark.parametrize(
    "query,expected_distance",
    [
        ("Near the Matterhorn within 2km", 2000),
        ("Close to Lake Geneva within 10km", 10000),
    ],
)
def test_explicit_distance_overrides_context(parser, query, expected_distance):
    """Test that explicit distances override any inferred context."""
    result = parser.parse(query)
    assert result.spatial_relation.explicit_distance == expected_distance
    assert result.buffer_config.distance_m == expected_distance
