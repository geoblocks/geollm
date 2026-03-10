"""
Composite data source that aggregates results from multiple GeoDataSource instances.

Queries are forwarded to every registered source and results are merged,
deduplicating by (name, type) while preserving original ordering.
"""

from typing import Any

from .protocol import GeoDataSource


class CompositeDataSource:
    """
    Fan-out datasource that delegates to an ordered list of GeoDataSource instances.

    ``search`` queries every registered source and merges results in order,
    de-duplicating by ``(name, type)`` so that the same place appearing in
    multiple sources is only returned once (first-wins).

    ``get_by_id`` tries each source in order and returns the first hit.

    ``get_available_types`` returns the union of all sources' types.

    Args:
        sources: One or more GeoDataSource instances.

    Example:
        >>> swiss = SwissNames3DSource("data/")
        >>> ign   = IGNBDTopoSource("data/")
        >>> combo = CompositeDataSource(swiss, ign)
        >>> results = combo.search("Geneva", type="city")
    """

    def __init__(self, *sources: GeoDataSource) -> None:
        if not sources:
            raise ValueError("At least one datasource is required.")
        self._sources: list[GeoDataSource] = list(sources)

    # ------------------------------------------------------------------
    # Public API (mirrors GeoDataSource protocol)
    # ------------------------------------------------------------------

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search all registered sources and return merged, deduplicated results.

        Args:
            name: Location name to search for.
            type: Optional type hint passed through to every source.
            max_results: Maximum total results to return.

        Returns:
            List of GeoJSON Feature dicts, merged from all sources.
        """
        seen: set[tuple[str, str]] = set()
        merged: list[dict[str, Any]] = []

        for source in self._sources:
            for feature in source.search(name, type=type, max_results=max_results):
                props = feature.get("properties", {})
                key = (
                    str(props.get("name", "")).lower(),
                    str(props.get("type", "")),
                )
                if key not in seen:
                    seen.add(key)
                    merged.append(feature)
                    if len(merged) >= max_results:
                        return merged

        return merged

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a feature by ID, trying each source in order.

        Args:
            feature_id: Unique identifier to look up.

        Returns:
            The first matching GeoJSON Feature dict, or None.
        """
        for source in self._sources:
            result = source.get_by_id(feature_id)
            if result is not None:
                return result
        return None

    def get_available_types(self) -> list[str]:
        """
        Return the union of all sources' available types, sorted.

        Returns:
            Sorted list of unique type strings.
        """
        types: set[str] = set()
        for source in self._sources:
            types.update(source.get_available_types())
        return sorted(types)
