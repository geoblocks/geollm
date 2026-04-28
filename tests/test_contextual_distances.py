"""
Tests for context-dependent distance handling.

These tests verify that etter correctly recognizes and converts contextual
distance expressions like "walking distance" and "biking distance" into
explicit buffer distances.
"""

import pytest


@pytest.mark.parametrize(
    "query,expected_distance",
    [
        ("Walking distance from Geneva Airport", 1000),
        ("Walking distance from Matterhorn", 1000),
        ("Walking distance within 3km from Zurich", 3000),
    ],
)
def test_contextual_distance_different_locations(parser, query, expected_distance):
    """Test contextual distances work with various location types."""
    result = parser.parse(query)
    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    assert result.spatial_relation.explicit_distance == expected_distance
    assert result.buffer_config.distance_m == expected_distance
    assert result.buffer_config.inferred is False


@pytest.mark.parametrize(
    "query,min_dist,max_dist",
    [
        # walk: 5km/h
        ("10 minutes walk from Zurich main railway station", 833, 834),  # 833m
        # bike: 20km/h
        ("15 minutes bike from Bern", 5000, 5000),  # 5000m
    ],
)
def test_timed_distance(parser, query, min_dist, max_dist):
    """Test that timed walk/bike queries are converted to correct distances."""
    result = parser.parse(query)
    assert result.spatial_relation.relation == "near"
    assert min_dist <= result.spatial_relation.explicit_distance <= max_dist
    assert min_dist <= result.buffer_config.distance_m <= max_dist
    assert result.buffer_config.inferred is False
