"""
PostGIS data source implementation.

Generic datasource backed by any PostGIS-enabled PostgreSQL table.  The
table may store native dataset-specific type values (e.g. SwissNames3D's
``"See"``, ``"Berg"``) or already-normalized etter type names (e.g.
``"lake"``, ``"mountain"``).

When native values are stored, pass a ``type_map`` mapping normalized etter
type names to lists of raw column values, the same format as
``SwissNames3DSource.OBJEKTART_TYPE_MAP``.  The datasource then translates
in both directions: raw → normalized for output, normalized → raw for SQL
type filters.

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

    The table must expose at minimum a name column, a geometry column, and
    optionally a type column. The expected schema is:

    .. code-block:: sql

        CREATE TABLE <table> (
            id      TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            type    TEXT,
            geom    GEOMETRY(Geometry, 4326)
        );

    The ``type`` column may store either:

    - **Raw dataset values** (e.g. ``"See"``, ``"Berg"`` for SwissNames3D),
      pass ``type_map`` so the datasource can translate between raw values and
      the normalized etter type names.
    - **Already-normalized values** (e.g. ``"lake"``, ``"mountain"``),
      leave ``type_map=None`` (default).

    Geometries must be in WGS84 (EPSG:4326) or supply ``crs`` for on-the-fly
    reprojection.

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
            ``"EPSG:4326"`` (no reprojection).
        type_map: Optional mapping from **normalized etter type names** to
            **lists of raw type column values** present in the database.
            This is the same format as ``SwissNames3DSource.OBJEKTART_TYPE_MAP``
            and ``IGNBDCartoSource.IGN_BDCARTO_TYPE_MAP``, so they can be
            passed directly::

                from etter.datasources.swissnames3d import OBJEKTART_TYPE_MAP
                source = PostGISDataSource(
                    engine,
                    table="public.swissnames3d",
                    type_map=OBJEKTART_TYPE_MAP,
                )

            When ``type_map`` is provided the datasource:

            - Translates raw DB values → normalized types in returned features.
            - Translates user type hints → raw DB values in SQL ``WHERE`` clauses.
            - Returns normalized type names from ``get_available_types()``.

            When ``None`` (default) the stored values are used as-is.
        fuzzy_threshold: Minimum ``pg_trgm`` similarity score (0-1) used for
            fuzzy fallback search when no exact ``ILIKE`` match is found.

    Example: unmodified SwissNames3D table::

        from sqlalchemy import create_engine
        from etter.datasources import PostGISDataSource
        from etter.datasources.swissnames3d import OBJEKTART_TYPE_MAP

        engine = create_engine(...)
        source = PostGISDataSource(
            engine,
            table="public.swissnames3d",
            type_map=OBJEKTART_TYPE_MAP,
        )
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
        type_map: dict[str, list[str]] | None = None,
        fuzzy_threshold: float = 0.65,
    ) -> None:
        sa = _require_sqlalchemy()

        if isinstance(connection, str):
            self._engine = sa.create_engine(connection)
        else:
            self._engine = connection

        try:
            with self._engine.connect() as conn:
                conn.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1"))
        except Exception as exc:
            raise ValueError(f"Failed to connect to database or access table {table!r}") from exc

        self._table = table
        self._name_col = name_column
        self._type_col = type_column
        self._geom_col = geometry_column
        self._id_col = id_column
        self._crs = crs
        self._fuzzy_threshold = fuzzy_threshold

        # Build bidirectional lookup structures from the user-supplied map.
        if type_map:
            self._normalized_to_raw: dict[str, list[str]] = dict(type_map)
            self._raw_to_normalized: dict[str, str] = {
                raw: normalized for normalized, raws in type_map.items() for raw in raws
            }
        else:
            self._normalized_to_raw = {}
            self._raw_to_normalized = {}

        self._trgm_available: bool | None = None
        self._unaccent_available: bool | None = None

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

    def _check_unaccent(self, conn: Any) -> bool:
        """Return True if the unaccent extension is available in the database."""
        if self._unaccent_available is not None:
            return self._unaccent_available
        sa = _require_sqlalchemy()
        try:
            result = conn.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'"))
            self._unaccent_available = result.fetchone() is not None
        except Exception:
            logger.exception("Failed to check unaccent availability")
            self._unaccent_available = False
        return self._unaccent_available

    def _normalize_type(self, raw_type: str | None) -> str | None:
        """Translate a raw DB type value to its normalized etter name.

        If no type_map was supplied the value is returned unchanged.
        """
        if raw_type is None:
            return None
        return self._raw_to_normalized.get(raw_type, raw_type)

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
        2. **pg_trgm fuzzy with unaccent** (pg_trgm extension required and unaccent extension recommended)
        3. **ILIKE substring**

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

        # Resolve type filter to the raw DB values to use in the SQL WHERE clause.
        type_filter_values: list[str] | None = None
        if type is not None and self._type_col is not None:
            matching_types = get_matching_types(type)
            concrete_types = matching_types if matching_types else [type.lower()]
            if self._normalized_to_raw:
                raw_values: list[str] = []
                for t in concrete_types:
                    raw_values.extend(self._normalized_to_raw.get(t, [t]))
                type_filter_values = raw_values if raw_values else concrete_types
            else:
                type_filter_values = concrete_types

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
                features = self._search_fuzzy(conn, sa, cols, name, type_filter_values, internal_limit)

        if not features:
            with self._get_connection() as conn:
                features = self._search_ilike(conn, sa, cols, name, type_filter_values, internal_limit)

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
        name_expr = f"lower({self._name_col})"
        if self._check_unaccent(conn):
            name_expr = f"unaccent({name_expr})"
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE {name_expr} = :query{type_clause} "
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
        """Case-insensitive substring fallback using ``ILIKE '%name%'``.

        When the ``unaccent`` extension is available, both the stored name column
        and the pattern are accent-stripped so that e.g. ``"Rhone"`` matches
        ``"Rhône"``.  Without ``unaccent``, standard ILIKE is used (case-insensitive
        only).
        """
        type_clause, type_params = self._type_filter_sql(type_filter)
        normalized = _normalize_name(name)
        if self._check_unaccent(conn):
            name_expr = f"unaccent(lower({self._name_col}))"
            pattern = f"%{normalized}%"
        else:
            name_expr = self._name_col
            pattern = f"%{name}%"
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE {name_expr} ILIKE :pattern{type_clause} "
            f"LIMIT :limit"
        )
        params: dict[str, Any] = {"pattern": pattern, "limit": fetch_limit, **type_params}
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
            logger.warning(
                "pg_trgm extension not available. Fuzzy search disabled. Install it with: CREATE EXTENSION pg_trgm;"
            )
            return []
        normalized_query = _normalize_name(name)
        if self._check_unaccent(conn):
            name_expr = f"unaccent(lower({self._name_col}))"
        else:
            logger.warning(
                "unaccent extension not available. Accent-insensitive fuzzy search degraded. "
                "Install it with: CREATE EXTENSION unaccent;"
            )
            name_expr = f"lower({self._name_col})"
        type_clause, type_params = self._type_filter_sql(type_filter)
        sql = sa.text(
            f"SELECT {cols} FROM {self._table} "  # noqa: S608
            f"WHERE word_similarity({name_expr}, :query) > :threshold{type_clause} "
            f"ORDER BY word_similarity({name_expr}, :query) DESC "
            f"LIMIT :limit"
        )
        params: dict[str, Any] = {
            "query": normalized_query,
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
