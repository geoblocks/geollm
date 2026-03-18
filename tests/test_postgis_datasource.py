"""
Integration tests for PostGISDataSource using a real PostGIS container.

Requires Docker to be available and running.  The tests are automatically
skipped when Docker is not accessible so they don't break CI environments
without Docker.

The test suite spins up a ``postgis/postgis:18-3.6`` container, loads a
small set of synthetic GeoJSON features into a PostGIS table via
geopandas.to_postgis(), then exercises the full PostGISDataSource API.
"""

import shutil

import pytest

# Skip the whole module when Docker is unavailable, before any imports that
# require a running daemon (testcontainers, etc.).

_docker_available = shutil.which("docker") is not None
if _docker_available:
    try:
        import docker as _docker_sdk

        _docker_sdk.from_env().ping()
    except Exception:
        _docker_available = False

if not _docker_available:
    pytest.skip("Docker is not available — skipping PostGIS integration tests", allow_module_level=True)

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from etter.datasources import PostGISDataSource  # noqa: E402

# Shared PostGIS container fixture (module-scoped for speed)


POSTGIS_IMAGE = "postgis/postgis:18-3.6"
TABLE_NAME = "public.test_locations"


@pytest.fixture(scope="module")
def postgis_container():
    """Start a PostGIS container for the entire test module."""
    with PostgresContainer(
        image=POSTGIS_IMAGE,
        username="testuser",
        password="testpass",
        dbname="testdb",
    ) as container:
        yield container


@pytest.fixture(scope="module")
def db_engine(postgis_container):
    """Create a SQLAlchemy engine connected to the test container."""
    url = postgis_container.get_connection_url()
    engine = create_engine(url)

    # Enable PostGIS extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def populated_table(db_engine):
    """Load synthetic test data into the PostGIS table."""
    features = [
        {
            "id": "feat-001",
            "name": "Lac Léman",
            "type": "lake",
            "geometry": Polygon([(6.1, 46.2), (6.9, 46.2), (6.9, 46.5), (6.1, 46.5), (6.1, 46.2)]),
        },
        {
            "id": "feat-002",
            "name": "Geneva",
            "type": "city",
            "geometry": Point(6.1432, 46.2044),
        },
        {
            "id": "feat-003",
            "name": "Mont Blanc",
            "type": "peak",
            "geometry": Point(6.8651, 45.8326),
        },
        {
            "id": "feat-004",
            "name": "Rhône",
            "type": "river",
            "geometry": Point(7.3, 46.0),
        },
        {
            "id": "feat-005",
            "name": "La Venoge",
            "type": "river",
            "geometry": Point(6.5, 46.5),
        },
        {
            "id": "feat-006",
            "name": "Zurich",
            "type": "city",
            "geometry": Point(8.5417, 47.3769),
        },
    ]

    gdf = gpd.GeoDataFrame(
        pd.DataFrame([{k: v for k, v in f.items() if k != "geometry"} for f in features]),
        geometry=[f["geometry"] for f in features],
        crs="EPSG:4326",
    )

    gdf.to_postgis(
        "test_locations",
        db_engine,
        schema="public",
        if_exists="replace",
        index=False,
    )

    # Rename geometry column to 'geom' to match PostGISDataSource default
    with db_engine.connect() as conn:
        conn.execute(text("ALTER TABLE public.test_locations RENAME COLUMN geometry TO geom"))
        conn.commit()

    yield TABLE_NAME


@pytest.fixture(scope="module")
def source(db_engine, populated_table):  # noqa: ARG001
    """Create a PostGISDataSource instance backed by the test container."""
    return PostGISDataSource(
        connection=db_engine,
        table=TABLE_NAME,
        name_column="name",
        type_column="type",
        geometry_column="geom",
        id_column="id",
    )


def test_search_exact(source):
    """Exact name returns the expected feature."""
    results = source.search("Geneva")
    assert len(results) >= 1
    names = [r["properties"]["name"] for r in results]
    assert "Geneva" in names


def test_search_case_insensitive(source):
    """ILIKE search is case-insensitive."""
    results = source.search("geneva")
    assert any(r["properties"]["name"] == "Geneva" for r in results)


def test_search_partial_name(source):
    """Partial name match (substring) returns results."""
    results = source.search("Léman")
    assert len(results) >= 1
    assert any("Léman" in r["properties"]["name"] for r in results)


def test_search_with_type_filter(source):
    """Type filter restricts results to matching types."""
    results = source.search("Geneva", type="city")
    assert all(r["properties"]["type"] == "city" for r in results)


def test_search_type_category_expansion(source):
    """Type category 'water' expands to include 'lake' and 'river'."""
    results = source.search("Lac", type="water")
    types = {r["properties"]["type"] for r in results}
    # All returned types should be water-related
    water_types = {"lake", "river", "pond", "spring", "waterfall", "glacier"}
    assert types.issubset(water_types)


def test_search_no_results(source):
    """Unknown name returns empty list."""
    results = source.search("zzznomatch999")
    assert results == []


def test_search_max_results(source):
    """max_results limits the number of returned features."""
    results = source.search("e", max_results=2)
    assert len(results) <= 2


def test_get_by_id_found(source):
    """get_by_id returns the correct feature for a known id."""
    feature = source.get_by_id("feat-002")
    assert feature is not None
    assert feature["id"] == "feat-002"
    assert feature["properties"]["name"] == "Geneva"
    assert feature["properties"]["type"] == "city"


def test_get_by_id_not_found(source):
    """get_by_id returns None for an unknown id."""
    result = source.get_by_id("does-not-exist-99999")
    assert result is None


def test_geojson_structure(source):
    """Returned features conform to GeoJSON Feature structure."""
    results = source.search("Zurich")
    assert len(results) >= 1
    feature = results[0]
    assert feature["type"] == "Feature"
    assert "id" in feature
    assert "geometry" in feature
    assert "properties" in feature
    geometry = feature["geometry"]
    assert "type" in geometry
    assert "coordinates" in geometry


def test_coordinates_in_wgs84(source):
    """Returned coordinates are in WGS84 range."""
    results = source.search("Geneva")
    assert results
    coords = results[0]["geometry"]["coordinates"]
    lon, lat = coords[0], coords[1]
    assert -180 <= lon <= 180
    assert -90 <= lat <= 90


def test_get_available_types(source):
    """get_available_types returns the distinct types in the table."""
    types = source.get_available_types()
    assert isinstance(types, list)
    assert len(types) > 0
    assert "city" in types
    assert "lake" in types
    assert "river" in types
    assert "peak" in types


def test_get_available_types_sorted(source):
    """get_available_types returns types in sorted order."""
    types = source.get_available_types()
    assert types == sorted(types)


def test_connection_string_creates_engine(postgis_container):
    """Passing a connection string creates an engine internally."""
    url = postgis_container.get_connection_url()
    source = PostGISDataSource(
        connection=url,
        table=TABLE_NAME,
    )
    # Should be able to call get_available_types without error
    types = source.get_available_types()
    assert isinstance(types, list)


def test_confidence_in_properties(source):
    """Returned features have a 'confidence' property."""
    results = source.search("Geneva")
    assert results
    assert results[0]["properties"]["confidence"] == 1.0


def test_bbox_present_for_polygon(source):
    """Polygon features include a bbox."""
    results = source.search("Léman", type="lake")
    if not results:
        results = source.search("Lac Léman")
    assert results
    feature = results[0]
    if feature["geometry"]["type"] == "Polygon":
        assert feature["bbox"] is not None
        assert len(feature["bbox"]) == 4


def test_type_map_normalisation(db_engine, populated_table):  # noqa: ARG001
    """type_map parameter remaps raw DB type values."""
    source = PostGISDataSource(
        connection=db_engine,
        table=TABLE_NAME,
        type_map={"city": "settlement", "peak": "mountain_peak"},
    )
    results = source.search("Geneva")
    assert results
    # After mapping, "city" should become "settlement"
    assert results[0]["properties"]["type"] == "settlement"


def test_no_type_column(db_engine, populated_table):  # noqa: ARG001
    """Datasource works when type_column is None."""
    source = PostGISDataSource(
        connection=db_engine,
        table=TABLE_NAME,
        type_column=None,
    )
    results = source.search("Geneva")
    assert len(results) >= 1
    types = source.get_available_types()
    assert types == []
