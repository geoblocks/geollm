"""
Tests for validation logic.
"""

import warnings

import pytest

from etter.exceptions import LowConfidenceError, LowConfidenceWarning, UnknownRelationError
from etter.models import (
    BufferConfig,
    ConfidenceScore,
    GeoQuery,
    ReferenceLocation,
    SpatialRelation,
)
from etter.spatial_config import SpatialRelationConfig
from etter.validators import (
    check_confidence_threshold,
    enrich_with_defaults,
    validate_query,
    validate_spatial_relation,
)


@pytest.fixture
def spatial_config():
    """Fixture for spatial config."""
    return SpatialRelationConfig()


@pytest.fixture
def sample_query():
    """Fixture for a sample query."""
    return GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="in",
            category="containment",
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=None,
        confidence_breakdown=ConfidenceScore(
            overall=0.85,
            location_confidence=0.90,
            relation_confidence=0.80,
        ),
        original_query="in Bern",
    )


def test_validate_known_relation(spatial_config, sample_query):
    """Test validation passes for known relation."""
    # Should not raise
    validate_spatial_relation(sample_query, spatial_config)


def test_validate_unknown_relation(spatial_config, sample_query):
    """Test validation fails for unknown relation."""
    sample_query.spatial_relation.relation = "unknown_relation"

    with pytest.raises(UnknownRelationError) as exc_info:
        validate_spatial_relation(sample_query, spatial_config)

    assert "unknown_relation" in str(exc_info.value)


def test_enrich_buffer_defaults(spatial_config):
    """Test enrichment adds buffer defaults."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="near",
            category="buffer",
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=BufferConfig(
            distance_m=0,  # Placeholder, will be enriched
            buffer_from="center",
            ring_only=False,
            inferred=True,
        ),
        confidence_breakdown=ConfidenceScore(
            overall=0.85,
            location_confidence=0.85,
            relation_confidence=0.85,
        ),
        original_query="near Bern",
    )

    enriched = enrich_with_defaults(query, spatial_config)

    assert enriched.buffer_config is not None
    assert enriched.buffer_config.distance_m == 5000  # Default for "near"
    assert enriched.buffer_config.buffer_from == "center"


def test_enrich_explicit_distance(spatial_config):
    """Test that explicit distance overrides defaults."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="near",
            category="buffer",
            explicit_distance=2000,  # User specified 2km
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=BufferConfig(
            distance_m=0,  # Placeholder
            buffer_from="center",
            ring_only=False,
            inferred=True,
        ),
        confidence_breakdown=ConfidenceScore(
            overall=0.85,
            location_confidence=0.85,
            relation_confidence=0.85,
        ),
        original_query="within 2km of Bern",
    )

    enriched = enrich_with_defaults(query, spatial_config)

    assert enriched.buffer_config is not None
    assert enriched.buffer_config.distance_m == 2000  # User's value
    assert enriched.buffer_config.inferred is False


def test_confidence_above_threshold(sample_query):
    """Test that good confidence passes."""
    sample_query.confidence_breakdown.overall = 0.90

    # Should not raise
    check_confidence_threshold(sample_query, threshold=0.6, strict=False)
    check_confidence_threshold(sample_query, threshold=0.6, strict=True)


def test_confidence_below_threshold_permissive(sample_query):
    """Test low confidence in permissive mode emits warning."""
    sample_query.confidence_breakdown.overall = 0.50

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        check_confidence_threshold(sample_query, threshold=0.6, strict=False)

        assert len(w) == 1
        assert issubclass(w[0].category, LowConfidenceWarning)


def test_confidence_below_threshold_strict(sample_query):
    """Test low confidence in strict mode raises error."""
    sample_query.confidence_breakdown.overall = 0.50

    with pytest.raises(LowConfidenceError) as exc_info:
        check_confidence_threshold(sample_query, threshold=0.6, strict=True)

    assert exc_info.value.confidence == 0.50


def test_validate_query_complete_pipeline(spatial_config):
    """Test complete validation pipeline."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="near",
            category="buffer",
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=BufferConfig(
            distance_m=0,  # Placeholder, will be enriched
            buffer_from="center",
            ring_only=False,
            inferred=True,
        ),
        confidence_breakdown=ConfidenceScore(
            overall=0.85,
            location_confidence=0.85,
            relation_confidence=0.85,
        ),
        original_query="near Bern",
    )

    validated = validate_query(
        query,
        spatial_config,
        confidence_threshold=0.6,
        strict_mode=False,
    )

    # Should be enriched with defaults
    assert validated.buffer_config is not None
    assert validated.buffer_config.distance_m == 5000


def test_enrich_directional_defaults(spatial_config):
    """Test that directional relations auto-generate buffer_config with 10km defaults."""
    query = GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(
            relation="north_of",
            category="directional",
        ),
        reference_location=ReferenceLocation(
            name="Bern",
            type="city",
        ),
        buffer_config=BufferConfig(
            distance_m=0,  # Placeholder, will be enriched
            buffer_from="center",
            ring_only=False,
            inferred=True,
        ),
        confidence_breakdown=ConfidenceScore(
            overall=0.85,
            location_confidence=0.85,
            relation_confidence=0.85,
        ),
        original_query="north of Bern",
    )

    enriched = enrich_with_defaults(query, spatial_config)

    # Verify buffer_config was enriched with directional defaults
    assert enriched.buffer_config is not None
    assert enriched.buffer_config.distance_m == 10000  # 10km default for directional
    assert enriched.buffer_config.buffer_from == "center"
    assert enriched.buffer_config.ring_only is False
    assert enriched.buffer_config.inferred is True
