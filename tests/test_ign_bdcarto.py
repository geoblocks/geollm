"""
Tests for IGNBDCartoSource using a synthetic JSON fixture and real BD-CARTO data.
"""

from pathlib import Path

import pytest

from etter.datasources.ign_bdcarto import IGNBDCartoSource

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ign_bdcarto_sample.json"
DATA_DIR = Path(__file__).parent.parent / "data" / "bdcarto"


@pytest.fixture
def source():
    """IGNBDCartoSource loaded from the JSON fixture."""
    return IGNBDCartoSource(FIXTURE_PATH)


@pytest.fixture
def real_source():
    """IGNBDCartoSource loaded from real BD-CARTO GeoPackage files."""
    if not DATA_DIR.exists():
        pytest.skip("Real BD-CARTO data directory not found")
    return IGNBDCartoSource(DATA_DIR)


# Fixture-based tests


def test_load_data(source):
    source._ensure_loaded()
    assert source._gdf is not None
    assert len(source._gdf) == 10  # 10 features in fixture


def test_structure(source):
    feature = source.search("Paris")[0]
    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert "properties" in feature
    assert feature["properties"]["confidence"] == 1.0


def test_search_exact(source):
    results = source.search("Paris")
    assert len(results) == 1
    assert results[0]["properties"]["name"] == "Paris"


def test_search_case_insensitive(source):
    results = source.search("paris")
    assert len(results) == 1
    assert results[0]["properties"]["name"] == "Paris"


def test_search_accent_normalization(source):
    results = source.search("Auvergne-Rhone-Alpes", type="region")
    assert len(results) == 1
    assert results[0]["properties"]["name"] == "Auvergne-Rhône-Alpes"


def test_article_stripping(source):
    """Searching without the article should find features stored with it."""
    results_bare = source.search("Seine", type="river")
    results_full = source.search("la Seine", type="river")
    assert len(results_bare) == 1
    assert len(results_full) == 1
    assert results_bare[0]["properties"]["name"] == results_full[0]["properties"]["name"]


def test_search_with_type_filter(source):
    results_city = source.search("Lyon", type="city")
    assert len(results_city) == 1
    assert results_city[0]["properties"]["type"] == "city"

    results_wrong = source.search("Lyon", type="department")
    assert len(results_wrong) == 0


def test_city_vs_municipality(source):
    """Chef-lieu flag → city; plain commune → municipality."""
    assert source.search("Paris")[0]["properties"]["type"] == "city"
    assert source.search("Lyon")[0]["properties"]["type"] == "city"

    municipalities = source.search("Saint-Martin", type="municipality")
    assert len(municipalities) == 2


def test_coordinates_in_wgs84(source):
    paris = source.search("Paris")[0]
    lon, lat = paris["geometry"]["coordinates"]
    assert 2.0 < lon < 3.0
    assert 48.0 < lat < 49.5


def test_get_by_id(source):
    feature = source.get_by_id("COMMUNE-75056")
    assert feature is not None
    assert feature["properties"]["name"] == "Paris"


def test_unknown_name(source):
    assert source.search("Atlantis") == []


def test_search_type_category_expansion(source):
    """type='water' should match concrete types lake, river, etc."""
    results_lake = source.search("Lac du Der", type="water")
    assert len(results_lake) == 1
    assert results_lake[0]["properties"]["type"] == "lake"

    results_river = source.search("la Seine", type="water")
    assert len(results_river) == 1
    assert results_river[0]["properties"]["type"] == "river"


def test_search_type_exact_still_works(source):
    assert len(source.search("Lac du Der", type="lake")) == 1
    assert source.search("Lac du Der", type="river") == []


def test_mountain_matches_peak(source):
    """type='mountain' expands to include 'peak' (Sommet maps to peak in BD-CARTO)."""
    results = source.search("Mont Blanc", type="mountain")
    assert len(results) == 1
    assert results[0]["properties"]["type"] == "peak"


def test_segment_merging_river(source):
    """Two segments of 'la Seine' should be merged into one feature."""
    results = source.search("la Seine", type="river")
    assert len(results) == 1
    assert results[0]["geometry"]["type"] in ("LineString", "MultiLineString")


def test_no_segment_merging_for_settlements(source):
    """Same-name municipalities in different locations must NOT be merged."""
    results = source.search("Saint-Martin", type="municipality")
    assert len(results) == 2


def test_department_type(source):
    results = source.search("Rhône", type="department")
    assert len(results) == 1
    assert results[0]["properties"]["type"] == "department"


def test_region_type(source):
    results = source.search("Auvergne-Rhône-Alpes", type="region")
    assert len(results) == 1
    assert results[0]["properties"]["type"] == "region"


def test_administrative_category_expansion(source):
    """type='administrative' should match department and region."""
    results = source.search("Rhône", type="administrative")
    assert any(f["properties"]["type"] == "department" for f in results)


def test_get_available_types(source):
    types = source.get_available_types()
    assert isinstance(types, list)
    assert "city" in types
    assert "river" in types
    assert "department" in types
    assert "lake" in types
    assert "peak" in types


# Real data tests (skipped when BD-CARTO files are absent)


def test_real_load(real_source):
    real_source._ensure_loaded()
    assert real_source._gdf is not None
    assert len(real_source._gdf) > 1000


def test_real_search_city(real_source):
    results = real_source.search("Lyon", type="city")
    assert len(results) >= 1
    assert results[0]["properties"]["type"] == "city"


def test_real_search_river_merged(real_source):
    """Oise segments should be merged into a single feature."""
    results = real_source.search("Oise", type="river")
    assert len(results) == 1
    assert results[0]["geometry"]["type"] in ("LineString", "MultiLineString")


def test_real_search_department(real_source):
    results = real_source.search("Ardèche", type="department")
    assert len(results) == 1
    assert results[0]["properties"]["type"] == "department"


def test_real_peak_via_mountain_type(real_source):
    """type='mountain' expands to peak, finding BD-CARTO Sommets."""
    results = real_source.search("Mont Blanc", type="mountain")
    assert len(results) >= 1
    assert results[0]["properties"]["type"] == "peak"


def test_real_article_stripping(real_source):
    results_bare = real_source.search("Rhône", type="river")
    results_article = real_source.search("le Rhône", type="river")
    assert len(results_bare) >= 1
    assert len(results_article) >= 1
    assert results_bare[0]["properties"]["name"] == results_article[0]["properties"]["name"]
