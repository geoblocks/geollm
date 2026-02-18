"""
Tests for spatial relation configuration.
"""

import pytest

from geollm.exceptions import UnknownRelationError
from geollm.spatial_config import RelationConfig, SpatialRelationConfig


def test_default_relations_loaded():
    """Test that default relations are initialized."""
    config = SpatialRelationConfig()

    # Check containment relations
    assert config.has_relation("in")

    # Check buffer relations
    assert config.has_relation("near")
    assert config.has_relation("on_shores_of")
    assert config.has_relation("along")
    assert config.has_relation("in_the_heart_of")

    # Check cardinal directional relations
    assert config.has_relation("north_of")
    assert config.has_relation("south_of")
    assert config.has_relation("east_of")
    assert config.has_relation("west_of")

    # Check diagonal directional relations
    assert config.has_relation("northeast_of")
    assert config.has_relation("southeast_of")
    assert config.has_relation("southwest_of")
    assert config.has_relation("northwest_of")


def test_get_config():
    """Test getting configuration for a relation."""
    config = SpatialRelationConfig()

    near_config = config.get_config("near")
    assert near_config.name == "near"
    assert near_config.category == "buffer"
    assert near_config.default_distance_m == 5000


def test_get_unknown_relation():
    """Test that unknown relation raises error."""
    config = SpatialRelationConfig()

    with pytest.raises(UnknownRelationError) as exc_info:
        config.get_config("unknown_relation")

    assert "unknown_relation" in str(exc_info.value)


def test_register_custom_relation():
    """Test registering a custom relation."""
    config = SpatialRelationConfig()

    custom = RelationConfig(
        name="very_close",
        category="buffer",
        description="Very close proximity",
        default_distance_m=500,
        buffer_from="center",
    )

    config.register_relation(custom)

    assert config.has_relation("very_close")
    retrieved = config.get_config("very_close")
    assert retrieved.default_distance_m == 500


def test_list_relations():
    """Test listing relations."""
    config = SpatialRelationConfig()

    all_relations = config.list_relations()
    assert "in" in all_relations
    assert "near" in all_relations
    assert "north_of" in all_relations


def test_list_relations_by_category():
    """Test listing relations filtered by category."""
    config = SpatialRelationConfig()

    containment = config.list_relations(category="containment")
    assert "in" in containment
    assert "near" not in containment

    buffer = config.list_relations(category="buffer")
    assert "near" in buffer
    assert "in" not in buffer


def test_format_for_prompt():
    """Test formatting relations for LLM prompt."""
    config = SpatialRelationConfig()

    formatted = config.format_for_prompt()

    # Should include category headers
    assert "CONTAINMENT RELATIONS" in formatted
    assert "BUFFER RELATIONS" in formatted
    assert "DIRECTIONAL RELATIONS" in formatted

    # Should include relation names
    assert "in" in formatted
    assert "near" in formatted
    assert "north_of" in formatted

    # Should include notes
    assert "Negative distances" in formatted


def test_directional_angles():
    """Test that directional relations have correct angle values."""
    config = SpatialRelationConfig()

    # Cardinal directions (0° = North, clockwise)
    assert config.get_config("north_of").direction_angle_degrees == 0
    assert config.get_config("east_of").direction_angle_degrees == 90
    assert config.get_config("south_of").direction_angle_degrees == 180
    assert config.get_config("west_of").direction_angle_degrees == 270

    # Diagonal directions
    assert config.get_config("northeast_of").direction_angle_degrees == 45
    assert config.get_config("southeast_of").direction_angle_degrees == 135
    assert config.get_config("southwest_of").direction_angle_degrees == 225
    assert config.get_config("northwest_of").direction_angle_degrees == 315
