# Datasources

A datasource resolves a location name (e.g. `"Lausanne"`) to a geometry. etter ships with three implementations and a composable aggregator.

All datasources implement the [`GeoDataSource`](../api/etter.html#GeoDataSource) protocol — no inheritance required.

## SwissNames3D

Wraps the [swisstopo SwissNames3D](https://www.swisstopo.admin.ch/en/landscape-model-swissnames3d) dataset (Shapefile/GDB). Covers Switzerland with ~80 geographic feature types.

```python
from etter.datasources import SwissNames3DSource

source = SwissNames3DSource("data/swissnames3d/")
results = source.search("Lausanne", type="settlement", max_results=5)
```

Handles EPSG:2056 → WGS84 reprojection and fuzzy name matching automatically. Data is loaded lazily on first use.

## IGN BD-CARTO

Wraps the [IGN BD-CARTO](https://geoservices.ign.fr/bdcarto) GeoPackage for France. Covers 14 thematic layers (administrative boundaries, hydrography, named places, protected areas, etc.).

```python
from etter.datasources import IGNBDCartoSource

source = IGNBDCartoSource("data/bdcarto/")
results = source.search("Rhône", type="water")
```

Handles Lambert-93 (EPSG:2154) → WGS84 reprojection and French article stripping (`le`, `la`, `l'`, `les`, `de`, `du`, `des`).

## PostGIS

A generic PostGIS datasource that works with any table. The connection is validated at construction time.

```python
from etter.datasources import PostGISDataSource

source = PostGISDataSource(
    connection="postgresql+psycopg2://...",
    table="public.my_geodata",
    type_map={"municipality": ["COMMUNE"], "river": ["COURS_EAU"]},
)
results = source.search("Genève", type="city")
```

The `type_map` maps **normalized type names** (as used by etter's type system) to lists of **raw values** in the database's type column — the same direction as `SwissNames3DSource`'s `OBJEKTART_TYPE_MAP`.

Install the extra for PostGIS support:

```bash
uv sync --extra postgis
```

The search cascade is: exact match → fuzzy (`pg_trgm`) → ILIKE. CRS reprojection is done at query time via `ST_Transform` when the stored SRID differs from 4326.

See [`PostGISDataSource`](../api/etter.html#PostGISDataSource) for the full constructor reference.

## CompositeDataSource

Fan-out across multiple datasources. Sources are queried in order and results are accumulated until `max_results` is reached:

```python
from etter.datasources import CompositeDataSource, SwissNames3DSource, IGNBDCartoSource

source = CompositeDataSource(
    SwissNames3DSource("data/swissnames3d/"),
    IGNBDCartoSource("data/bdcarto/"),
)
results = source.search("Geneva", type="settlement")
```

## Type System

All datasources share a common type hierarchy for fuzzy type matching. Query with a category and it matches all concrete types within it:

| Category | Concrete types (examples) |
|----------|--------------------------|
| `water` | `lake`, `river`, `pond`, `spring`, `glacier` |
| `landforms` | `mountain`, `peak`, `hill`, `pass`, `valley` |
| `settlement` | `city`, `town`, `village`, `hamlet` |
| `administrative` | `country`, `canton`, `municipality`, `region` |
| `transport` | `train_station`, `airport`, `road`, `bridge` |
| `building` | `building`, `tower`, `monument`, `fountain` |
| `amenity` | `restaurant`, `hospital`, `school`, `park` |
| `natural` | `cave`, `forest`, `nature_reserve` |

```python
# Matches lake, river, pond, spring, ...
source.search("Morat", type="water")

# Matches only "lake"
source.search("Morat", type="lake")
```

See [`location_types`](../api/etter.html#etter.datasources.location_types) for the complete hierarchy.

## Implementing a Custom Datasource

Any class with a `search` method and `get_available_types` method matching the protocol qualifies:

```python
class MyDataSource:
    def get_available_types(self) -> list[str]:
        return ["city", "river", "lake"]

    def search(
        self,
        name: str,
        type: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        # Return standard GeoJSON feature dicts
        ...

    def get_by_id(self, feature_id: str) -> dict | None:
        # Optional: return a feature by its unique ID
        ...
```

See [`GeoDataSource`](../api/etter.html#GeoDataSource) for the full protocol definition. The `get_by_id()` method is optional for custom datasources.
