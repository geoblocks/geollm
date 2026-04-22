"""
Tests for TypeMap and LocationTypeName explicit typing (issue #38).

Verifies that:
- LocationTypeName and TypeMap are importable from the public datasources API.
- All keys in the built-in type maps (OBJEKTART_TYPE_MAP, IGN_BDCARTO_TYPE_MAP)
  are valid LocationTypeName values (i.e. known etter type names or categories),
  catching any typos or stale keys at test time rather than at runtime.
"""

import typing

import pytest

from etter.datasources import LocationTypeName, TypeMap
from etter.datasources.ign_bdcarto import IGN_BDCARTO_TYPE_MAP, _build_type_map
from etter.datasources.location_types import ALL_CATEGORIES, ALL_TYPES
from etter.datasources.swissnames3d import OBJEKTART_TYPE_MAP

# The complete set of valid etter type names: concrete types + category names.
_VALID_NAMES: frozenset[str] = frozenset(ALL_TYPES) | frozenset(ALL_CATEGORIES)


class TestLocationTypeNameAlias:
    """Verify the LocationTypeName Literal type is correctly defined."""

    def test_importable(self) -> None:
        assert LocationTypeName is not None

    def test_is_literal(self) -> None:
        """LocationTypeName must be a Literal type."""
        origin = typing.get_origin(LocationTypeName)
        assert origin is typing.Literal

    def test_literal_args_match_valid_names(self) -> None:
        """All args of the Literal must be in ALL_TYPES | ALL_CATEGORIES."""
        literal_args = set(typing.get_args(LocationTypeName))
        unknown = literal_args - _VALID_NAMES
        assert not unknown, f"LocationTypeName contains values not present in location_types: {sorted(unknown)}"

    def test_all_valid_names_covered(self) -> None:
        """Every name in ALL_TYPES and ALL_CATEGORIES must appear in the Literal."""
        literal_args = set(typing.get_args(LocationTypeName))
        missing = _VALID_NAMES - literal_args
        assert not missing, f"LocationTypeName is missing values from location_types: {sorted(missing)}"


class TestTypeMapAlias:
    """Verify the TypeMap alias is correctly defined."""

    def test_importable(self) -> None:
        assert TypeMap is not None


class TestObjekartTypeMapKeys:
    """All keys of OBJEKTART_TYPE_MAP must be valid LocationTypeName values."""

    @pytest.mark.parametrize("key", list(OBJEKTART_TYPE_MAP.keys()))
    def test_key_is_valid_location_type_name(self, key: str) -> None:
        assert key in _VALID_NAMES, (
            f"OBJEKTART_TYPE_MAP key {key!r} is not a known etter type name or category. "
            f"Valid names are: {sorted(_VALID_NAMES)}"
        )

    def test_values_are_non_empty_lists(self) -> None:
        for key, values in OBJEKTART_TYPE_MAP.items():
            assert isinstance(values, list) and len(values) > 0, (
                f"OBJEKTART_TYPE_MAP[{key!r}] must be a non-empty list, got {values!r}"
            )


class TestIgnBdcartoTypeMapKeys:
    """All keys of IGN_BDCARTO_TYPE_MAP must be valid LocationTypeName values."""

    @pytest.mark.parametrize("key", list(IGN_BDCARTO_TYPE_MAP.keys()))
    def test_key_is_valid_location_type_name(self, key: str) -> None:
        assert key in _VALID_NAMES, (
            f"IGN_BDCARTO_TYPE_MAP key {key!r} is not a known etter type name or category. "
            f"Valid names are: {sorted(_VALID_NAMES)}"
        )

    def test_values_are_non_empty_lists(self) -> None:
        for key, values in IGN_BDCARTO_TYPE_MAP.items():
            assert isinstance(values, list) and len(values) > 0, (
                f"IGN_BDCARTO_TYPE_MAP[{key!r}] must be a non-empty list, got {values!r}"
            )

    def test_no_duplicate_values(self) -> None:
        """Regression: shared fixed_type across layers must not produce duplicate raw values.

        _build_type_map() deduplicates fixed_type entries so that types shared by
        multiple layers (e.g. "arrondissement" used by both "arrondissement" and
        "arrondissement_municipal") appear only once in the value list.  Without the
        deduplication guard the SQL IN clause would contain repeated placeholders,
        producing incorrect query behaviour.
        """
        for key, values in IGN_BDCARTO_TYPE_MAP.items():
            assert len(values) == len(set(values)), f"IGN_BDCARTO_TYPE_MAP[{key!r}] contains duplicate values: {values}"

    def test_commune_flags_types_present(self) -> None:
        """Regression: commune_flags layers must contribute 'city' and 'municipality' to the map.

        The 'commune' layer uses commune_flags instead of fixed_type or type_map.
        _build_type_map() must handle this branch explicitly; without it 'city' is
        silently absent from IGN_BDCARTO_TYPE_MAP even though the datasource produces
        city features at runtime.
        """
        assert "city" in IGN_BDCARTO_TYPE_MAP, (
            "'city' is missing from IGN_BDCARTO_TYPE_MAP commune_flags branch "
            "in _build_type_map() may have been removed or broken"
        )
        assert "municipality" in IGN_BDCARTO_TYPE_MAP, "'municipality' is missing from IGN_BDCARTO_TYPE_MAP"

    def test_build_type_map_output_matches_typemap_structure(self) -> None:
        """_build_type_map() output must conform to TypeMap at runtime."""
        result = _build_type_map()
        valid_keys = frozenset(typing.get_args(LocationTypeName))

        assert isinstance(result, dict), "_build_type_map() must return a dict"
        for key, values in result.items():
            assert key in valid_keys, (
                f"_build_type_map() produced key {key!r} which is not a valid "
                f"LocationTypeName the cast(TypeMap, ...) would silently lie"
            )
            assert isinstance(values, list) and len(values) > 0, (
                f"_build_type_map() produced a non-list or empty list for key {key!r}: {values!r}"
            )
            assert all(isinstance(v, str) for v in values), (
                f"_build_type_map() produced non-string values for key {key!r}: {values!r}"
            )
