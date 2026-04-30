"""
Spatial operations module for transforming geometries according to spatial relations.

Applies buffer, directional, and containment operations to GeoJSON geometries.
All inputs and outputs are GeoJSON dicts in WGS84 (EPSG:4326).
Shapely is used internally for geometry operations.
"""

import math
from typing import Any

from shapely.geometry import MultiLineString, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.linestring import LineString
from shapely.geometry.polygon import Polygon
from shapely.ops import linemerge, unary_union

from .geometry_format import convert_geometry
from .models import BufferConfig, GeometryFormat, SpatialRelation
from .spatial_config import SpatialRelationConfig

_DEFAULT_SPATIAL_CONFIG = SpatialRelationConfig()  # Module-level singleton for default spatial relation configuration.


def apply_spatial_relation(
    geometry: dict[str, Any],
    relation: SpatialRelation,
    buffer_config: BufferConfig | None = None,
    spatial_config: SpatialRelationConfig | None = None,
    geometry_format: GeometryFormat = "geojson",
) -> dict[str, Any] | str:
    """
    Transform a reference geometry according to a spatial relation.

    Converts the input GeoJSON geometry to a search area based on the
    spatial relation category:
    - Containment: returns the original geometry unchanged
    - Buffer: applies positive (expand), negative (erode), or ring buffer
    - Directional: creates an angular sector wedge

    Args:
        geometry: GeoJSON geometry dict in WGS84 (EPSG:4326).
        relation: Spatial relation to apply.
        buffer_config: Buffer configuration (required for buffer/directional relations).
        spatial_config: Spatial relation registry used to look up directional angles.
            Defaults to the module-level singleton; pass an explicit instance to
            avoid repeated construction when calling from a hot path.
        geometry_format: Output format for the geometry. "geojson" (default) returns a
            GeoJSON dict, "wkt" returns a WKT string, "wkb" returns a hex-encoded WKB string.

    Returns:
        Transformed geometry in the requested format (GeoJSON dict, WKT string, or WKB hex string).

    Raises:
        ValueError: If buffer_config is missing for buffer/directional relations,
                     or if the relation category is unknown.

    Examples:
        >>> from etter.models import SpatialRelation, BufferConfig
        >>> # Circular buffer as GeoJSON (default)
        >>> result = apply_spatial_relation(
        ...     geometry={"type": "Point", "coordinates": [6.63, 46.52]},
        ...     relation=SpatialRelation(relation="near", category="buffer"),
        ...     buffer_config=BufferConfig(distance_m=5000, buffer_from="center"),
        ... )

        >>> # Same buffer as WKT
        >>> result = apply_spatial_relation(
        ...     geometry={"type": "Point", "coordinates": [6.63, 46.52]},
        ...     relation=SpatialRelation(relation="near", category="buffer"),
        ...     buffer_config=BufferConfig(distance_m=5000, buffer_from="center"),
        ...     geometry_format="wkt",
        ... )

        >>> # Containment (passthrough)
        >>> result = apply_spatial_relation(
        ...     geometry=city_polygon,
        ...     relation=SpatialRelation(relation="in", category="containment"),
        ... )
    """
    if relation.category == "containment":
        result = _apply_containment(geometry)
    elif relation.category == "buffer":
        if buffer_config is None:
            raise ValueError(f"Buffer relation '{relation.relation}' requires buffer_config")
        result = _apply_buffer(geometry, buffer_config)
    elif relation.category == "directional":
        if buffer_config is None:
            raise ValueError(f"Directional relation '{relation.relation}' requires buffer_config")
        cfg = spatial_config if spatial_config is not None else _DEFAULT_SPATIAL_CONFIG
        relation_config = cfg.get_config(relation.relation)
        direction = relation_config.direction_angle_degrees or 0
        sector_angle = relation_config.sector_angle_degrees or 90
        result = _apply_directional(geometry, buffer_config, direction, sector_angle)
    else:
        raise ValueError(f"Unknown relation category: '{relation.category}'")

    return convert_geometry(result, geometry_format)


def _apply_containment(geometry: dict[str, Any]) -> dict[str, Any]:
    """Return the geometry unchanged for containment relations."""
    return geometry


def _apply_buffer(geometry: dict[str, Any], config: BufferConfig) -> dict[str, Any]:
    """
    Apply buffer operation to geometry.

    Handles:
    - Positive buffer (expand): creates a circular/area buffer
    - Negative buffer (erode): shrinks the geometry inward
    - Ring buffer: excludes the original geometry from the buffer
    - Buffer from center vs boundary
    """
    geom = shape(geometry)
    distance_deg = _meters_to_degrees(config.distance_m, geom.centroid.y)

    if config.buffer_from == "center":
        # Buffer from centroid
        centroid = geom.centroid
        buffered = centroid.buffer(abs(distance_deg))
    elif config.side is not None:
        # One-sided buffer: symmetric buffer clipped to one side of the line
        buffered = _one_sided_buffer(geom, abs(distance_deg), config.side)
    else:
        # Buffer from boundary
        buffered = geom.buffer(distance_deg)

    # Ring buffer: subtract original geometry
    if config.ring_only and config.distance_m > 0:
        buffered = buffered.difference(geom)

    if buffered.is_empty:
        return geometry  # Fallback if erosion eliminates geometry

    return mapping(buffered)


def _collect_line_parts(geom: BaseGeometry) -> list[LineString]:
    """Return a flat list of LineStrings from a LineString or MultiLineString."""
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        merged = linemerge(geom)
        if isinstance(merged, LineString):
            return [merged]
        return [part for part in merged.geoms if isinstance(part, LineString)]
    return []


def _offset_coords(line: LineString, offset_dist: float) -> list[tuple[float, ...]]:
    """Return coordinates of the offset curve of a LineString, flattened across parts."""
    offset = line.offset_curve(offset_dist)
    if offset.is_empty:
        return []
    if isinstance(offset, MultiLineString):
        merged = linemerge(offset)
        if isinstance(merged, LineString):
            return list(merged.coords)
        return [coord for part in merged.geoms for coord in part.coords]
    return list(offset.coords)


def _one_sided_buffer(geom: BaseGeometry, distance_deg: float, side: str) -> BaseGeometry:
    """
    Create a one-sided buffer by clipping a symmetric buffer to one side of a line.

    Uses offset_curve to build a clipping polygon per segment, then intersects each
    with the segment's buffer and unions the results. This avoids artifacts from
    Shapely's single_sided=True on sinuous lines with large distances, and correctly
    handles MultiLineString inputs (e.g. rivers stored as disconnected segments).
    """
    # offset_curve: positive = left, negative = right
    offset_dist = distance_deg if side == "left" else -distance_deg

    parts = _collect_line_parts(geom)
    if not parts:
        return geom.buffer(distance_deg)

    clipped_parts: list[BaseGeometry] = []
    for part in parts:
        part_buffer = part.buffer(distance_deg)
        off_coords = _offset_coords(part, offset_dist)

        if not off_coords:
            clipped_parts.append(part_buffer)
            continue

        # Build a clip polygon: original part coords + reversed offset coords
        clip_coords = list(part.coords) + off_coords[::-1]
        clip_poly = Polygon(clip_coords).buffer(0)  # buffer(0) fixes self-intersections
        clipped_parts.append(part_buffer.intersection(clip_poly))

    return unary_union(clipped_parts)


def _apply_directional(
    geometry: dict[str, Any],
    config: BufferConfig,
    direction_degrees: float,
    sector_angle_degrees: float,
) -> dict[str, Any]:
    """
    Create a directional sector wedge from the geometry centroid.

    The sector extends outward from the centroid in the given direction.
    Convention: 0° = North, 90° = East, 180° = South, 270° = West (clockwise).

    Args:
        geometry: Reference geometry.
        config: Buffer config (distance_m used as sector radius).
        direction_degrees: Center direction of the sector (0=N, 90=E, etc.).
        sector_angle_degrees: Total angular width of the sector.
    """
    geom = shape(geometry)
    centroid = geom.centroid
    cx, cy = centroid.x, centroid.y

    radius_deg = _meters_to_degrees(config.distance_m, cy)
    half_angle = sector_angle_degrees / 2

    # Build sector as a polygon wedge
    # Start angle and end angle (geographic: 0=N, clockwise)
    start_angle = direction_degrees - half_angle
    end_angle = direction_degrees + half_angle

    # Generate arc points
    num_points = 36
    points = [(cx, cy)]  # Center point

    for i in range(num_points + 1):
        angle = start_angle + (end_angle - start_angle) * i / num_points
        # Convert geographic angle to math angle
        # Geographic: 0=N, 90=E (clockwise)
        # Math: 0=E, 90=N (counterclockwise)
        math_angle = math.radians(90 - angle)
        px = cx + radius_deg * math.cos(math_angle)
        py = cy + radius_deg * math.sin(math_angle)
        points.append((px, py))

    points.append((cx, cy))  # Close the polygon

    sector = Polygon(points)

    if sector.is_empty or not sector.is_valid:
        sector = sector.buffer(0)  # Fix invalid geometry

    return mapping(sector)


def _meters_to_degrees(meters: float, latitude: float) -> float:
    """
    Approximate conversion from meters to degrees at a given latitude.

    This is a rough approximation suitable for buffer visualizations.
    For precise work, use proper projection (e.g., UTM).

    At the equator, 1° ≈ 111,320m. At higher latitudes, longitude degrees shrink.
    We use the average of lat/lon degree sizes for a reasonable approximation.
    """
    # 1 degree latitude ≈ 111,320 meters (relatively constant)
    meters_per_degree_lat = 111_320
    # 1 degree longitude varies with latitude
    meters_per_degree_lon = 111_320 * math.cos(math.radians(latitude))
    # Average for a circular approximation
    avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2
    return meters / avg_meters_per_degree
