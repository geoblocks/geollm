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
from etter.datasources.ign_bdcarto import IGN_BDCARTO_TYPE_MAP
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
