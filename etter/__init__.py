"""
etter - Natural language geographic query parsing using LLMs.

Parse location queries into structured geographic queries using LLM.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("etter")
except PackageNotFoundError:  # running from source without install
    __version__ = "unknown"

# Main API
# Exceptions
# Datasources
from .datasources import CompositeDataSource, GeoDataSource, IGNBDCartoSource, PostGISDataSource, SwissNames3DSource
from .exceptions import (
    GeoFilterError,
    LowConfidenceError,
    LowConfidenceWarning,
    ParsingError,
    UnknownRelationError,
    ValidationError,
)
from .geometry_format import convert_feature_geometry, convert_geometry

# Models (for type hints and result access)
from .models import (
    BufferConfig,
    ConfidenceLevel,
    ConfidenceScore,
    GeometryFormat,
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
    "GeometryFormat",
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
    "IGNBDCartoSource",
    "CompositeDataSource",
    "PostGISDataSource",
    # Spatial
    "apply_spatial_relation",
    "convert_geometry",
    "convert_feature_geometry",
]
