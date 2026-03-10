"""
Geographic data source layer for resolving location names to geometries.

Provides a Protocol-based interface for data sources and a SwissNames3D implementation.
"""

from .composite import CompositeDataSource
from .ign_bdtopo import IGNBDTopoSource
from .protocol import GeoDataSource
from .swissnames3d import SwissNames3DSource

__all__ = [
    "CompositeDataSource",
    "GeoDataSource",
    "IGNBDTopoSource",
    "SwissNames3DSource",
]
