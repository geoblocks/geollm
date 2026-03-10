"""
IGN BD-CARTO data source implementation.

Loads French geographic data from IGN's BD-CARTO 5.0 dataset (GeoPackage format)
and provides name-based search with type filtering.

All layers are in EPSG:2154 (Lambert-93) and are reprojected to WGS84 on load.

Data source: https://cartes.gouv.fr/rechercher-une-donnee/dataset/IGNF_BD-CARTO

Expected data layout (produced by scripts/extract_bdcarto.sh):
    data/bdcarto/
        commune.gpkg
        departement.gpkg
        region.gpkg
        canton.gpkg
        arrondissement.gpkg
        arrondissement_municipal.gpkg
        collectivite_territoriale.gpkg
        commune_associee_ou_deleguee.gpkg
        cours_d_eau.gpkg
        plan_d_eau.gpkg
        zone_d_habitation.gpkg
        lieu_dit_non_habite.gpkg
        detail_orographique.gpkg
        parc_ou_reserve.gpkg
"""

import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from .location_types import get_matching_types

_PLAN_D_EAU_TYPES: dict[str, str] = {
    "Lac": "lake",
    "Lagune": "lake",
    "Retenue": "lake",
    "Retenue-barrage": "lake",
    "Retenue-digue": "lake",
    "Retenue-bassin portuaire": "lake",
    "Estuaire": "river",
    "Canal": "river",
    "Ecoulement canalisé": "river",
    "Ecoulement naturel": "river",
    "Glacier, névé": "glacier",
    "Mare": "pond",
    "Marais": "pond",
    "Plan d'eau de gravière": "pond",
    "Plan d'eau de mine": "pond",
    "Réservoir-bassin": "pond",
    "Réservoir-bassin d'orage": "pond",
    "Réservoir-bassin piscicole": "pond",
}

_DETAIL_OROGRAPHIQUE_TYPES: dict[str, str] = {
    "Sommet": "peak",
    "Pic": "peak",
    "Volcan": "peak",
    "Montagne": "mountain",
    "Col": "pass",
    "Crête": "ridge",
    "Cap": "peninsula",
    "Vallée": "valley",
    "Gorge": "valley",
    "Cirque": "valley",
    "Dépression": "valley",
    "Plaine": "plain",
    "Ile": "island",
    "Grotte": "cave",
    "Gouffre": "cave",
    "Rochers": "rock_head",
    "Dune": "local_name",
    "Escarpement": "local_name",
    "Isthme": "local_name",
    "Plage": "local_name",
    "Récif": "local_name",
    "Terril": "local_name",
    "Versant": "local_name",
}

_PARC_TYPES: dict[str, str] = {
    "Parc national": "park",
    "Parc naturel marin": "park",
    "Parc naturel régional": "park",
    "Réserve nationale de chasse et de faune sauvage": "nature_reserve",
    "Réserve naturelle": "nature_reserve",
}

_ZONE_HABITATION_TYPES: dict[str, str] = {
    "Quartier": "district",
    "Lieu-dit habité": "hamlet",
    "Château": "local_name",
    "Grange": "local_name",
    "Moulin": "local_name",
    "Ruines": "local_name",
}

_LIEU_DIT_TYPES: dict[str, str] = {
    "Bois": "forest",
    "Arbre": "local_name",
    "Lieu-dit non habité": "local_name",
}

_LAYER_CONFIGS: dict[str, dict[str, Any]] = {
    "commune": {
        "name_col": "nom_officiel",
        "commune_flags": True,  # type derived from chef_lieu_* boolean columns
    },
    "commune_associee_ou_deleguee": {
        "name_col": "nom_officiel",
        "fixed_type": "municipality",
    },
    "departement": {
        "name_col": "nom_officiel",
        "fixed_type": "department",
    },
    "region": {
        "name_col": "nom_officiel",
        "fixed_type": "region",
    },
    "canton": {
        "name_col": "nom_officiel",
        "fixed_type": "canton",
    },
    "arrondissement": {
        "name_col": "nom_officiel",
        "fixed_type": "arrondissement",
    },
    "arrondissement_municipal": {
        "name_col": "nom_officiel",
        "fixed_type": "arrondissement",
    },
    "collectivite_territoriale": {
        "name_col": "nom_officiel",
        "fixed_type": "region",
    },
    "cours_d_eau": {
        "name_col": "toponyme",
        "fixed_type": "river",
    },
    "plan_d_eau": {
        "name_col": "toponyme",
        "type_col": "nature",
        "type_map": _PLAN_D_EAU_TYPES,
    },
    "zone_d_habitation": {
        "name_col": "toponyme",
        "type_col": "nature",
        "type_map": _ZONE_HABITATION_TYPES,
    },
    "lieu_dit_non_habite": {
        "name_col": "toponyme",
        "type_col": "nature",
        "type_map": _LIEU_DIT_TYPES,
    },
    "detail_orographique": {
        "name_col": "toponyme",
        "type_col": "nature",
        "type_map": _DETAIL_OROGRAPHIQUE_TYPES,
    },
    "parc_ou_reserve": {
        "name_col": "toponyme",
        "type_col": "nature",
        "type_map": _PARC_TYPES,
    },
}

_TYPE_COL = "_normalized_type"
_NAME_COL = "_name"


def _normalize_name(name: str) -> str:
    """Lowercase, strip diacritics for accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


_FR_ARTICLES = ("le ", "la ", "les ", "l'", "l'", "de ", "du ", "des ")


def _index_keys(name: str) -> list[str]:
    """
    Return all normalized keys under which *name* should be indexed.

    Always includes the full normalized form.  Also includes a form with any
    leading French article stripped, so that searching for "Rhône" finds
    features stored as "le Rhône".
    """
    full = _normalize_name(name)
    keys = [full]
    for article in _FR_ARTICLES:
        if full.startswith(article):
            stripped = full[len(article) :].strip()
            if stripped and stripped not in keys:
                keys.append(stripped)
            break  # at most one leading article
    return keys


def _to_json_value(val: Any) -> Any:
    """
    Convert a pandas/numpy value to a JSON-serializable Python primitive.

    Returns ``None`` for missing values (NaN, NaT, None) so they are omitted
    from the feature properties.
    """
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, pd.Timestamp):
        return val.isoformat()
    if hasattr(val, "item"):
        return val.item()
    return val


def _commune_type(row: pd.Series) -> str:
    """Derive municipality vs. city from chef-lieu boolean flags."""
    for flag in ("capitale_d_etat", "chef_lieu_de_region", "chef_lieu_de_departement", "chef_lieu_d_arrondissement"):
        if flag in row.index and str(row[flag]).strip().lower() == "true":
            return "city"
    return "municipality"


def _derive_type(row: pd.Series, cfg: dict[str, Any]) -> str:
    """Return the normalized type for a single row given its layer config."""
    if cfg.get("commune_flags"):
        return _commune_type(row)
    if cfg.get("fixed_type"):
        return cfg["fixed_type"]
    type_col: str | None = cfg.get("type_col")
    type_map: dict[str, str] | None = cfg.get("type_map")
    if type_col and type_map:
        raw = str(row.get(type_col, "")) if pd.notna(row.get(type_col)) else ""
        return type_map.get(raw, "unknown")
    return "unknown"


_MERGE_TYPES: frozenset[str] = frozenset(
    [
        # Hydrography
        "river",
        "lake",
        "pond",
        "glacier",
        # Landforms
        "mountain",
        "peak",
        "ridge",
        "valley",
        "plain",
        "massif",
        "pass",
        # Protected areas / forests
        "park",
        "nature_reserve",
        "forest",
        # Transport linear features
        "road",
        "railway",
        "bridge",
        "tunnel",
    ]
)


def _merge_segments(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge features that share the same (name, type) by unioning their geometries,
    but only for types listed in ``_MERGE_TYPES``.

    Rivers, ridges and other continuous geographic features in BD-CARTO are
    often split into many individual segments.  When the caller queries for
    "l'Oise" they expect the full course of the river, not an arbitrary single
    segment.  Settlement and administrative types (city, municipality, …) are
    excluded because two French villages with the same name are distinct places
    that must not be conflated.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in features:
        props = f.get("properties", {})
        key = (str(props.get("name", "")), str(props.get("type", "")))
        groups[key].append(f)

    merged: list[dict[str, Any]] = []
    for (name, ftype), group_features in groups.items():
        if len(group_features) == 1 or ftype not in _MERGE_TYPES:
            merged.extend(group_features)
        else:
            geoms = [shape(f["geometry"]) for f in group_features if f.get("geometry") and f["geometry"].get("type")]
            combined = unary_union(geoms)
            base = dict(group_features[0].items())
            base["geometry"] = mapping(combined)
            bounds = combined.bounds
            base["bbox"] = tuple(bounds) if bounds else None
            merged.append(base)
    return merged


class IGNBDCartoSource:
    """
    Geographic data source backed by IGN's BD-CARTO 5.0 dataset.

    Loads French geographic data from GeoPackage files extracted to a directory.
    Supports administrative boundaries (communes, departments, regions, …),
    hydrography (rivers, lakes, …), named places (quarters, hamlets, …),
    orographic features (peaks, passes, valleys, …) and protected areas.

    Data must first be downloaded with ``make download-data-ign``, which places
    the GeoPackage files in ``data/bdcarto/``.

    All geometries are reprojected from EPSG:2154 (Lambert-93) to WGS84
    (EPSG:4326) and returned as standard GeoJSON Feature dicts.

    Args:
        data_path: Directory containing the ``.gpkg`` files (e.g. ``"data/bdcarto"``).

    Example:
        >>> source = IGNBDCartoSource("data/bdcarto")
        >>> results = source.search("Ardèche", type="department")
        >>> results = source.search("Lyon", type="city")
        >>> results = source.search("Rhône", type="river")
    """

    def __init__(self, data_path: str | Path) -> None:
        self._data_path = Path(data_path)
        self._gdf: gpd.GeoDataFrame | None = None
        self._name_index: dict[str, list[int]] = {}

    def _ensure_loaded(self) -> None:
        if self._gdf is not None:
            return
        self._load_data()

    def _load_data(self) -> None:
        if self._data_path.is_dir():
            self._gdf = self._load_from_directory()
        else:
            self._gdf = self._load_from_file(self._data_path)
        self._build_name_index()

    def _load_from_file(self, path: Path) -> gpd.GeoDataFrame:
        """Load from a GeoJSON fixture file. Features must include a ``_layer`` column."""
        full_gdf = gpd.read_file(str(path))
        if "_layer" not in full_gdf.columns:
            raise ValueError(f"GeoJSON fixture {path} must include a '_layer' column")

        gdfs: list[gpd.GeoDataFrame] = []
        for layer_name, cfg in _LAYER_CONFIGS.items():
            rows = full_gdf[full_gdf["_layer"] == layer_name].copy()
            if rows.empty:
                continue
            name_col: str = cfg["name_col"]
            if name_col not in rows.columns:
                continue
            rows[_NAME_COL] = rows[name_col].astype(str)
            rows[_TYPE_COL] = rows.apply(lambda row, c=cfg: _derive_type(row, c), axis=1)
            rows = rows.to_crs("EPSG:4326")
            gdfs.append(rows)

        if not gdfs:
            raise ValueError(f"No matching BD-CARTO features found in {path}")

        combined = pd.concat(gdfs, ignore_index=True)
        return gpd.GeoDataFrame(combined, crs="EPSG:4326", geometry="geometry")

    def _load_from_directory(self) -> gpd.GeoDataFrame:
        """Load and concatenate all configured layers from the data directory."""
        gdfs: list[gpd.GeoDataFrame] = []

        for layer_name, cfg in _LAYER_CONFIGS.items():
            gpkg_path = self._data_path / f"{layer_name}.gpkg"
            if not gpkg_path.exists():
                continue

            gdf = gpd.read_file(str(gpkg_path))

            name_col: str = cfg["name_col"]
            if name_col not in gdf.columns:
                continue

            gdf[_NAME_COL] = gdf[name_col].astype(str)
            gdf[_TYPE_COL] = gdf.apply(lambda row, c=cfg: _derive_type(row, c), axis=1)
            gdf = gdf.to_crs("EPSG:4326")

            gdfs.append(gdf)

        if not gdfs:
            raise ValueError(
                f"No BD-CARTO GeoPackage files found in {self._data_path}. "
                f"Run 'make download-data-ign' to download the dataset."
            )

        combined = pd.concat(gdfs, ignore_index=True)
        return gpd.GeoDataFrame(combined, crs="EPSG:4326", geometry="geometry")

    def _build_name_index(self) -> None:
        """Build normalized name → row indices lookup (with article-stripped variants)."""
        assert self._gdf is not None
        self._name_index = {}
        for idx, name in enumerate(self._gdf[_NAME_COL]):
            if not isinstance(name, str) or not name.strip() or name == "nan":
                continue
            for key in _index_keys(name):
                if key not in self._name_index:
                    self._name_index[key] = []
                self._name_index[key].append(idx)

    def _row_to_feature(self, idx: int) -> dict[str, Any]:
        """Convert a GeoDataFrame row to a GeoJSON Feature dict (WGS84)."""
        assert self._gdf is not None
        row = self._gdf.iloc[idx]

        name = str(row[_NAME_COL])
        normalized_type = str(row[_TYPE_COL]) if pd.notna(row.get(_TYPE_COL)) else "unknown"
        feature_id = str(row["cleabs"]) if pd.notna(row.get("cleabs")) else str(idx)

        geom = row.geometry
        if geom is None or geom.is_empty:
            geometry: dict[str, Any] = {"type": "Point", "coordinates": [0, 0]}
            bbox = None
        else:
            geometry = mapping(geom)
            bounds = geom.bounds
            bbox: tuple[float, float, float, float] | None = (bounds[0], bounds[1], bounds[2], bounds[3])

        skip_cols = {_NAME_COL, _TYPE_COL, "geometry", "cleabs"}
        properties: dict[str, Any] = {
            "name": name,
            "type": normalized_type,
            "confidence": 1.0,
        }
        for col in self._gdf.columns:
            if col not in skip_cols:
                val = _to_json_value(row.get(col))
                if val is not None:
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

        Uses case-insensitive, accent-normalized exact matching with fuzzy
        fallback when no exact match is found.

        Args:
            name: Location name to search for (e.g. ``"Ardèche"``, ``"Lyon"``,
                  ``"Rhône"``).
            type: Optional type hint for filtering. Supports both concrete types
                  (``"department"``, ``"city"``, ``"river"``) and category hints
                  (``"administrative"``, ``"water"``).
            max_results: Maximum number of results.

        Returns:
            List of GeoJSON Feature dicts in WGS84. Empty list if no match.
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

        features = _merge_segments(features)

        return features[:max_results]

    def _fuzzy_search(self, normalized: str, threshold: float = 75.0) -> list[int]:
        """Token-overlap + token_set_ratio fuzzy search."""
        matches: list[tuple[int, float]] = []
        query_tokens = set(normalized.split())

        for indexed_name, indices in self._name_index.items():
            if query_tokens & set(indexed_name.split()):
                score = fuzz.token_set_ratio(normalized, indexed_name)
                if score >= threshold:
                    for idx in indices:
                        matches.append((idx, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in matches]

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a feature by its ``cleabs`` identifier or row index.

        Args:
            feature_id: ``cleabs`` string or integer row index.

        Returns:
            Matching GeoJSON Feature dict, or ``None``.
        """
        self._ensure_loaded()
        assert self._gdf is not None

        if "cleabs" in self._gdf.columns:
            matches = self._gdf[self._gdf["cleabs"].astype(str) == feature_id]
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
        Return the union of all normalized types this source can return.

        Returns:
            Sorted list of type strings.
        """
        types: set[str] = set()
        for cfg in _LAYER_CONFIGS.values():
            if cfg.get("commune_flags"):
                types.update({"city", "municipality"})
            elif cfg.get("fixed_type"):
                types.add(cfg["fixed_type"])
            elif cfg.get("type_map"):
                types.update(cfg["type_map"].values())
        return sorted(types)
