"""
Tests for spatial operations module.
"""

from shapely.geometry import Point, Polygon, mapping, shape

from etter.models import BufferConfig, SpatialRelation
from etter.spatial import apply_spatial_relation


def test_containment_passthrough():
    """Test that containment returns geometry unchanged."""
    geom = {"type": "Point", "coordinates": [0, 0]}
    relation = SpatialRelation(relation="in", category="containment")

    result = apply_spatial_relation(geom, relation)
    assert result == geom


def test_buffer_positive():
    """Test positive circular buffer."""
    geom = {"type": "Point", "coordinates": [0, 0]}  # Null island
    relation = SpatialRelation(relation="near", category="buffer")
    config = BufferConfig(distance_m=111320, buffer_from="center")  # ~1 degree at equator

    result = apply_spatial_relation(geom, relation, config)

    assert result["type"] == "Polygon"
    # Check bounding box approx (should be ~ +/- 1 degree)
    bounds = shape(result).bounds
    assert -1.1 < bounds[0] < -0.9  # Min X
    assert 0.9 < bounds[2] < 1.1  # Max X


def test_buffer_negative_erosion():
    """Test negative buffer (erosion)."""
    # 2x2 degree square
    poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    geom = mapping(poly)

    relation = SpatialRelation(relation="in_the_heart_of", category="buffer")
    # Erode by ~0.5 degrees (~55km)
    config = BufferConfig(distance_m=-55000, buffer_from="boundary")

    result = apply_spatial_relation(geom, relation, config)

    assert result["type"] == "Polygon"
    area_orig = poly.area
    area_new = shape(result).area
    assert area_new < area_orig
    assert area_new > 0


def test_ring_buffer():
    """Test ring buffer (difference)."""
    geom = {"type": "Point", "coordinates": [0, 0]}
    relation = SpatialRelation(relation="on_shores_of", category="buffer")
    # Buffer 1 deg, but ring only? point has no area, so ring matches buffer
    # unless we use it on a polygon. Let's use a polygon.

    # 1x1 degree square
    poly = Polygon([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])
    geom = mapping(poly)

    config = BufferConfig(distance_m=100000, buffer_from="boundary", ring_only=True)

    result = apply_spatial_relation(geom, relation, config)

    res_shape = shape(result)
    assert res_shape.area > poly.area  # Should be larger total area
    assert not res_shape.contains(Point(0, 0))  # Should NOT contain center (hole)


def test_directional_sector():
    """Test directional sector generation."""
    geom = {"type": "Point", "coordinates": [0, 0]}
    relation = SpatialRelation(relation="north_of", category="directional")
    # North sector (0 degrees), 90 degree width
    config = BufferConfig(distance_m=100000, buffer_from="center")

    # Mocking the spatial config lookup inside apply_spatial_relation requires mocking
    # SpatialRelationConfig. Or we can rely on defaults if we didn't mock it?
    # The implementation instantiates SpatialRelationConfig() internally.
    # "north_of" is a built-in relation, so it should work.

    result = apply_spatial_relation(geom, relation, config)

    poly = shape(result)
    assert poly.contains(Point(0, 0.5))  # Point to North should be inside
    assert not poly.contains(Point(0, -0.5))  # Point to South should be outside
    assert not poly.contains(Point(0.5, 0))  # Point to East should be outside (45 deg boundary)
