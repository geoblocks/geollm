"""
IGN BD-TOPO data source implementation.

Loads French administrative geographic data from IGN's BD-TOPO dataset and provides
search functionality. Data is already in WGS84 (EPSG:4326), so no coordinate
transformation is required.

Data source: https://geoservices.ign.fr/bdtopo

Supported files (auto-detected in directory):
  - IGNF_BD-TOPO_COMMUNE.shp       - French municipalities (polygon)
  - IGNF_BD-TOPO_CHEF_LIEU.shp     - Administrative capitals / chief towns (point)
  - IGNF_BD-TOPO_ARRONDISSEMENT.shp - Urban arrondissements (polygon)
"""

import unicodedata
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz
from shapely.geometry import mapping

from .location_types import get_matching_types

# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

# Maps normalized type names to their NATURE (CHEF_LIEU) / STATUT (COMMUNE) raw values.
# The same raw values appear in both columns, so one map covers both.
#
# All place-level statuses (capital, préfecture, etc.) are normalized to "city" because they
# are standard settlements in the geographic sense — the administrative label is preserved
# as the raw STATUT / NATURE property on each returned feature for downstream filtering.
NATURE_TYPE_MAP: dict[str, list[str]] = {
    "city": ["Capitale d'état", "Préfecture de région", "Préfecture", "Sous-préfecture"],
    "municipality": ["Commune simple", "Commune"],
}

# Configuration for each supported shapefile:
#   type_col   - column that holds the raw type value (or None)
#   fixed_type - constant type to use when there is no type column
_FILE_CONFIGS: dict[str, dict[str, str | None]] = {
    "IGNF_BD-TOPO_COMMUNE": {
        "type_col": "STATUT",
        "fixed_type": None,
    },
    "IGNF_BD-TOPO_CHEF_LIEU": {
        "type_col": "NATURE",
        "fixed_type": None,
    },
    "IGNF_BD-TOPO_ARRONDISSEMENT": {
        "type_col": None,
        "fixed_type": "arrondissement",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nature_to_type(raw: str) -> str:
    """
    Convert a NATURE or STATUT raw value to a normalized type string.

    Args:
        raw: Raw NATURE or STATUT value from the IGN data.

    Returns:
        Normalized type (e.g. "prefecture", "municipality").
        Falls back to a slugified version of the raw value if not found.
    """
    for type_name, values in NATURE_TYPE_MAP.items():
        if raw in values:
            return type_name
    return raw.lower().replace(" ", "_").replace("'", "")


def _normalize_name(name: str) -> str:
    """
    Normalize a name for case-insensitive, accent-insensitive matching.

    Strips diacritics (é→e, ç→c, etc.) and lowercases.
    """
    nfkd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


# ---------------------------------------------------------------------------
# Data source class
# ---------------------------------------------------------------------------


class IGNBDTopoSource:
    """
    Geographic data source backed by IGN's BD-TOPO dataset.

    Loads French administrative geographic data from a directory that contains
    one or more of the standard IGN BD-TOPO shapefiles:

    * ``IGNF_BD-TOPO_COMMUNE.shp``        - municipalities
    * ``IGNF_BD-TOPO_CHEF_LIEU.shp``      - administrative capitals / chief towns
    * ``IGNF_BD-TOPO_ARRONDISSEMENT.shp`` - urban arrondissements

    All geometries are returned as GeoJSON in WGS84 (EPSG:4326); the source
    data is already projected in that CRS so no reprojection is needed.

    Internally, a unified ``_normalized_type`` column is derived during loading
    so that type-based filtering works consistently regardless of which source
    file a feature originated from.

    Args:
        data_path: Path to a directory containing the IGN BD-TOPO shapefiles.

    Example:
        >>> source = IGNBDTopoSource("data/")
        >>> results = source.search("Paris", type="capital")
        >>> results = source.search("Lyon", type="administrative")
        >>> print(results[0]["geometry"])  # GeoJSON in WGS84
    """

    # Name of the synthetic type column added at load time.
    _TYPE_COL = "_normalized_type"

    def __init__(self, data_path: str | Path) -> None:
        self._data_path = Path(data_path)
        self._gdf: gpd.GeoDataFrame | None = None
        self._name_index: dict[str, list[int]] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load data lazily on first access."""
        if self._gdf is not None:
            return
        self._load_data()

    def _load_data(self) -> None:
        """Load all available IGN BD-TOPO shapefiles and build the name index."""
        self._gdf = self._load_from_directory()
        self._build_name_index()

    def _load_from_directory(self) -> gpd.GeoDataFrame:
        """
        Detect and load all supported shapefiles from *data_path*.

        Returns a single concatenated GeoDataFrame with a unified
        ``_normalized_type`` column.
        """
        gdfs: list[gpd.GeoDataFrame] = []

        for filename, cfg in _FILE_CONFIGS.items():
            shp_path = self._data_path / f"{filename}.shp"
            if not shp_path.exists():
                continue

            gdf = gpd.read_file(str(shp_path))

            # Derive the normalized type for every row in this file.
            type_col: str | None = cfg["type_col"]  # type: ignore[assignment]
            fixed_type: str | None = cfg["fixed_type"]  # type: ignore[assignment]

            if fixed_type is not None:
                gdf[self._TYPE_COL] = fixed_type
            elif type_col and type_col in gdf.columns:
                gdf[self._TYPE_COL] = gdf[type_col].apply(
                    lambda v: _nature_to_type(str(v)) if pd.notna(v) else "unknown"
                )
            else:
                gdf[self._TYPE_COL] = "unknown"

            gdfs.append(gdf)

        if not gdfs:
            raise ValueError(
                f"No IGN BD-TOPO shapefiles found in {self._data_path}. "
                f"Expected one or more of: {', '.join(_FILE_CONFIGS.keys())}"
            )

        # Concatenate with an outer join so that all columns are preserved;
        # missing values for columns not present in a given file become NaN.
        combined = pd.concat(gdfs, ignore_index=True)
        return gpd.GeoDataFrame(combined, crs=gdfs[0].crs, geometry="geometry")

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _build_name_index(self) -> None:
        """Build a normalized name → row indices lookup for fast search."""
        assert self._gdf is not None
        self._name_index = {}

        for idx, name in enumerate(self._gdf["NOM"]):
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = _normalize_name(name)
            if normalized not in self._name_index:
                self._name_index[normalized] = []
            self._name_index[normalized].append(idx)

    # ------------------------------------------------------------------
    # Feature conversion
    # ------------------------------------------------------------------

    def _row_to_feature(self, idx: int) -> dict[str, Any]:
        """Convert a GeoDataFrame row to a GeoJSON Feature dict."""
        assert self._gdf is not None
        row = self._gdf.iloc[idx]

        name = str(row["NOM"])
        normalized_type = str(row[self._TYPE_COL]) if pd.notna(row.get(self._TYPE_COL)) else "unknown"
        feature_id = str(row["ID"]) if pd.notna(row.get("ID")) else str(idx)

        # Geometry - data is already in WGS84, just convert to GeoJSON dict.
        geom = row.geometry
        if geom is None or geom.is_empty:
            geometry: dict[str, Any] = {"type": "Point", "coordinates": [0, 0]}
            bbox = None
        else:
            geometry = mapping(geom)
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            bbox: tuple[float, float, float, float] | None = (bounds[0], bounds[1], bounds[2], bounds[3])

        # Extra properties - skip internal/index columns.
        skip_cols = {"NOM", "ID", self._TYPE_COL, "geometry"}
        properties: dict[str, Any] = {
            "name": name,
            "type": normalized_type,
            "confidence": 1.0,
        }
        for col in self._gdf.columns:
            if col not in skip_cols:
                val = row.get(col)
                if val is not None and str(val) != "nan":
                    properties[col] = val

        return {
            "type": "Feature",
            "id": feature_id,
            "geometry": geometry,
            "bbox": bbox,
            "properties": properties,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for geographic features by name.

        Uses case-insensitive, accent-normalized matching with fuzzy fallback.
        First tries exact matching, then falls back to fuzzy matching if no
        exact matches are found.

        Args:
            name: Location name to search for (e.g. "Paris", "Lyon 6e Arrondissement").
            type: Optional type hint for filtering results.
                  Examples: "prefecture", "municipality", "arrondissement",
                  "administrative" (matches all administrative types).
            max_results: Maximum number of results to return.

        Returns:
            List of GeoJSON Feature dicts. Empty list if no matches found.
        """
        self._ensure_loaded()

        normalized = _normalize_name(name)
        indices = self._name_index.get(normalized, [])

        if not indices:
            indices = self._fuzzy_search(normalized)

        features = [self._row_to_feature(idx) for idx in indices]

        if type is not None:
            matching_types = get_matching_types(type)
            if matching_types:
                features = [f for f in features if f["properties"].get("type") in matching_types]
            else:
                features = [f for f in features if f["properties"].get("type") == type.lower()]

        return features[:max_results]

    def _fuzzy_search(self, normalized: str, threshold: float = 75.0) -> list[int]:
        """
        Fuzzy search using token overlap and token_set_ratio scoring.

        Works for partial names such as:
        * "lyon" matching "Lyon 6e Arrondissement"
        * "prefecture" not involved - only name-based

        Args:
            normalized: The normalized search query.
            threshold: Minimum fuzzy match score (0-100).

        Returns:
            List of row indices sorted by score descending.
        """
        matches: list[tuple[int, float]] = []
        query_tokens = set(normalized.split())

        for indexed_name, indices in self._name_index.items():
            indexed_tokens = set(indexed_name.split())
            if query_tokens & indexed_tokens:
                score = fuzz.token_set_ratio(normalized, indexed_name)
                if score >= threshold:
                    for idx in indices:
                        matches.append((idx, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in matches]

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a specific feature by its unique identifier.

        Args:
            feature_id: The ``ID`` value from the IGN data, or a row index.

        Returns:
            The matching GeoJSON Feature dict, or ``None`` if not found.
        """
        self._ensure_loaded()
        assert self._gdf is not None

        if "ID" in self._gdf.columns:
            matches = self._gdf[self._gdf["ID"].astype(str) == feature_id]
            if not matches.empty:
                return self._row_to_feature(matches.index[0])

        try:
            idx = int(feature_id)
            if 0 <= idx < len(self._gdf):
                return self._row_to_feature(idx)
        except ValueError:
            pass

        return None

    def get_available_types(self) -> list[str]:
        """
        Return all normalized geographic types this datasource can return.

        Returns:
            Sorted list of type strings: ``["arrondissement", "city", "municipality"]``.
        """
        return sorted(set(NATURE_TYPE_MAP.keys()) | {"arrondissement"})
