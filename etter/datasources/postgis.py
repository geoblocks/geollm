"""
PostGIS data source implementation.

Generic datasource backed by any PostGIS-enabled PostgreSQL table using a
unified normalized schema (id, name, type, geom).

The datasource is DB-agnostic: the caller provides either a SQLAlchemy
Engine or a connection URL string.  No specific driver is bundled — the
user installs the driver they need (psycopg2, psycopg, asyncpg, …) and
encodes it in the URL (e.g. ``postgresql+psycopg2://...``).

Requires the optional ``[postgis]`` extras:
    pip install etter[postgis]
which pulls in ``sqlalchemy`` and ``geoalchemy2``.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from typing import TYPE_CHECKING, Any

from .location_types import get_matching_types, merge_segments

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Only for type-checking; not imported at runtime to keep the base package
    # free of SQLAlchemy as a hard dependency.
    from sqlalchemy import Engine


def _normalize_name(name: str) -> str:
    """Normalize a name for accent- and case-insensitive matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


def _require_sqlalchemy() -> Any:
    """Import sqlalchemy, raising a clear error if it is not installed."""
    try:
        import sqlalchemy  # noqa: PLC0415

        return sqlalchemy
    except ImportError as exc:
        raise ImportError(
            "SQLAlchemy is required for PostGISDataSource. Install it with: pip install etter[postgis]"
        ) from exc


class PostGISDataSource:
    """
    Geographic data source backed by a PostGIS table.

    Expects the table to follow the unified normalized schema produced by the
    ``scripts/load_data_postgis.py`` loader:

    .. code-block:: sql

        CREATE TABLE <table> (
            id      TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            type    TEXT,
            geom    GEOMETRY(Geometry, 4326)
        );

    Geometries must already be in WGS84 (EPSG:4326).  If your data lives in a
    different CRS, reproject it before storing or set ``crs`` accordingly and
    the datasource will reproject on the fly using ``pyproj``.

    Args:
        connection: A SQLAlchemy :class:`~sqlalchemy.engine.Engine` **or** a
            connection URL string (e.g. ``"postgresql+psycopg2://user:pass@host/db"``).
            When a string is provided the engine is created internally.
        table: Fully-qualified table name, e.g. ``"public.swissnames3d"``.
        name_column: Column used for name-based search (default ``"name"``).
        type_column: Column used for type filtering.  Pass ``None`` to disable
            type filtering (default ``"type"``).
        geometry_column: PostGIS geometry column (default ``"geom"``).
        id_column: Primary-key column (default ``"id"``).
        crs: CRS of the stored geometries as an EPSG string.  Defaults to
            ``"EPSG:4326"`` (no reprojection).  If a different CRS is supplied
            geometries are reprojected to WGS84 before being returned.
        type_map: Optional mapping of raw ``type`` column values to normalized
            type strings used by the rest of the etter package.  When ``None``
            the stored values are used as-is.
        fuzzy_threshold: Minimum ``pg_trgm`` similarity score (0–1) used for
            fuzzy fallback search when no exact ``ILIKE`` match is found.

    Example::

        from sqlalchemy import create_engine
        from etter.datasources import PostGISDataSource

        engine = create_engine("postgresql+psycopg2://user:pass@localhost/geodata")
        source = PostGISDataSource(engine, table="public.swissnames3d")
        results = source.search("Lac Léman", type="lake")
    """

    def __init__(
        self,
        connection: str | Engine,
        table: str,
        name_column: str = "name",
        type_column: str | None = "type",
        geometry_column: str = "geom",
        id_column: str = "id",
        crs: str = "EPSG:4326",
        type_map: dict[str, str] | None = None,
        fuzzy_threshold: float = 0.3,
    ) -> None:
        sa = _require_sqlalchemy()

        if isinstance(connection, str):
            self._engine = sa.create_engine(connection)
        else:
            self._engine = connection

        self._table = table
        self._name_col = name_column
        self._type_col = type_column
        self._geom_col = geometry_column
        self._id_col = id_column
        self._crs = crs
        self._type_map = type_map or {}
        self._fuzzy_threshold = fuzzy_threshold

        self._trgm_available: bool | None = None

    def _get_connection(self) -> Any:
        """Return a SQLAlchemy connection from the engine."""
        return self._engine.connect()

    def _check_trgm(self, conn: Any) -> bool:
        """Return True if pg_trgm extension is available in the database."""
        if self._trgm_available is not None:
            return self._trgm_available
        sa = _require_sqlalchemy()
        try:
            result = conn.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
            self._trgm_available = result.fetchone() is not None
        except Exception:
            logger.exception("Failed to check pg_trgm availability")
            self._trgm_available = False
        return self._trgm_available

    def _normalize_type(self, raw_type: str | None) -> str | None:
        """Apply type_map to a raw DB value, or return it unchanged."""
        if raw_type is None:
            return None
        return self._type_map.get(raw_type, raw_type)

    def _row_to_feature(self, row: Any) -> dict[str, Any]:
        """Convert a SQLAlchemy Row to a GeoJSON Feature dict."""
        feature_id = str(row.id)
        name = str(row.name)
        raw_type = getattr(row, "type", None)
        normalized_type = self._normalize_type(raw_type)

        geojson_str = row.geojson
        if geojson_str:
            geometry = json.loads(geojson_str)
        else:
            geometry = {"type": "Point", "coordinates": [0, 0]}

        bbox = _bbox_from_geojson(geometry)

        properties: dict[str, Any] = {
            "name": name,
            "type": normalized_type,
            "confidence": 1.0,
        }

        return {
            "type": "Feature",
            "id": feature_id,
            "geometry": geometry,
            "bbox": bbox,
            "properties": properties,
        }

    def _build_select_columns(self) -> str:
        """Build the SELECT column list as a SQL fragment."""
        type_expr = f", {self._type_col} AS type" if self._type_col else ", NULL AS type"
        if self._crs.upper() != "EPSG:4326":
            geom_expr = f", ST_AsGeoJSON(ST_Transform({self._geom_col}, 4326)) AS geojson"
        else:
            geom_expr = f", ST_AsGeoJSON({self._geom_col}) AS geojson"
        return f"{self._id_col} AS id, {self._name_col} AS name{type_expr}{geom_expr}"

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for geographic features by name.

        Uses a three-step cascade, stopping as soon as any step returns results:

        1. **Normalized exact match**
        2. **ILIKE substring**
        3. **pg_trgm fuzzy** (requires the ``pg_trgm`` extension).

        ``merge_segments`` is applied after all rows are fetched so that
        multi-segment linestrings (rivers, roads) are merged before the
        ``max_results`` cap is applied.

        Args:
            name: Location name to search for.
            type: Optional type hint for filtering results.
            max_results: Maximum number of results to return.

        Returns:
            List of matching GeoJSON Feature dicts in WGS84.
        """
        sa = _require_sqlalchemy()
        cols = self._build_select_columns()

        # Resolve type filter to concrete types via the hierarchy
        type_filter_values: list[str] | None = None
        if type is not None and self._type_col is not None:
            matching_types = get_matching_types(type)
            type_filter_values = matching_types if matching_types else [type.lower()]

        # Fetch more rows than requested so that merge_segments has the full
        # set of segments to work with.  Without this, a SQL LIMIT applied
        # *before* merging would only return a partial set of linestring
        # segments, producing incorrect / truncated geometries.
        # We cap the internal limit at 2000 to avoid unbounded queries.
        internal_limit = min(max(max_results * 20, 100), 2000)

        with self._get_connection() as conn:
            features = self._search_normalized(conn, sa, cols, name, type_filter_values, internal_limit)

        if not features:
            with self._get_connection() as conn:
                features = self._search_ilike(conn, sa, cols, name, type_filter_values, internal_limit)

        if not features:
            with self._get_connection() as conn:
                features = self._search_fuzzy(conn, sa, cols, name, type_filter_values, internal_limit)

        features = merge_segments(features)
        return features[:max_results]

    def _type_filter_sql(self, values: list[str] | None) -> tuple[str, dict[str, Any]]:
        """Return a WHERE clause fragment and bind params for type filtering."""
        if not values or self._type_col is None:
            return "", {}
        placeholders = ", ".join(f":type_{i}" for i in range(len(values)))
        clause = f" AND {self._type_col} IN ({placeholders})"
        params = {f"type_{i}": v for i, v in enumerate(values)}
        return clause, params

    def _search_normalized(
        self,
        conn: Any,
        sa: Any,
        cols: str,
        name: str,
        type_filter: list[str] | None,
        fetch_limit: int,
    ) -> list[dict[str, Any]]:
        """
        Exact accent- and case-insensitive search.

        Accent normalization (NFD decomposition + diacritic strip) is done in
        Python before the query is sent to the DB.
        """
        type_clause, type_params = self._type_filter_sql(type_filter)
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE lower({self._name_col}) = :query{type_clause} "
            f"LIMIT :limit"
        )
        params: dict[str, Any] = {
            "query": _normalize_name(name),
            "limit": fetch_limit,
            **type_params,
        }
        try:
            result = conn.execute(sql, params)
            return [self._row_to_feature(row) for row in result]
        except Exception:
            logger.exception("Normalized search failed for %r", name)
            return []

    def _search_ilike(
        self,
        conn: Any,
        sa: Any,
        cols: str,
        name: str,
        type_filter: list[str] | None,
        fetch_limit: int,
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring fallback using ``ILIKE '%name%'``."""
        type_clause, type_params = self._type_filter_sql(type_filter)
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE {self._name_col} ILIKE :pattern{type_clause} "
            f"LIMIT :limit"
        )
        params: dict[str, Any] = {"pattern": f"%{name}%", "limit": fetch_limit, **type_params}
        try:
            result = conn.execute(sql, params)
            return [self._row_to_feature(row) for row in result]
        except Exception:
            logger.exception("ILIKE search failed for %r", name)
            return []

    def _search_fuzzy(
        self,
        conn: Any,
        sa: Any,
        cols: str,
        name: str,
        type_filter: list[str] | None,
        fetch_limit: int,
    ) -> list[dict[str, Any]]:
        """Fuzzy fallback using pg_trgm similarity (if extension is available)."""
        if not self._check_trgm(conn):
            return []
        type_clause, type_params = self._type_filter_sql(type_filter)
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE similarity({self._name_col}, :name) > :threshold{type_clause} "
            f"ORDER BY similarity({self._name_col}, :name) DESC "
            f"LIMIT :limit"
        )
        params: dict[str, Any] = {
            "name": name,
            "threshold": self._fuzzy_threshold,
            "limit": fetch_limit,
            **type_params,
        }
        try:
            result = conn.execute(sql, params)
            return [self._row_to_feature(row) for row in result]
        except Exception:
            logger.exception("Fuzzy search failed for %r", name)
            return []

    def get_by_id(self, feature_id: str) -> dict[str, Any] | None:
        """
        Get a specific feature by its unique identifier.

        Args:
            feature_id: Value of the ``id`` column.

        Returns:
            The matching GeoJSON Feature dict, or ``None`` if not found.
        """
        sa = _require_sqlalchemy()
        cols = self._build_select_columns()
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} WHERE {self._id_col} = :id LIMIT 1"  # noqa: S608
        )
        with self._get_connection() as conn:
            try:
                result = conn.execute(sql, {"id": feature_id})
                row = result.fetchone()
                return self._row_to_feature(row) if row else None
            except Exception:
                logger.exception("get_by_id failed for %r", feature_id)
                return None

    def get_available_types(self) -> list[str]:
        """
        Return the distinct ``type`` values present in the table.

        Returns:
            Sorted list of concrete type strings, or an empty list if the table
            has no type column.
        """
        if self._type_col is None:
            return []
        sa = _require_sqlalchemy()
        sql = sa.text(
            f"SELECT DISTINCT {self._type_col} AS type FROM {self._table} "  # noqa: S608
            f"WHERE {self._type_col} IS NOT NULL ORDER BY 1"
        )
        with self._get_connection() as conn:
            try:
                result = conn.execute(sql)
                raw_types = [row.type for row in result]
            except Exception:
                logger.exception("get_available_types failed")
                return []

        normalized = {self._normalize_type(t) for t in raw_types if t}
        return sorted(t for t in normalized if t)


# Geometry helpers


def _bbox_from_geojson(geometry: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Compute a bounding-box tuple from a GeoJSON geometry dict."""
    try:
        coords = _flatten_coords(geometry)
        if not coords:
            return None
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        return None


def _flatten_coords(geometry: dict[str, Any]) -> list[list[float]]:
    """Recursively extract all coordinate pairs from a GeoJSON geometry."""
    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates")

    if geom_type == "Point":
        return [coords] if coords else []
    if geom_type in ("MultiPoint", "LineString"):
        return list(coords) if coords else []
    if geom_type in ("MultiLineString", "Polygon"):
        return [pt for ring in (coords or []) for pt in ring]
    if geom_type in ("MultiPolygon",):
        return [pt for poly in (coords or []) for ring in poly for pt in ring]
    if geom_type == "GeometryCollection":
        return [pt for g in geometry.get("geometries", []) for pt in _flatten_coords(g)]
    return []
