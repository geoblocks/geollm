"""
Tests for Pydantic models.
"""

import pytest
from pydantic import ValidationError

from geollm.models import (
    BufferConfig,
    ConfidenceScore,
    GeoQuery,
    ReferenceLocation,
    SpatialRelation,
)


def test_confidence_score_valid():
    """Test valid confidence score creation."""
    score = ConfidenceScore(
        overall=0.85,
        location_confidence=0.90,
        relation_confidence=0.80,
        reasoning="High confidence in all components",
    )
    assert score.overall == 0.85
    assert score.location_confidence == 0.90


def test_confidence_score_out_of_range():
    """Test that confidence scores must be 0-1."""
    with pytest.raises(ValidationError):
        ConfidenceScore(
            overall=1.5,  # Invalid
            location_confidence=0.9,
            relation_confidence=0.8,
            reasoning="Test reasoning",
        )


def test_reference_location():
    """Test reference location model."""
    location = ReferenceLocation(
        name="Lausanne",
        type="city",
    )
    assert location.name == "Lausanne"


def test_buffer_config_valid():
    """Test valid buffer config."""
    config = BufferConfig(
        distance_m=5000,
        buffer_from="center",
        ring_only=False,
        inferred=True,
    )
    assert config.distance_m == 5000
    assert config.buffer_from == "center"


def test_buffer_config_ring_only_validation():
    """Test that ring_only requires boundary buffer."""
    with pytest.raises(ValidationError):
        BufferConfig(
            distance_m=1000,
            buffer_from="center",  # Invalid with ring_only
            ring_only=True,
            inferred=True,
        )


def test_buffer_config_negative_distance():
    """Test negative buffer (erosion)."""
    config = BufferConfig(
        distance_m=-500,
        buffer_from="boundary",
        ring_only=False,
        inferred=True,
    )
    assert config.distance_m == -500


def test_spatial_relation():
    """Test spatial relation model."""
    relation = SpatialRelation(
        relation="near",
        category="buffer",
        explicit_distance=2000,
    )
    assert relation.relation == "near"
    assert relation.category == "buffer"
    assert relation.explicit_distance == 2000


def test_geo_query_containment():
    """Test GeoQuery for containment query."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="in",
            category="containment",
            explicit_distance=None,
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=None,
        confidence_breakdown=ConfidenceScore(
            overall=0.95,
            location_confidence=0.95,
            relation_confidence=0.95,
            reasoning="High confidence in containment query",
        ),
        original_query="in Bern",
    )
    assert query.query_type == "simple"
    assert query.buffer_config is None


def test_geo_query_buffer_requires_config():
    """Test that buffer relations require buffer_config."""
    with pytest.raises(ValidationError):
        GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(
                relation="near",
                category="buffer",  # Buffer category
                explicit_distance=None,
            ),
            reference_location=ReferenceLocation(
                name="Bern",
                type="city",
            ),
            buffer_config=None,  # Missing config!
            confidence_breakdown=ConfidenceScore(
                overall=0.85,
                location_confidence=0.85,
                relation_confidence=0.85,
                reasoning="Test reasoning",
            ),
            original_query="near Bern",
        )


def test_geo_query_containment_no_buffer_config():
    """Test that containment relations should not have buffer_config."""
    with pytest.raises(ValidationError):
        GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(
                relation="in",
                category="containment",
                explicit_distance=None,
            ),
            reference_location=ReferenceLocation(
                name="Bern",
                type="city",
            ),
            buffer_config=BufferConfig(  # Should not be present!
                distance_m=1000,
                buffer_from="center",
                ring_only=False,
                inferred=True,
            ),
            confidence_breakdown=ConfidenceScore(
                overall=0.95,
                location_confidence=0.95,
                relation_confidence=0.95,
                reasoning="Test reasoning",
            ),
            original_query="in Bern",
        )


def test_geo_query_serialization():
    """Test that GeoQuery can be serialized to JSON."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="in",
            category="containment",
            explicit_distance=None,
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=None,
        confidence_breakdown=ConfidenceScore(
            overall=0.95,
            location_confidence=0.95,
            relation_confidence=0.95,
            reasoning="High confidence query",
        ),
        original_query="in Bern",
    )

    # Serialize to dict and JSON
    data = query.model_dump()
    json_str = query.model_dump_json()

    assert data["query_type"] == "simple"
    assert data["reference_location"]["name"] == "Bern"
    assert isinstance(json_str, str)
    assert "Bern" in json_str
