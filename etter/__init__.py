"""
etter - Natural Language Geographic Query Parsing

Parse location queries into structured geographic queries using LLM.
"""

# Main API
# Exceptions
# Datasources
from .datasources import GeoDataSource, SwissNames3DSource
from .exceptions import (
    GeoFilterError,
    LowConfidenceError,
    LowConfidenceWarning,
    ParsingError,
    UnknownRelationError,
    ValidationError,
)

# Models (for type hints and result access)
from .models import (
    BufferConfig,
    ConfidenceLevel,
    ConfidenceScore,
    GeoQuery,
    ReferenceLocation,
    SpatialRelation,
)
from .parser import GeoFilterParser

# Spatial operations
from .spatial import apply_spatial_relation

# Configuration
from .spatial_config import RelationConfig, SpatialRelationConfig

__all__ = [
    # Main API
    "GeoFilterParser",
    # Models
    "GeoQuery",
    "SpatialRelation",
    "ReferenceLocation",
    "BufferConfig",
    "ConfidenceScore",
    "ConfidenceLevel",
    # Configuration
    "SpatialRelationConfig",
    "RelationConfig",
    # Exceptions
    "GeoFilterError",
    "ParsingError",
    "ValidationError",
    "UnknownRelationError",
    "LowConfidenceError",
    "LowConfidenceWarning",
    # Datasources
    "GeoDataSource",
    "SwissNames3DSource",
    # Spatial
    "apply_spatial_relation",
]
