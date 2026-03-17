"""
Protocol definition for geographic data sources.

Any class implementing this Protocol can be used as a datasource,
without needing to inherit from a base class (structural typing).
"""

from typing import Any, Protocol


class GeoDataSource(Protocol):
    """
    Protocol for geographic data sources.

    Implementations resolve location names to geographic features.
    Features are returned as standard GeoJSON Feature objects (dicts) in WGS84 (EPSG:4326).

    Example of returned feature:
        {
            "type": "Feature",
            "id": "uuid-123",
            "geometry": {"type": "Point", "coordinates": [8.5, 47.3]},
            "bbox": [8.4, 47.3, 8.6, 47.4],
            "properties": {
                "name": "Zürich",
                "type": "city",
                "confidence": 1.0,
                ...
            }
        }
    """

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for geographic features by name.

        Args:
            name: Location name to search for (e.g., "Lake Geneva", "Bern").
            type: Optional type hint for filtering/ranking results.
                  Examples: "lake", "city", "mountain", "canton", "river".
                  When provided, matching types are ranked higher.
            max_results: Maximum number of results to return.

        Returns:
            List of matching GeoJSON Feature dicts, ranked by relevance.
            Returns empty list if no matches found.
        """
        ...

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a specific feature by its unique identifier.

        Args:
            feature_id: Unique identifier from the data source.

        Returns:
            The matching GeoJSON Feature dict, or None if not found.
        """
        ...

    def get_available_types(self) -> list[str]:
        """
        Get list of concrete geographic types this datasource can return.

        Returns a list of concrete type values (e.g., "lake", "city", "restaurant")
        that this datasource uses in the "type" property of returned features.
        These types can be matched against the location type hierarchy for fuzzy matching.

        The returned types should be a subset of or mapped to the standard location
        type hierarchy defined in location_types.TYPE_HIERARCHY.

        Returns:
            List of concrete type strings (e.g., ["lake", "river", "city", "mountain"]).
            Empty list if this datasource does not provide type information.

        Example:
            >>> source = SwissNames3DSource("data/")
            >>> types = source.get_available_types()
            >>> print(types)
            ['lake', 'river', 'city', 'mountain', 'peak', 'hill', ...]
        """
        ...
