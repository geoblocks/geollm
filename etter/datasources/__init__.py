"""
Geographic data source layer for resolving location names to geometries.

Provides a Protocol-based interface (GeoDataSource) and concrete implementations:
SwissNames3DSource, IGNBDCartoSource, PostGISDataSource, and CompositeDataSource.
"""

from .composite import CompositeDataSource
from .ign_bdcarto import IGNBDCartoSource
from .location_types import LocationTypeName, TypeMap
from .postgis import PostGISDataSource
from .protocol import GeoDataSource
from .swissnames3d import SwissNames3DSource

__all__ = [
    "CompositeDataSource",
    "GeoDataSource",
    "IGNBDCartoSource",
    "LocationTypeName",
    "PostGISDataSource",
    "SwissNames3DSource",
    "TypeMap",
]
