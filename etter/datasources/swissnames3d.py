"""
SwissNames3D data source implementation.

Loads geographic names from swisstopo's swissNAMES3D dataset and provides
search functionality with coordinate conversion to WGS84 GeoJSON.

Data source: https://www.swisstopo.admin.ch/en/landscape-model-swissnames3d
"""

import unicodedata
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from geojson import Feature
from rapidfuzz import fuzz
from shapely import force_2d
from shapely.geometry import mapping

from .location_types import TypeMap, get_matching_types

# Map normalized, grouped types to their OBJEKTART values.
# Each type groups related OBJEKTART values (e.g., lake groups: See, Seeteil).
# This reduces cardinality while preserving semantic meaning and traceability.
# Based on swissNAMES3D 2025 (https://www.swisstopo.admin.ch/en/landscape-model-swissnames3d).
OBJEKTART_TYPE_MAP: TypeMap = {
    # Water bodies
    "lake": ["See", "Seeteil"],
    "island": ["Seeinsel"],
    "river": ["Fliessgewaesser"],
    "ditch": ["Graben"],
    "spring": ["Quelle"],
    "waterfall": ["Wasserfall"],
    "glacier": ["Gletscher"],
    "weir": ["Wehr"],
    "dam": ["Staumauer", "Staudamm"],
    # Landforms
    "peak": ["Gipfel", "Hauptgipfel", "Alpiner Gipfel"],
    "hill": ["Huegel", "Haupthuegel", "Huegelzug"],
    "pass": ["Pass", "Strassenpass"],
    "valley": ["Tal", "Haupttal"],
    "rock_head": ["Felskopf"],
    "boulder": ["Felsblock", "Erratischer Block"],
    "ridge": ["Grat"],
    "massif": ["Massiv"],
    "cave": ["Grotte, Hoehle"],  # single OBJEKTART value with comma, not two separate values
    # Populated places
    "city": ["Ort"],
    "district": ["Ortsteil", "Quartier", "Quartierteil"],
    # Buildings
    "building": ["Gebaeude", "Offenes Gebaeude"],
    "religious_building": ["Sakrales Gebaeude", "Kapelle"],
    "tower": ["Turm"],
    "monument": ["Denkmal", "Bildstock"],
    "fountain": ["Brunnen"],
    # Administrative
    "region": ["Landschaftsname", "Grossregion"],
    "area": ["Gebiet"],
    "border_marker": ["Landesgrenzstein"],
    # Transport - Stops & Stations
    "train_station": ["Haltestelle Bahn"],
    "bus_stop": ["Haltestelle Bus"],
    "boat_stop": ["Haltestelle Schiff"],
    # Transport - Roads
    "road": ["Strasse"],
    "exit": ["Ausfahrt"],
    "entrance_exit": ["Ein- und Ausfahrt"],
    "junction": ["Verzweigung"],
    # Transport - Railways
    "railway": ["Normalspur", "Schmalspur", "Schmalspur mit Normalspur", "Kleinbahn", "Uebrige Bahnen"],
    "railway_area": ["Gleisareal"],
    # Transport - Cable Cars & Lifts
    "lift": ["Luftseilbahn", "Gondelbahn", "Sesselbahn", "Skilift", "Transportseil"],
    "loading_station": ["Verladestation"],
    # Transport - Airports
    "airport": ["Flugplatzareal", "Flugfeldareal", "Flughafenareal"],
    "heliport": ["Heliport"],
    # Transport - Ferries
    "ferry": ["Personenfaehre mit Seil", "Personenfaehre ohne Seil", "Autofaehre"],
    # Areas - Recreational
    "park": ["Oeffentliches Parkareal"],
    "swimming_pool": ["Schwimmbadareal"],
    "sports_facility": [
        "Sportplatzareal",
        "Golfplatzareal",
        "Rodelbahn",
        "Bobbahn",
        "Skisprungschanze",
        "Pferderennbahnareal",
    ],
    "leisure_facility": ["Freizeitanlagenareal"],
    "zoo": ["Zooareal"],
    # Areas - Public Services
    "parking": ["Oeffentliches Parkplatzareal"],
    "camping": ["Campingplatzareal"],
    "standing_area": ["Standplatzareal"],
    "rest_area": ["Rastplatzareal"],
    "school": ["Schul- und Hochschulareal"],
    "hospital": ["Spitalareal"],
    "cemetery": ["Friedhof"],
    "fairground": ["Messeareal"],
    # Areas - Historical & Cultural
    "historical_site": ["Historisches Areal"],
    "monastery": ["Klosterareal"],
    # Areas - Infrastructure
    "power_plant": ["Kraftwerkareal"],
    "wastewater_treatment": ["Abwasserreinigungsareal"],
    "waste_incineration": ["Kehrichtverbrennungsareal"],
    "landfill": ["Deponieareal"],
    "quarry": ["Abbauareal"],
    # Areas - Other
    "private_driving_area": ["Privates Fahrareal"],
    "correctional_facility": ["Massnahmenvollzugsanstaltsareal"],
    "military_training_area": ["Truppenuebungsplatz"],
    "customs": ["Zollamt 24h 24h", "Zollamt 24h eingeschraenkt", "Zollamt eingeschraenkt"],
    # Nature
    "field_name": ["Flurname swisstopo"],
    "local_name": ["Lokalname swisstopo"],
    # Points of Interest
    "viewpoint": ["Aussichtspunkt"],
}


def _objektart_to_type(objektart: str) -> str:
    """
    Convert OBJEKTART value to normalized type.

    Searches through OBJEKTART_TYPE_MAP to find which type the OBJEKTART belongs to.
    Falls back to lowercased raw value if not found.

    Args:
        objektart: Raw OBJEKTART value from SwissNames3D data

    Returns:
        Normalized type string (e.g., "lake", "city", "mountain")
    """
    for type_name, objektart_values in OBJEKTART_TYPE_MAP.items():
        if objektart in objektart_values:
            return type_name
    # Fallback: return lowercased raw value if not found
    return objektart.lower()


def _normalize_name(name: str) -> str:
    """
    Normalize a name for case-insensitive, accent-insensitive matching.

    Strips diacritics (é→e, ü→u, etc.) and lowercases.
    """
    # Decompose unicode characters (é → e + combining accent)
    nfkd = unicodedata.normalize("NFKD", name)
    # Strip combining characters (accents, umlauts, etc.)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


class SwissNames3DSource:
    """
    Geographic data source backed by swisstopo's swissNAMES3D dataset.

    Loads geographic names from a Shapefile, GeoPackage, or ESRI File Geodatabase
    and provides search by name with optional type filtering.

    If data_path is a directory, automatically loads and concatenates all SwissNames3D
    shapefiles (swissNAMES3D_PKT, swissNAMES3D_LIN, swissNAMES3D_PLY) found within.

    All geometries are returned as GeoJSON in WGS84 (EPSG:4326).

    Args:
        data_path: Path to SwissNames3D data file or directory containing SwissNames3D shapefiles.
        layer: Layer name within the data source (for multi-layer formats like GDB).

    Example:
        >>> source = SwissNames3DSource("data/")  # Load all 3 geometry types
        >>> results = source.search("Lac Léman", type="lake")
        >>> print(results[0].geometry)  # GeoJSON in WGS84
    """

    def __init__(self, data_path: str | Path, layer: str | None = None) -> None:
        self._data_path = Path(data_path)
        self._layer = layer
        self._gdf: gpd.GeoDataFrame | None = None
        self._name_index: dict[str, list[int]] = {}
        self._token_index: dict[str, set[str]] = {}
        self._name_col: str = ""
        self._type_col: str | None = None
        self._id_col: str | None = None
        self._extra_cols: list[str] = []

    def preload(self) -> None:
        """Eagerly load data. Call at startup to avoid first-query latency."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        """Load data lazily on first access."""
        if self._gdf is not None:
            return
        self._load_data()

    def _load_data(self) -> None:
        """Load SwissNames3D data and build the name index."""
        if self._data_path.is_dir():
            self._load_from_directory()
        else:
            kwargs: dict[str, Any] = {}
            if self._layer is not None:
                kwargs["layer"] = self._layer
            self._gdf = gpd.read_file(str(self._data_path), **kwargs)

        assert self._gdf is not None

        # Drop Z coordinates once — vectorized; the source has LN02 height and
        # single_sided buffers reject 3D geometries
        self._gdf.geometry = force_2d(self._gdf.geometry.values)

        # Reproject to WGS84 once — avoids per-query coordinate transform
        self._gdf = self._gdf.to_crs("EPSG:4326")

        # Cache column names once — reused on every _row_to_feature() call
        self._name_col = self._detect_name_column()
        self._type_col = self._detect_type_column()
        self._id_col = self._detect_id_column()
        skip = {self._name_col, "geometry"}
        if self._type_col:
            skip.add(self._type_col)
        if self._id_col:
            skip.add(self._id_col)
        self._extra_cols = [c for c in self._gdf.columns if c not in skip]

        self._build_name_index()

    def _load_from_directory(self) -> None:
        """Load and concatenate all SwissNames3D shapefiles from a directory."""
        # Look for the 3 standard SwissNames3D shapefiles
        shapefile_names = ["swissNAMES3D_PKT", "swissNAMES3D_LIN", "swissNAMES3D_PLY"]
        gdfs: list[gpd.GeoDataFrame] = []

        for name in shapefile_names:
            shp_path = self._data_path / f"{name}.shp"
            if shp_path.exists():
                gdf = gpd.read_file(str(shp_path))
                gdfs.append(gdf)

        if not gdfs:
            raise ValueError(
                f"No SwissNames3D shapefiles found in {self._data_path}. Expected: {', '.join(shapefile_names)}"
            )

        # Find common columns across all loaded GeoDataFrames
        common_cols = set(gdfs[0].columns)
        for gdf in gdfs[1:]:
            common_cols &= set(gdf.columns)

        # Keep only common columns and concatenate
        gdfs_filtered = [gdf[sorted(common_cols)] for gdf in gdfs]
        self._gdf = gpd.GeoDataFrame(pd.concat(gdfs_filtered, ignore_index=True), crs=gdfs[0].crs, geometry="geometry")

    def _build_name_index(self) -> None:
        """Build normalized name → row indices and token → candidate names indexes."""
        assert self._gdf is not None
        self._name_index = {}
        self._token_index = {}

        for idx, name in enumerate(self._gdf[self._name_col]):
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = _normalize_name(name)
            if normalized not in self._name_index:
                self._name_index[normalized] = []
            self._name_index[normalized].append(idx)
            for token in normalized.split():
                if token not in self._token_index:
                    self._token_index[token] = set()
                self._token_index[token].add(normalized)

    def _detect_name_column(self) -> str:
        """Detect the name column in the data."""
        assert self._gdf is not None
        for col in self._gdf.columns:
            if col.upper() in ("NAME", "BEZEICHNUNG"):
                return col
        raise ValueError(f"Cannot find name column in data. Available columns: {list(self._gdf.columns)}")

    def _detect_type_column(self) -> str | None:
        """Detect the feature type column in the data."""
        assert self._gdf is not None
        for col in self._gdf.columns:
            if col.upper() == "OBJEKTART":
                return col
        return None

    def _detect_id_column(self) -> str | None:
        """Detect the unique ID column in the data."""
        assert self._gdf is not None
        for candidate in ("UUID", "FID", "OBJECTID", "ID"):
            for col in self._gdf.columns:
                if col.upper() == candidate:
                    return col
        return None

    def _row_to_feature(self, idx: int) -> Feature:
        """Convert a GeoDataFrame row to a GeoJSON Feature dict with WGS84 geometry."""
        assert self._gdf is not None
        row = self._gdf.iloc[idx]

        name = str(row[self._name_col])

        raw_type = str(row[self._type_col]) if self._type_col and row.get(self._type_col) else "unknown"
        normalized_type = _objektart_to_type(raw_type)

        feature_id = str(row[self._id_col]) if self._id_col and row.get(self._id_col) else str(idx)

        # Geometry is already in WGS84 (2D) — pre-converted at load time
        geom = row.geometry
        if geom is None or geom.is_empty:
            geometry = {"type": "Point", "coordinates": [0, 0]}
            bbox = None
        else:
            geometry = mapping(geom)
            bounds = geom.bounds
            bbox = (bounds[0], bounds[1], bounds[2], bounds[3])

        properties: dict[str, Any] = {
            "name": name,
            "type": normalized_type,
            "confidence": 1.0,
        }
        for col in self._extra_cols:
            val = row.get(col)
            if val is not None and str(val) != "nan":
                properties[col] = val

        return Feature(geometry=geometry, properties=properties, id=feature_id, bbox=bbox)

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[Feature]:
        """
        Search for geographic features by name.

        Uses case-insensitive, accent-normalized matching with fuzzy fallback.
        First tries exact matching, then falls back to fuzzy matching if no exact
        matches found.

        Args:
            name: Location name to search for.
            type: Optional type hint to filter results. If provided, only features
                  of this type are returned.
            max_results: Maximum number of results to return.

        Returns:
            List of matching GeoJSON Feature dicts. If type is provided, only
            features of that type are returned. Empty list if no matches found.
        """
        self._ensure_loaded()

        normalized = _normalize_name(name)
        indices = self._name_index.get(normalized, [])

        # If no exact match, try fuzzy matching
        if not indices:
            indices = self._fuzzy_search(normalized)

        features = [self._row_to_feature(idx) for idx in indices]

        # Filter by type if type hint provided.
        # Expand via the type hierarchy so that category hints (e.g. "water") match
        # all concrete types within that category ("lake", "river", "pond", ...).
        if type is not None:
            matching_types = get_matching_types(type)
            if matching_types:
                features = [f for f in features if f["properties"].get("type") in matching_types]
            else:
                # Unknown type hint, fall back to exact string match
                features = [f for f in features if f["properties"].get("type") == type.lower()]

        return features[:max_results]

    def _fuzzy_search(self, normalized: str, threshold: float = 75.0) -> list[int]:
        """
        Fuzzy search using a token inverted index for fast candidate pre-filtering.

        Looks up each query token in _token_index to find only the indexed names
        that share at least one token, then scores those candidates with
        token_set_ratio. Misses (no shared tokens) return instantly at O(1).
        """
        candidates: set[str] = set()
        for token in normalized.split():
            candidates |= self._token_index.get(token, set())

        matches: list[tuple[int, float]] = []
        for name in candidates:
            score = fuzz.token_set_ratio(normalized, name)
            if score >= threshold:
                for idx in self._name_index[name]:
                    matches.append((idx, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in matches]

    def get_by_id(self, feature_id: str) -> Feature | None:
        """
        Get a specific feature by its unique identifier.

        Args:
            feature_id: Unique identifier (UUID or row index).

        Returns:
            The matching GeoJSON Feature dict, or None if not found.
        """
        self._ensure_loaded()
        assert self._gdf is not None

        if self._id_col:
            matches = self._gdf[self._gdf[self._id_col].astype(str) == feature_id]
            if not matches.empty:
                return self._row_to_feature(matches.index[0])

        # Fallback: try as row index
        try:
            idx = int(feature_id)
            if 0 <= idx < len(self._gdf):
                return self._row_to_feature(idx)
        except ValueError:
            pass

        return None

    def get_available_types(self) -> list[str]:
        """
        Get list of concrete geographic types this datasource can return.

        Returns all normalized types from the OBJEKTART_TYPE_MAP keys,
        representing all possible types that SwissNames3D data can be classified as.

        Returns:
            Sorted list of type strings (e.g., ["lake", "city", "river", ...])
        """
        return sorted(OBJEKTART_TYPE_MAP.keys())
