"""
Smoke test for the etter wheel distribution (wheel and source distribution)

Run with:
    uv run --isolated --no-project --with dist/*.whl tests/smoke_check.py
    uv run --isolated --no-project --with dist/*.tar.gz tests/smoke_check.py

In CI (tag-triggered), pass the expected version via the environment:
    ETTER_EXPECTED_VERSION=1.2.3 uv run --isolated --no-project --with dist/*.whl tests/smoke_check.py

The script will then assert that the installed package version matches the tag.
"""

import os
import pathlib
import sys

_repo_root = str(pathlib.Path(__file__).parent.parent.resolve())
sys.path = [p for p in sys.path if pathlib.Path(p).resolve() != pathlib.Path(_repo_root)]

_failures: list[str] = []


def check(label: str, fn):
    try:
        fn()
        print(f"  OK  {label}")
    except Exception as exc:
        print(f"  FAIL  {label}: {exc}", file=sys.stderr)
        _failures.append(f"{label}: {exc}")


def _exit_if_failures():
    if _failures:
        print(f"\n{len(_failures)} check(s) failed:", file=sys.stderr)
        for f in _failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)


print("--- version ---")


def _version_string_exists():
    import etter

    assert hasattr(etter, "__version__"), "etter.__version__ is not defined"
    assert isinstance(etter.__version__, str), "__version__ must be a str"
    assert etter.__version__ != "unknown", (
        "__version__ is 'unknown': package metadata not found; did you install from the wheel?"
    )


def _version_matches_metadata():
    from importlib.metadata import version

    import etter

    metadata_version = version("etter")
    assert etter.__version__ == metadata_version, (
        f"etter.__version__ ({etter.__version__!r}) != importlib.metadata version ({metadata_version!r})"
    )


check("__version__ attribute exists and is not 'unknown'", _version_string_exists)
check("__version__ matches importlib.metadata", _version_matches_metadata)


def _version_matches_expected_tag():
    expected = os.environ.get("ETTER_EXPECTED_VERSION")
    if not expected:
        print("  SKIP  version matches expected tag (ETTER_EXPECTED_VERSION not set)")
        return
    import etter

    assert etter.__version__ == expected, (
        f"etter.__version__ ({etter.__version__!r}) != ETTER_EXPECTED_VERSION ({expected!r}); "
        "pyproject.toml version was not updated before tagging"
    )


check("version matches expected tag (ETTER_EXPECTED_VERSION)", _version_matches_expected_tag)

_exit_if_failures()

print("--- imports ---")


def _import_top_level():
    import etter  # noqa: F401

    required = [
        "GeoFilterParser",
        "GeoQuery",
        "SpatialRelation",
        "ReferenceLocation",
        "BufferConfig",
        "ConfidenceScore",
        "ConfidenceLevel",
        "SpatialRelationConfig",
        "RelationConfig",
        "GeoFilterError",
        "ParsingError",
        "ValidationError",
        "UnknownRelationError",
        "LowConfidenceError",
        "LowConfidenceWarning",
        "GeoDataSource",
        "SwissNames3DSource",
        "IGNBDCartoSource",
        "CompositeDataSource",
        "PostGISDataSource",
        "apply_spatial_relation",
    ]
    missing = [name for name in required if not hasattr(etter, name)]
    assert not missing, f"Missing from etter.__all__: {missing}"


check("etter package importable with all public names", _import_top_level)


print("--- sub-modules ---")

check("etter.models", lambda: __import__("etter.models"))
check("etter.exceptions", lambda: __import__("etter.exceptions"))
check("etter.parser", lambda: __import__("etter.parser"))
check("etter.spatial", lambda: __import__("etter.spatial"))
check("etter.spatial_config", lambda: __import__("etter.spatial_config"))
check("etter.validators", lambda: __import__("etter.validators"))
check("etter.prompts", lambda: __import__("etter.prompts"))
check("etter.datasources", lambda: __import__("etter.datasources"))
check("etter.datasources.protocol", lambda: __import__("etter.datasources.protocol"))
check("etter.datasources.composite", lambda: __import__("etter.datasources.composite"))
check("etter.datasources.swissnames3d", lambda: __import__("etter.datasources.swissnames3d"))
check("etter.datasources.ign_bdcarto", lambda: __import__("etter.datasources.ign_bdcarto"))
check("etter.datasources.postgis", lambda: __import__("etter.datasources.postgis"))
check("etter.datasources.location_types", lambda: __import__("etter.datasources.location_types"))


print("--- models ---")


def _reference_location():
    from etter import ReferenceLocation

    loc = ReferenceLocation(name="Lausanne", type="city", type_confidence=0.9)
    assert loc.name == "Lausanne"


def _spatial_relation_containment():
    from etter import SpatialRelation

    rel = SpatialRelation(relation="in", category="containment", explicit_distance=None)
    assert rel.category == "containment"


def _spatial_relation_buffer():
    from etter import SpatialRelation

    rel = SpatialRelation(relation="near", category="buffer", explicit_distance=5000)
    assert rel.explicit_distance == 5000


def _buffer_config():
    from etter import BufferConfig

    cfg = BufferConfig(distance_m=3000, buffer_from="center", ring_only=False, side=None, inferred=True)
    assert cfg.distance_m == 3000
    assert not cfg.ring_only


def _buffer_config_ring_boundary():
    from etter import BufferConfig

    cfg = BufferConfig(distance_m=200, buffer_from="boundary", ring_only=True, side=None, inferred=True)
    assert cfg.ring_only


def _buffer_config_ring_center_raises():
    from etter import BufferConfig

    try:
        BufferConfig(distance_m=200, buffer_from="center", ring_only=True, side=None, inferred=True)
        raise AssertionError("Expected ValueError for ring_only=True with buffer_from='center'")
    except ValueError:
        pass


def _confidence_score():
    from etter import ConfidenceScore

    cs = ConfidenceScore(overall=0.9, location_confidence=0.95, relation_confidence=0.85, reasoning="test")
    assert cs.overall == 0.9


def _geoquery_containment():
    from etter import ConfidenceScore, GeoQuery, ReferenceLocation, SpatialRelation

    GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(relation="in", category="containment", explicit_distance=None),
        reference_location=ReferenceLocation(name="Geneva", type=None, type_confidence=None),
        buffer_config=None,
        confidence_breakdown=ConfidenceScore(
            overall=0.95, location_confidence=0.95, relation_confidence=0.95, reasoning=None
        ),
        original_query="restaurants in Geneva",
    )


def _geoquery_buffer():
    from etter import BufferConfig, ConfidenceScore, GeoQuery, ReferenceLocation, SpatialRelation

    GeoQuery(
        query_type="simple",
        spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=None),
        reference_location=ReferenceLocation(name="Zurich", type=None, type_confidence=None),
        buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, side=None, inferred=True),
        confidence_breakdown=ConfidenceScore(
            overall=0.9, location_confidence=0.9, relation_confidence=0.9, reasoning=None
        ),
        original_query="near Zurich",
    )


def _geoquery_buffer_missing_config_raises():
    from etter import ConfidenceScore, GeoQuery, ReferenceLocation, SpatialRelation

    try:
        GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=None),
            reference_location=ReferenceLocation(name="Zurich", type=None, type_confidence=None),
            buffer_config=None,
            confidence_breakdown=ConfidenceScore(
                overall=0.9, location_confidence=0.9, relation_confidence=0.9, reasoning=None
            ),
            original_query="near Zurich",
        )
        raise AssertionError("Expected ValueError for missing buffer_config")
    except ValueError:
        pass


check("ReferenceLocation instantiation", _reference_location)
check("SpatialRelation containment", _spatial_relation_containment)
check("SpatialRelation buffer with explicit_distance", _spatial_relation_buffer)
check("BufferConfig center buffer", _buffer_config)
check("BufferConfig boundary ring buffer", _buffer_config_ring_boundary)
check("BufferConfig ring_only=True with center raises", _buffer_config_ring_center_raises)
check("ConfidenceScore instantiation", _confidence_score)
check("GeoQuery containment", _geoquery_containment)
check("GeoQuery buffer", _geoquery_buffer)
check("GeoQuery buffer missing buffer_config raises", _geoquery_buffer_missing_config_raises)


print("--- exceptions ---")


def _exception_hierarchy():
    from etter import (
        GeoFilterError,
        LowConfidenceError,
        LowConfidenceWarning,
        ParsingError,
        UnknownRelationError,
        ValidationError,
    )

    assert issubclass(ParsingError, GeoFilterError)
    assert issubclass(ValidationError, GeoFilterError)
    assert issubclass(UnknownRelationError, ValidationError)
    assert issubclass(LowConfidenceError, GeoFilterError)
    assert issubclass(LowConfidenceWarning, UserWarning)


def _parsing_error_attrs():
    from etter import ParsingError

    err = ParsingError("bad", raw_response="raw", original_error=ValueError("x"))
    assert err.raw_response == "raw"


def _low_confidence_error_attrs():
    from etter import LowConfidenceError

    err = LowConfidenceError("low", confidence=0.3, reasoning="unclear")
    assert err.confidence == 0.3


def _unknown_relation_error_attrs():
    from etter import UnknownRelationError

    err = UnknownRelationError("unknown", relation_name="flying_over")
    assert err.relation_name == "flying_over"


check("Exception hierarchy", _exception_hierarchy)
check("ParsingError attributes", _parsing_error_attrs)
check("LowConfidenceError attributes", _low_confidence_error_attrs)
check("UnknownRelationError attributes", _unknown_relation_error_attrs)


print("--- SpatialRelationConfig ---")


def _default_relations_present():
    from etter import SpatialRelationConfig

    cfg = SpatialRelationConfig()
    assert len(cfg.relations) > 0, "No built-in relations registered"
    for expected in ("in", "near"):
        assert expected in cfg.relations, f"Built-in relation '{expected}' missing"


def _relation_config_attrs():
    from etter import RelationConfig, SpatialRelationConfig

    cfg = SpatialRelationConfig()
    rel = cfg.relations["in"]
    assert isinstance(rel, RelationConfig)
    assert rel.category == "containment"


def _custom_relation_registration():
    from etter import RelationConfig, SpatialRelationConfig

    cfg = SpatialRelationConfig()
    cfg.relations["test_relation"] = RelationConfig(
        name="test_relation",
        category="buffer",
        description="A test relation",
        default_distance_m=1000,
        buffer_from="center",
    )
    assert "test_relation" in cfg.relations


check("Default relations registered", _default_relations_present)
check("RelationConfig attributes on built-in relation", _relation_config_attrs)
check("Custom relation can be registered", _custom_relation_registration)


print("--- apply_spatial_relation ---")


def _apply_spatial_relation_in_top_level():
    import etter

    assert hasattr(etter, "apply_spatial_relation"), "apply_spatial_relation should be exported from etter"


def _containment_passthrough():
    from etter import SpatialRelation, apply_spatial_relation

    geojson = {"type": "Polygon", "coordinates": [[[6.0, 46.0], [6.1, 46.0], [6.1, 46.1], [6.0, 46.1], [6.0, 46.0]]]}
    result = apply_spatial_relation(
        geojson, SpatialRelation(relation="in", category="containment", explicit_distance=None)
    )
    assert result["type"] == "Polygon"


def _buffer_from_point():
    from etter import BufferConfig, SpatialRelation, apply_spatial_relation

    point = {"type": "Point", "coordinates": [6.63, 46.52]}
    result = apply_spatial_relation(
        point,
        SpatialRelation(relation="near", category="buffer", explicit_distance=None),
        buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, side=None, inferred=True),
    )
    assert result["type"] in ("Polygon", "MultiPolygon")


def _directional_buffer():
    from etter import BufferConfig, SpatialRelation, apply_spatial_relation

    point = {"type": "Point", "coordinates": [6.63, 46.52]}
    result = apply_spatial_relation(
        point,
        SpatialRelation(relation="north_of", category="directional", explicit_distance=None),
        buffer_config=BufferConfig(distance_m=50000, buffer_from="center", ring_only=False, side=None, inferred=True),
    )
    assert result["type"] in ("Polygon", "MultiPolygon")


check("apply_spatial_relation exported from top-level etter", _apply_spatial_relation_in_top_level)
check("Containment relation – geometry passes through unchanged", _containment_passthrough)
check("Buffer relation – point expands to polygon", _buffer_from_point)
check("Directional relation – sector polygon produced", _directional_buffer)


print("--- GeoFilterParser ---")


def _parser_instantiation():
    from unittest.mock import MagicMock

    from etter import GeoFilterParser, SpatialRelationConfig

    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=mock_llm)
    parser = GeoFilterParser(llm=mock_llm, spatial_config=SpatialRelationConfig())
    assert parser is not None


check("GeoFilterParser can be instantiated with a mock LLM", _parser_instantiation)


print()
_exit_if_failures()
print("All smoke checks passed.")
