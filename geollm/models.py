"""
Pydantic models for structured geographic query representation.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

ConfidenceLevel = Annotated[float, Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")]


class ConfidenceScore(BaseModel):
    """Confidence scores for different aspects of the parsed query."""

    overall: ConfidenceLevel = Field(
        description="Overall confidence score for the entire query parse. "
        "0.9-1.0 = highly confident, 0.7-0.9 = confident, 0.5-0.7 = uncertain, <0.5 = very uncertain",
    )
    location_confidence: ConfidenceLevel = Field(
        description="Confidence in correctly identifying the reference location",
    )
    relation_confidence: ConfidenceLevel = Field(
        description="Confidence in correctly identifying the spatial relation",
    )
    reasoning: str | None = Field(
        None,
        description="Explanation for confidence scores. Always include reasoning for clarity and debugging. "
        "For example: 'Ambiguous location name', 'Unclear spatial relationship', 'High confidence in location matching', etc.",
    )


class ReferenceLocation(BaseModel):
    """A geographic reference location extracted from the query."""

    name: str = Field(description="Location name as mentioned in the query (e.g., 'Lausanne', 'Lake Geneva')")
    # FIXME: enum ?
    type: str | None = Field(
        None,
        description="Type hint for geographic feature (city, lake, mountain, canton, country, "
        "train_station, airport, river, road, etc.). This is a HINT for ranking results, "
        "NOT a strict filter. For ambiguous cases (e.g., 'Bern' could be city or canton, "
        "'Rhone' could be river or road), provide your best guess or leave null. "
        "The datasource will return multiple types ranked by relevance.",
    )
    type_confidence: ConfidenceLevel | None = Field(
        None,
        description="Confidence in the type inference (0-1). High confidence (>0.8) when type is "
        "explicit in query (e.g., 'Lake Geneva'). Low confidence (<0.6) when ambiguous "
        "(e.g., 'Bern', 'Rhone'). Use spatial relation as hint: 'along X' → river/road, "
        "'in X' → city/region, 'on X' → lake/mountain.",
    )


class BufferConfig(BaseModel):
    """Configuration for buffer-based spatial operations."""

    distance_m: float = Field(
        description="Buffer distance in meters. Positive values expand outward (proximity), "
        "negative values erode inward (e.g., 'in the heart of'). "
        "Examples: 5000 = 5km radius, -500 = 500m erosion"
    )
    buffer_from: Literal["center", "boundary"] = Field(
        description="Buffer origin. 'center' = buffer from centroid point (for proximity), "
        "'boundary' = buffer from polygon boundary (for shores, along roads, erosion)"
    )
    ring_only: bool = Field(
        False,
        description="If True, exclude the reference feature itself to create a ring/donut shape. "
        "Used for queries like 'on the shores of Lake X' (exclude the lake water itself). "
        "Only valid with buffer_from='boundary'.",
    )
    inferred: bool = Field(
        True,
        description="True if this configuration was inferred from relation defaults. "
        "False if the user explicitly specified distance or buffer parameters.",
    )

    @model_validator(mode="after")
    def validate_ring_only(self) -> "BufferConfig":
        """Validate that ring_only is only used with boundary buffers."""
        if self.ring_only and self.buffer_from == "center":
            raise ValueError("ring_only=True requires buffer_from='boundary' (cannot create ring from center point)")
        return self


class SpatialRelation(BaseModel):
    """A spatial relationship between target and reference."""

    relation: str = Field(
        description="Spatial relation keyword. Examples: 'in', 'near', 'around', 'north_of', "
        "'on_shores_of', 'in_the_heart_of', etc. Use the exact relation name from the available list."
    )
    category: Literal["containment", "buffer", "directional"] = Field(
        description="Category of spatial relation. "
        "'containment' = exact boundary matching (in), "
        "'buffer' = proximity or erosion operations (near, around, on_shores_of, in_the_heart_of), "
        "'directional' = sector-based queries (north_of, south_of, east_of, west_of)"
    )
    explicit_distance: float | None = Field(
        None,
        description="Distance in meters if explicitly mentioned by user. "
        "For example: 'within 5km' → 5000, 'within 500 meters' → 500. "
        "Leave null if not explicitly stated.",
    )


class GeoQuery(BaseModel):
    """
    Root model representing a parsed geographic query.
    This is the main output structure returned by the parser.
    """

    query_type: Literal["simple", "compound", "split", "boolean"] = Field(
        "simple",
        description="Type of query. Phase 1 only supports 'simple'. "
        "Future: 'compound' = multi-step, 'split' = area division, 'boolean' = AND/OR/NOT operations",
    )
    spatial_relation: SpatialRelation = Field(description="Spatial relationship to reference location")
    reference_location: ReferenceLocation = Field(description="Reference location for the spatial query")
    buffer_config: BufferConfig | None = Field(
        None,
        description="Buffer configuration for buffer and directional relations. "
        "Auto-generated with defaults by enrich_with_defaults() if not provided. "
        "Required for 'near', 'around', 'north_of', etc. "
        "Set to None for containment relations ('in').",
    )
    confidence_breakdown: ConfidenceScore = Field(description="Confidence scores for different aspects of the parse")
    original_query: str = Field(description="Original query text exactly as provided by the user")

    @model_validator(mode="after")
    def validate_buffer_config_consistency(self) -> "GeoQuery":
        """Validate buffer_config consistency with relation category."""
        # Buffer and directional relations must have buffer_config
        if self.spatial_relation.category in ("buffer", "directional") and self.buffer_config is None:
            raise ValueError(
                f"{self.spatial_relation.category} relation '{self.spatial_relation.relation}' requires buffer_config"
            )

        # Containment relations should not have buffer_config
        if self.spatial_relation.category == "containment" and self.buffer_config is not None:
            raise ValueError(
                f"{self.spatial_relation.category} relation '{self.spatial_relation.relation}' "
                f"should not have buffer_config"
            )

        return self
