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
import pyproj
from rapidfuzz import fuzz
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

# CH1903+ (LV95) to WGS84 transformer - data is assumed to always be in EPSG:2056
_TRANSFORMER = pyproj.Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)

# Map normalized, grouped types to their OBJEKTART values.
# Each type groups related OBJEKTART values (e.g., lake groups: See, Seeteil, Stausee).
# This reduces cardinality while preserving semantic meaning and traceability.
OBJEKTART_TYPE_MAP: dict[str, list[str]] = {
    # Water bodies
    "lake": ["See", "Seeteil", "Stausee"],
    "island": ["Seeinsel", "Insel"],
    "pond": ["Weiher"],
    "river": ["Fliessgewaesser"],
    "ditch": ["Graben"],
    "spring": ["Quelle"],
    "waterfall": ["Wasserfall"],
    "glacier": ["Gletscher"],
    "weir": ["Wehr"],
    "dam": ["Staumauer", "Staudamm"],
    # Landforms
    "mountain": ["Berg"],
    "peak": ["Gipfel", "Hauptgipfel", "Alpiner Gipfel"],
    "hill": ["Huegel", "Haupthuegel", "Huegelzug"],
    "pass": ["Pass", "Strassenpass"],
    "valley": ["Tal", "Haupttal"],
    "plain": ["Ebene"],
    "rock_head": ["Felskopf"],
    "boulder": ["Felsblock", "Erratischer Block"],
    "ridge": ["Grat"],
    "massif": ["Massiv"],
    "peninsula": ["Halbinsel"],
    "cave": ["Grotte, Hoehle"],
    # Populated places
    "city": ["Ort"],
    "district": ["Ortsteil", "Quartier", "Quartierteil", "Bezirk"],
    "hamlet": ["Weiler"],
    # Buildings
    "building": ["Einzelhaus", "Gebaeude", "Offenes Gebaeude"],
    "religious_building": ["Sakrales Gebaeude", "Kapelle"],
    "tower": ["Turm"],
    "monument": ["Denkmal", "Bildstock"],
    "fountain": ["Brunnen"],
    # Administrative
    "region": ["Landschaftsname", "Grossregion"],
    "area": ["Gebiet"],
    "border_marker": ["Landesgrenzstein"],
    # Transport - Stops & Stations
    "train_station": ["Haltestelle Bahn", "Haltestelle_Bahn"],
    "bus_stop": ["Haltestelle Bus", "Haltestelle_Bus"],
    "boat_stop": ["Haltestelle Schiff"],
    # Transport - Roads
    "road": ["Strasse"],
    "bridge": ["Bruecke"],
    "tunnel": ["Tunnel"],
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
    "airport": ["Flugplatz", "Flugplatzareal", "Flugfeldareal", "Flughafenareal"],
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
    "forest": ["Wald"],
    "nature_reserve": ["Naturschutzgebiet"],
    "alpine_pasture": ["Alp"],
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

    def _ensure_loaded(self) -> None:
        """Load data lazily on first access."""
        if self._gdf is not None:
            return
        self._load_data()

    def _load_data(self) -> None:
        """Load SwissNames3D data and build the name index."""
        # Check if data_path is a directory
        if self._data_path.is_dir():
            self._load_from_directory()
        else:
            # Load single file
            kwargs: dict[str, Any] = {}
            if self._layer is not None:
                kwargs["layer"] = self._layer
            self._gdf = gpd.read_file(str(self._data_path), **kwargs)

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
        self._gdf = gpd.GeoDataFrame(
            gpd.pd.concat(gdfs_filtered, ignore_index=True), crs=gdfs[0].crs, geometry="geometry"
        )

    def _build_name_index(self) -> None:
        """Build a normalized name → row indices lookup for fast search."""
        assert self._gdf is not None
        self._name_index = {}

        name_col = self._detect_name_column()
        for idx, name in enumerate(self._gdf[name_col]):
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = _normalize_name(name)
            if normalized not in self._name_index:
                self._name_index[normalized] = []
            self._name_index[normalized].append(idx)

    def _detect_name_column(self) -> str:
        """Detect the name column in the data."""
        assert self._gdf is not None
        for candidate in ("NAME", "name", "Name", "BEZEICHNUNG"):
            if candidate in self._gdf.columns:
                return candidate
        raise ValueError(f"Cannot find name column in data. Available columns: {list(self._gdf.columns)}")

    def _detect_type_column(self) -> str | None:
        """Detect the feature type column in the data."""
        assert self._gdf is not None
        for candidate in ("OBJEKTART", "objektart", "Objektart"):
            if candidate in self._gdf.columns:
                return candidate
        return None

    def _detect_id_column(self) -> str | None:
        """Detect the unique ID column in the data."""
        assert self._gdf is not None
        for candidate in ("UUID", "uuid", "FID", "OBJECTID", "id"):
            if candidate in self._gdf.columns:
                return candidate
        return None

    def _row_to_feature(self, idx: int) -> dict[str, Any]:
        """Convert a GeoDataFrame row to a GeoJSON Feature dict with WGS84 geometry."""
        assert self._gdf is not None
        row = self._gdf.iloc[idx]

        # Get name
        name_col = self._detect_name_column()
        name = str(row[name_col])

        # Get type
        type_col = self._detect_type_column()
        raw_type = str(row[type_col]) if type_col and row.get(type_col) else "unknown"
        normalized_type = _objektart_to_type(raw_type)

        # Get ID
        id_col = self._detect_id_column()
        feature_id = str(row[id_col]) if id_col and row.get(id_col) else str(idx)

        # Convert geometry to WGS84 GeoJSON
        geom = row.geometry
        if geom is None or geom.is_empty:
            geometry = {"type": "Point", "coordinates": [0, 0]}
            bbox = None
        else:
            # Transform geometry from EPSG:2056 to WGS84 using the module-level transformer
            wgs84_geom = shapely_transform(_TRANSFORMER.transform, geom)
            geometry = mapping(wgs84_geom)
            bounds = wgs84_geom.bounds  # (minx, miny, maxx, maxy)
            bbox = (bounds[0], bounds[1], bounds[2], bounds[3])

        # Collect extra properties
        skip_cols = {name_col, "geometry"}
        if type_col:
            skip_cols.add(type_col)
        if id_col:
            skip_cols.add(id_col)

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

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
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

        # Filter by type if type hint provided
        if type is not None:
            normalized_type = type.lower()
            features = [f for f in features if f["properties"].get("type") == normalized_type]

        return features[:max_results]

    def _fuzzy_search(self, normalized: str, threshold: float = 75.0) -> list[int]:
        """
        Fuzzy search for names that partially match the search query.

        Uses token matching to find results where at least one token from the
        query matches a token in the indexed name. This handles cases like:
        - "venoge" matching "la venoge"
        - "rhone" matching "rhone valais"

        Args:
            normalized: The normalized search query.
            threshold: Minimum fuzzy match score (0-100) to include a result.

        Returns:
            List of row indices for fuzzy-matched names, sorted by score (descending).
        """
        matches: list[tuple[int, float]] = []
        query_tokens = set(normalized.split())

        for indexed_name, indices in self._name_index.items():
            indexed_tokens = set(indexed_name.split())

            # Check if any query token matches any indexed token
            token_overlap = query_tokens & indexed_tokens

            if token_overlap:
                # Also use token_set_ratio for better matching of partial strings
                score = fuzz.token_set_ratio(normalized, indexed_name)
                if score >= threshold:
                    for idx in indices:
                        matches.append((idx, score))

        # Sort by score (descending) to return best matches first
        matches.sort(key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in matches]

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a specific feature by its unique identifier.

        Args:
            feature_id: Unique identifier (UUID or row index).

        Returns:
            The matching GeoJSON Feature dict, or None if not found.
        """
        self._ensure_loaded()
        assert self._gdf is not None

        id_col = self._detect_id_column()
        if id_col:
            matches = self._gdf[self._gdf[id_col].astype(str) == feature_id]
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
