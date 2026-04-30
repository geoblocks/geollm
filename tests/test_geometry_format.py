"""
Tests for geometry output format conversion.
"""

import re

from shapely.geometry import mapping

from etter.geometry_format import convert_feature_geometry, convert_geometry
from etter.models import BufferConfig, SpatialRelation
from etter.spatial import apply_spatial_relation

POINT_GEOM = {"type": "Point", "coordinates": [6.63, 46.52]}
POINT_FEATURE = {
    "type": "Feature",
    "id": "test-1",
    "geometry": POINT_GEOM,
    "bbox": [6.63, 46.52, 6.63, 46.52],
    "properties": {"name": "Lausanne"},
}


class TestConvertGeometry:
    def test_geojson_passthrough(self):
        result = convert_geometry(POINT_GEOM, "geojson")
        assert result is POINT_GEOM

    def test_wkt_point(self):
        result = convert_geometry(POINT_GEOM, "wkt")
        assert isinstance(result, str)
        assert result.startswith("POINT")
        assert "6.63" in result
        assert "46.52" in result

    def test_wkb_point(self):
        result = convert_geometry(POINT_GEOM, "wkb")
        assert isinstance(result, str)
        assert re.fullmatch(r"[0-9a-fA-F]+", result)

    def test_wkb_is_hex_decodable(self):
        result = convert_geometry(POINT_GEOM, "wkb")
        decoded = bytes.fromhex(result)
        assert len(decoded) > 0

    def test_wkt_polygon(self):
        from shapely.geometry import Polygon

        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        geom = mapping(poly)
        result = convert_geometry(geom, "wkt")
        assert result.startswith("POLYGON")

    def test_wkb_polygon(self):
        from shapely.geometry import Polygon

        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        geom = mapping(poly)
        result = convert_geometry(geom, "wkb")
        assert isinstance(result, str)
        assert re.fullmatch(r"[0-9a-fA-F]+", result)


class TestConvertFeatureGeometry:
    def test_geojson_passthrough_returns_same_object(self):
        result = convert_feature_geometry(POINT_FEATURE, "geojson")
        assert result is POINT_FEATURE

    def test_wkt_replaces_geometry(self):
        result = convert_feature_geometry(POINT_FEATURE, "wkt")
        assert isinstance(result["geometry"], str)
        assert result["geometry"].startswith("POINT")

    def test_wkb_replaces_geometry(self):
        result = convert_feature_geometry(POINT_FEATURE, "wkb")
        assert isinstance(result["geometry"], str)
        assert re.fullmatch(r"[0-9a-fA-F]+", result["geometry"])

    def test_other_fields_preserved(self):
        result = convert_feature_geometry(POINT_FEATURE, "wkt")
        assert result["type"] == "Feature"
        assert result["id"] == "test-1"
        assert result["bbox"] == [6.63, 46.52, 6.63, 46.52]
        assert result["properties"]["name"] == "Lausanne"

    def test_original_feature_not_mutated(self):
        original_geometry = POINT_FEATURE["geometry"]
        convert_feature_geometry(POINT_FEATURE, "wkt")
        assert POINT_FEATURE["geometry"] is original_geometry


class TestApplySpatialRelationFormat:
    def test_default_format_is_geojson(self):
        relation = SpatialRelation(relation="in", category="containment")
        result = apply_spatial_relation(POINT_GEOM, relation)
        assert isinstance(result, dict)
        assert result["type"] == "Point"

    def test_geojson_explicit(self):
        relation = SpatialRelation(relation="in", category="containment")
        result = apply_spatial_relation(POINT_GEOM, relation, geometry_format="geojson")
        assert isinstance(result, dict)

    def test_wkt_containment(self):
        relation = SpatialRelation(relation="in", category="containment")
        result = apply_spatial_relation(POINT_GEOM, relation, geometry_format="wkt")
        assert isinstance(result, str)
        assert result.startswith("POINT")

    def test_wkb_containment(self):
        relation = SpatialRelation(relation="in", category="containment")
        result = apply_spatial_relation(POINT_GEOM, relation, geometry_format="wkb")
        assert isinstance(result, str)
        assert re.fullmatch(r"[0-9a-fA-F]+", result)

    def test_wkt_buffer(self):
        relation = SpatialRelation(relation="near", category="buffer")
        config = BufferConfig(distance_m=5000, buffer_from="center")
        result = apply_spatial_relation(POINT_GEOM, relation, config, geometry_format="wkt")
        assert isinstance(result, str)
        assert result.startswith("POLYGON")

    def test_wkb_buffer(self):
        relation = SpatialRelation(relation="near", category="buffer")
        config = BufferConfig(distance_m=5000, buffer_from="center")
        result = apply_spatial_relation(POINT_GEOM, relation, config, geometry_format="wkb")
        assert isinstance(result, str)
        assert re.fullmatch(r"[0-9a-fA-F]+", result)

    def test_wkt_directional(self):
        relation = SpatialRelation(relation="north_of", category="directional")
        config = BufferConfig(distance_m=10000, buffer_from="center")
        result = apply_spatial_relation(POINT_GEOM, relation, config, geometry_format="wkt")
        assert isinstance(result, str)
        assert result.startswith("POLYGON")
