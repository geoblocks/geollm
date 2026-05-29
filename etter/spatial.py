"""
Spatial operations module for transforming geometries according to spatial relations.

Applies buffer, directional, and containment operations to GeoJSON geometries.
All inputs and outputs are GeoJSON dicts in WGS84 (EPSG:4326).
Shapely is used internally for geometry operations.
"""

from pyproj import Geod, Transformer
from shapely import clip_by_rect
from shapely.geometry import MultiLineString, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.linestring import LineString
from shapely.geometry.polygon import Polygon
from shapely.ops import linemerge, transform, unary_union

from .geometry_format import convert_geometry
from .models import BufferConfig, GeoJsonGeometry, GeometryFormat, SpatialRelation
from .spatial_config import SpatialRelationConfig

_DEFAULT_SPATIAL_CONFIG = SpatialRelationConfig()  # Module-level singleton for default spatial relation configuration.
_GEOD = Geod(ellps="WGS84")  # Geodesic calculator for accurate area and arc computation.


def _local_transformers(lon: float, lat: float) -> tuple[Transformer, Transformer]:
    """Return (to_local, to_wgs84) Transformers for an azimuthal equidistant CRS
    centred at (lon, lat).  Distances in the local CRS are in metres with low
    distortion within a few hundred kilometres of the centre point.
    """
    aeqd = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
    to_local = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    to_wgs84 = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    return to_local, to_wgs84


# Area thresholds in m² used for distance inference from geometry size.
# Brackets: point/tiny (<1 km²), small (1–50 km²), medium (50–500 km²), large (>500 km²)
_AREA_DISTANCE_BRACKETS: list[tuple[float, int]] = [
    (1_000_000, 500),  # < 1 km²   → 500 m
    (50_000_000, 1_500),  # < 50 km²  → 1 500 m
    (500_000_000, 5_000),  # < 500 km² → 5 000 m
]
_AREA_DISTANCE_DEFAULT = 15_000  # ≥ 500 km² → 15 000 m

# Erosion distances mirror the positive brackets (negative values).
_AREA_EROSION_BRACKETS: list[tuple[float, int]] = [
    (1_000_000, -200),
    (50_000_000, -500),
    (500_000_000, -1_000),
]
_AREA_EROSION_DEFAULT = -2_000


def _area_m2(geom: BaseGeometry) -> float:
    """Return the geodesic area of a Shapely geometry in m² (WGS84 ellipsoid).

    Uses pyproj.Geod.geometry_area_perimeter for accurate area computation
    without the need for reprojection.  The result is always non-negative.
    """
    if geom.area == 0:
        # Non-polygonal geometries (points, lines) have zero planar area; short-
        # circuit to avoid the artefact where pyproj implicitly closes a
        # LineString into a ring and returns a spurious non-zero value.
        return 0.0
    area, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(area)


def _infer_distance_from_area(area_m2: float, erosion: bool) -> int:
    """Return a default buffer distance (m) based on geometry area.

    Args:
        area_m2: Geometry area in square metres.
        erosion: True for erosion (negative buffer) relations.

    Returns:
        Distance in metres (negative for erosion).
    """
    brackets = _AREA_EROSION_BRACKETS if erosion else _AREA_DISTANCE_BRACKETS
    default = _AREA_EROSION_DEFAULT if erosion else _AREA_DISTANCE_DEFAULT
    for threshold, distance in brackets:
        if area_m2 < threshold:
            return distance
    return default


def _refine_buffer_config(
    geom: BaseGeometry,
    buffer_config: BufferConfig,
    relation: SpatialRelation,
) -> BufferConfig:
    """Replace inferred distance with an area-based estimate.

    Only acts when ``buffer_config.inferred`` is True and no explicit distance
    was stated by the user (``relation.explicit_distance is None``).  The
    geometry area drives bracket selection so that tiny features get small
    buffers and large regions get large ones.

    Returns the (possibly updated) BufferConfig — mutates in place for
    consistency with the rest of the pipeline.
    """
    if not buffer_config.inferred or relation.explicit_distance is not None:
        return buffer_config

    erosion = buffer_config.distance_m < 0
    area = _area_m2(geom)
    buffer_config.distance_m = _infer_distance_from_area(area, erosion)
    return buffer_config


def apply_spatial_relation(
    geometry: GeoJsonGeometry | list[GeoJsonGeometry],
    relation: SpatialRelation,
    buffer_config: BufferConfig | None = None,
    spatial_config: SpatialRelationConfig | None = None,
    geometry_format: GeometryFormat = "geojson",
) -> GeoJsonGeometry | str:
    """Transform one or more reference geometries according to a spatial relation.

    A list of geometries is unioned into one before the transformation, so that
    features split across multiple datasource records (e.g. a river in segments)
    produce a single coherent search area.

    When ``buffer_config.inferred`` is True (i.e. no explicit distance was
    stated), the buffer distance is refined from the actual geometry area so
    that small features receive small buffers and large regions receive large
    ones.

    Args:
        geometry: GeoJSON geometry dict or non-empty list of dicts (WGS84).
        relation: Spatial relation to apply.
        buffer_config: Required for buffer/directional relations.
        spatial_config: Relation registry; defaults to the module-level singleton.
        geometry_format: "geojson" (default), "wkt", or "wkb".

    Returns:
        Transformed geometry in the requested format.
    """
    if isinstance(geometry, list):
        if not geometry:
            raise ValueError("geometry list must not be empty")
        geom = unary_union([shape(g) for g in geometry])
        geom_dict: GeoJsonGeometry = mapping(geom)
    else:
        geom = shape(geometry)
        geom_dict = geometry

    # Refine inferred buffer distance from geometry area before dispatching.
    if buffer_config is not None and buffer_config.inferred:
        buffer_config = _refine_buffer_config(geom, buffer_config, relation)

    if relation.category == "containment":
        result = geom_dict
    elif relation.category == "buffer":
        if buffer_config is None:
            raise ValueError(f"Buffer relation '{relation.relation}' requires buffer_config")
        result = _apply_buffer(geom, buffer_config)
    elif relation.category == "directional":
        if buffer_config is None:
            raise ValueError(f"Directional relation '{relation.relation}' requires buffer_config")
        cfg = spatial_config if spatial_config is not None else _DEFAULT_SPATIAL_CONFIG
        relation_config = cfg.get_config(relation.relation)
        direction = relation_config.direction_angle_degrees or 0
        sector_angle = relation_config.sector_angle_degrees or 90
        result = _apply_directional(geom, buffer_config, direction, sector_angle)
    elif relation.category == "clipping":
        cfg = spatial_config if spatial_config is not None else _DEFAULT_SPATIAL_CONFIG
        relation_config = cfg.get_config(relation.relation)
        clip_direction = relation_config.clip_direction or "north"
        result = _apply_clipping(geom, clip_direction)
    else:
        raise ValueError(f"Unknown relation category: '{relation.category}'")

    return convert_geometry(result, geometry_format)


def _apply_clipping(geom: BaseGeometry, clip_direction: str) -> GeoJsonGeometry:
    """
    Clip a geometry to a directional half-plane using its bounding box midpoint.

    For example, "northern_part_of Switzerland" clips Switzerland's polygon to its
    northern half — the area above the bbox midpoint latitude.
    """
    minx, miny, maxx, maxy = geom.bounds
    midx = (minx + maxx) / 2
    midy = (miny + maxy) / 2

    if clip_direction == "north":
        clipped = clip_by_rect(geom, minx, midy, maxx, maxy)
    elif clip_direction == "south":
        clipped = clip_by_rect(geom, minx, miny, maxx, midy)
    elif clip_direction == "east":
        clipped = clip_by_rect(geom, midx, miny, maxx, maxy)
    else:  # west
        clipped = clip_by_rect(geom, minx, miny, midx, maxy)

    if clipped.is_empty:
        return mapping(geom)  # Fallback — should never happen for a valid half-plane clip

    return mapping(clipped)


def _apply_buffer(geom: BaseGeometry, config: BufferConfig) -> GeoJsonGeometry:
    """
    Apply buffer operation to geometry.

    Handles:
    - Positive buffer (expand): creates a circular/area buffer
    - Negative buffer (erode): shrinks the geometry inward
    - Ring buffer: excludes the original geometry from the buffer
    - Buffer from center vs boundary

    Projects the geometry to a local azimuthal equidistant CRS so that the
    buffer distance is in metres (accurate), then reprojects the result back
    to WGS84.
    """
    cx, cy = geom.centroid.x, geom.centroid.y
    to_local, to_wgs84 = _local_transformers(cx, cy)

    geom_local = transform(to_local.transform, geom)

    if config.buffer_from == "center":
        buffered_local = geom_local.centroid.buffer(abs(config.distance_m))
    elif config.side is not None:
        buffered_local = _one_sided_buffer(geom_local, abs(config.distance_m), config.side)
    else:
        buffered_local = geom_local.buffer(config.distance_m)

    # Ring buffer: subtract original geometry (in local CRS)
    if config.ring_only and config.distance_m > 0:
        buffered_local = buffered_local.difference(geom_local)

    if buffered_local.is_empty:
        return mapping(geom)  # Fallback if erosion eliminates geometry

    return mapping(transform(to_wgs84.transform, buffered_local))


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


def _one_sided_buffer(geom: BaseGeometry, distance_m: float, side: str) -> BaseGeometry:
    """
    Create a one-sided buffer by clipping a symmetric buffer to one side of a line.

    Operates on a geometry already projected to a local metric CRS so that
    ``distance_m`` is in metres.  Uses offset_curve to build a clipping polygon
    per segment, then intersects each with the segment's buffer and unions the
    results. This avoids artifacts from Shapely's single_sided=True on sinuous
    lines with large distances, and correctly handles MultiLineString inputs
    (e.g. rivers stored as disconnected segments).
    """
    # offset_curve: positive = left, negative = right
    offset_dist = distance_m if side == "left" else -distance_m

    parts = _collect_line_parts(geom)
    if not parts:
        return geom.buffer(distance_m)

    clipped_parts: list[BaseGeometry] = []
    for part in parts:
        part_buffer = part.buffer(distance_m)
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
    geom: BaseGeometry,
    config: BufferConfig,
    direction_degrees: float,
    sector_angle_degrees: float,
) -> GeoJsonGeometry:
    """
    Create a directional sector wedge from the geometry centroid.

    The sector extends outward from the centroid in the given direction.
    Convention: 0° = North, 90° = East, 180° = South, 270° = West (clockwise).

    Arc points are computed geodesically using vectorized ``Geod.fwd`` so the
    radius is accurate in metres regardless of latitude.

    Args:
        geom: Reference geometry (Shapely, WGS84).
        config: Buffer config (distance_m used as sector radius).
        direction_degrees: Center direction of the sector (0=N, 90=E, etc.).
        sector_angle_degrees: Total angular width of the sector.
    """
    cx, cy = geom.centroid.x, geom.centroid.y

    num_points = 36
    half_angle = sector_angle_degrees / 2
    azimuths = [direction_degrees - half_angle + sector_angle_degrees * i / num_points for i in range(num_points + 1)]

    # Vectorized geodesic forward computation: all arc points in one call.
    lons, lats, _ = _GEOD.fwd(
        [cx] * (num_points + 1),
        [cy] * (num_points + 1),
        azimuths,
        [config.distance_m] * (num_points + 1),
    )

    points = [(cx, cy), *zip(lons, lats), (cx, cy)]
    sector = Polygon(points)

    if sector.is_empty or not sector.is_valid:
        sector = sector.buffer(0)  # Fix invalid geometry

    return mapping(sector)
