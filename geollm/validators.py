"""
Validation logic for parsed queries.
"""

import warnings

from .exceptions import LowConfidenceError, LowConfidenceWarning, UnknownRelationError
from .models import BufferConfig, GeoQuery
from .spatial_config import SpatialRelationConfig


def validate_spatial_relation(geo_query: GeoQuery, spatial_config: SpatialRelationConfig) -> None:
    """
    Validate that the spatial relation is registered in configuration.

    Args:
        geo_query: Parsed query to validate
        spatial_config: Spatial relation configuration

    Raises:
        UnknownRelationError: If spatial relation is not registered
    """
    relation_name = geo_query.spatial_relation.relation

    if not spatial_config.has_relation(relation_name):
        available = ", ".join(sorted(spatial_config.list_relations()))
        raise UnknownRelationError(
            f"Unknown spatial relation: '{relation_name}'. "
            f"This may be an LLM hallucination. Available relations: {available}",
            relation_name=relation_name,
        )


def enrich_with_defaults(geo_query: GeoQuery, spatial_config: SpatialRelationConfig) -> GeoQuery:
    """
    Apply default parameters from configuration if not explicitly set.

    For buffer and directional relations, if buffer_config is missing or has inferred=True,
    populate with defaults from the relation configuration.

    Directional relations use consistent 10km radius with 90° sector angle defaults.
    Buffer relations use fallback defaults when LLM doesn't infer context (near=5km, etc.).

    Args:
        geo_query: Parsed query to enrich
        spatial_config: Spatial relation configuration

    Returns:
        Enriched GeoQuery with defaults applied
    """
    relation_config = spatial_config.get_config(geo_query.spatial_relation.relation)

    # Enrich buffer and directional relations
    if relation_config.category not in ("buffer", "directional"):
        return geo_query

    # If no buffer_config at all, create from defaults
    if geo_query.buffer_config is None:
        geo_query.buffer_config = BufferConfig(
            distance_m=relation_config.default_distance_m or 5000,
            buffer_from=relation_config.buffer_from or "center",
            ring_only=relation_config.ring_only,
            inferred=True,
        )
    # If buffer_config exists and is inferred, apply defaults for missing values
    elif geo_query.buffer_config.inferred:
        # Use explicit_distance if provided, otherwise use config default
        if geo_query.spatial_relation.explicit_distance is not None:
            geo_query.buffer_config.distance_m = geo_query.spatial_relation.explicit_distance
            geo_query.buffer_config.inferred = False
        elif geo_query.buffer_config.distance_m == 0:  # Sentinel value
            geo_query.buffer_config.distance_m = relation_config.default_distance_m or 5000

    # If explicit_distance was provided by user, override and mark as not inferred
    if geo_query.spatial_relation.explicit_distance is not None and geo_query.buffer_config:
        geo_query.buffer_config.distance_m = geo_query.spatial_relation.explicit_distance
        geo_query.buffer_config.inferred = False

    return geo_query


def validate_buffer_config_consistency(geo_query: GeoQuery) -> None:
    """
    Validate buffer configuration for consistency and logical constraints.

    Additional business logic checks beyond Pydantic validation.

    Args:
        geo_query: Parsed query to validate

    Raises:
        ValidationError: If buffer config has logical issues
    """
    if not geo_query.buffer_config:
        return

    # Most validation is handled by Pydantic @model_validator
    # Additional checks can be added here:

    # Example: Check for excessively large buffers
    if abs(geo_query.buffer_config.distance_m) > 100000:  # 100km
        warnings.warn(
            f"Large buffer distance: {geo_query.buffer_config.distance_m}m. "
            f"This may be intentional but could cause performance issues.",
            UserWarning,
        )

    # Example: Check for very small negative buffers that might eliminate geometry
    if geo_query.buffer_config.distance_m < -5000:  # -5km erosion
        warnings.warn(
            f"Large negative buffer: {geo_query.buffer_config.distance_m}m. "
            f"This may completely eliminate the reference geometry.",
            UserWarning,
        )


def check_confidence_threshold(geo_query: GeoQuery, threshold: float, strict: bool) -> None:
    """
    Check confidence score and raise error or warning based on mode.

    Args:
        geo_query: Parsed query with confidence scores
        threshold: Minimum acceptable confidence (0-1)
        strict: If True, raise error. If False, emit warning.

    Raises:
        LowConfidenceError: If strict mode and confidence below threshold

    Warns:
        LowConfidenceWarning: If permissive mode and confidence below threshold
    """
    confidence = geo_query.confidence_breakdown.overall

    if confidence >= threshold:
        return  # Confidence is acceptable

    # Build message
    message = (
        f"Low confidence score: {confidence:.2f} (threshold: {threshold:.2f})\n"
        f"Location confidence: {geo_query.confidence_breakdown.location_confidence:.2f}\n"
        f"Relation confidence: {geo_query.confidence_breakdown.relation_confidence:.2f}"
    )

    if geo_query.confidence_breakdown.reasoning:
        message += f"\nReasoning: {geo_query.confidence_breakdown.reasoning}"

    # Strict mode: raise error
    if strict:
        raise LowConfidenceError(
            message,
            confidence=confidence,
            reasoning=geo_query.confidence_breakdown.reasoning,
        )

    # Permissive mode: emit warning
    warnings.warn(LowConfidenceWarning(confidence, message), stacklevel=3)


def validate_query(
    geo_query: GeoQuery,
    spatial_config: SpatialRelationConfig,
    confidence_threshold: float = 0.6,
    strict_mode: bool = False,
) -> GeoQuery:
    """
    Run complete validation pipeline on a parsed query.

    This is a convenience function that runs all validation steps in order:
    1. Validate spatial relation is registered
    2. Enrich with defaults from config
    3. Validate buffer config consistency
    4. Check confidence threshold

    Args:
        geo_query: Parsed query to validate
        spatial_config: Spatial relation configuration
        confidence_threshold: Minimum acceptable confidence
        strict_mode: If True, raise error on low confidence. If False, warn.

    Returns:
        Validated and enriched GeoQuery

    Raises:
        UnknownRelationError: If spatial relation not registered
        ValidationError: If validation checks fail
        LowConfidenceError: If strict mode and confidence below threshold
    """
    # 1. Validate spatial relation
    validate_spatial_relation(geo_query, spatial_config)

    # 2. Enrich with defaults
    geo_query = enrich_with_defaults(geo_query, spatial_config)

    # 3. Validate buffer config
    validate_buffer_config_consistency(geo_query)

    # 4. Check confidence
    check_confidence_threshold(geo_query, confidence_threshold, strict_mode)

    return geo_query
