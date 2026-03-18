# etter Architecture

## Core Principle

**etter has ONE responsibility: Extract & Execute geographic filters from natural language queries.**

### What etter Does ✅

- **Layer 1: Parsing** - Extract structured `GeoQuery` from text ("north of Lausanne")
- **Layer 2: Resolution** - Resolve "Lausanne" to a physical geometry using a datasource
- **Layer 3: Spatial Operations** - Transform that geometry using the spatial relation (e.g., generate a "north" sector)

### What etter Does NOT Do ❌

- Subject/feature identification ("hiking", "restaurants")
- Attribute filtering ("with children", "vegetarian")
- Final search execution or result ranking (this is the parent app's job)

---

## Integration Pattern

etter fits into a search pipeline:

```
User Query: "Hiking with children north of Lausanne"
     ↓
Parent System → Extracts: Activity="Hiking", Audience="children"
     ↓
etter.parser → Parses: relation="north_of", location="Lausanne"
     ↓
etter.datasource → Resolves: "Lausanne" → Point(6.63, 46.52)
     ↓
etter.spatial → Transforms: Point → Polygon(North Sector)
     ↓
Parent System → Database Query: WHERE activity='hiking' AND ST_Intersects(location, sector_polygon)
```

---

## Complete Example Workflow

Here's what happens when you query "north of Lausanne" in the demo:

```
1. INPUT: "north of Lausanne"
   ↓
2. PARSER (Layer 1)
   - Extracts: spatial_relation="north_of", reference_location="Lausanne"
   - Confidence: 0.95
   - Buffer: 10000m (default for directional)
   ↓
3. DATASOURCE (Layer 2) 
   - Searches: name="Lausanne", type="settlement" (inferred)
   - Finds: Point(6.63, 46.52) in WGS84
   - Confidence: 1.0 (exact match)
   ↓
4. SPATIAL OPERATIONS (Layer 3)
   - Centroid: (6.63, 46.52)
   - Direction: North (0°)
   - Creates: 90° sector polygon extending 10km north
   ↓
5. OUTPUT: GeoJSON FeatureCollection
   {
     "type": "FeatureCollection",
     "features": [
       { "id": "reference", "geometry": Point, ... },     // Lausanne point
       { "id": "search_area", "geometry": Polygon, ... }  // North sector
     ]
   }
```

---



### 1. GeoFilterParser (Layer 1)

Extracts intent from text using an LLM.

- **Input**: "near Bern"
- **Output**: `GeoQuery` object (Pydantic model)
- **Key Features**:
  - Multilingual support
  - 13 spatial relations (containment, buffer, directional)
  - Distance inference ("10 min walk" → 833m)
  - Confidence scoring

### 2. GeoDataSource (Layer 2)

Resolves location names to geometries.

- **Interface**: `GeoDataSource` Protocol (returns `list[dict]` - standard GeoJSON)
- **Type System**: Each datasource declares its own list of available types via `get_available_types()`
  - Types are organized in a semantic hierarchy (water, landforms, settlement, etc.)
  - Supports fuzzy matching: query `type="water"` matches lake, river, pond, spring, etc.
  - See `location_types.py` for the standard type hierarchy
- **Implementations**:
  - `SwissNames3DSource`: Wraps swisstopo data (Shapefile/GDB). Handles:
    - Fuzzy/Exact search by name
    - Type filtering with fuzzy matching (lake, city, canton, etc.)
    - Coordinate conversion (CH1903+ → WGS84)
    - ~80 grouped geographic types
  - `IGNBDCartoSource`: Wraps IGN BD-CARTO data (GeoPackage). Handles:
    - 13 thematic layers (administrative, hydrography, named places, protected areas)
    - French article stripping for name normalization
    - Coordinate conversion (Lambert-93 → WGS84)
  - `PostGISDataSource`: Generic DB-backed datasource for any PostGIS table. Handles:
    - Accepts a SQLAlchemy `Engine` or a connection URL string (DB-agnostic)
    - ILIKE-based case-insensitive search with `pg_trgm` fuzzy fallback
    - CRS reprojection via `ST_Transform` when the stored CRS differs from WGS84
    - Optional `type_map` for normalizing raw DB type values to the etter hierarchy
    - No driver is bundled — the user provides it via the connection URL
      (e.g. `postgresql+psycopg2://...`)
  - `CompositeDataSource`: Fan-out aggregator over multiple datasources

### 3. Spatial Operations (Layer 3)

Transforms reference geometries into search areas.

- **Function**: `apply_spatial_relation(geometry, relation, buffer_config)`
- **Operations**:
  - **Containment**: Passthrough (exact boundary)
  - **Buffer**: Positive (expand), Negative (erode), Ring (donut)
  - **Directional**: Angular sector wedges (e.g., North = 90° wedge)
- **Technology**: Uses `shapely` + `pyproj` internally, IO is standard WGS84 GeoJSON.

---

## Data Models

### GeoQuery (Parse Result)

```python
GeoQuery(
    spatial_relation=SpatialRelation(relation="north_of", ...),
    reference_location=ReferenceLocation(name="Lausanne", ...),
    buffer_config=BufferConfig(distance_m=10000, ...),
    confidence_breakdown=...
)
```

### GeoJSON Feature (Resolution Result)

Standard GeoJSON dictionary structure:

```json
{
  "type": "Feature",
  "id": "uuid-123",
  "geometry": { "type": "Point", "coordinates": [6.63, 46.52] },
  "properties": {
    "name": "Lausanne",
    "type": "city",
    "confidence": 1.0
  }
}
```

---

## Spatial Relations (13 Total)

| Category (`category=`) | Relations | Behavior |
|------------------------|-----------|----------|
| **`containment`** | `in` | Exact geometry match |
| **`buffer`** | `near`, `along` | Circular/Linear buffer with context-aware distances |
| **`buffer`** (ring) | `on_shores_of` | Buffer - Original (Donut) |
| **`buffer`** (erosion) | `in_the_heart_of` | Negative buffer (shrink) with context-aware depth |
| **`directional`** | `north_of`, `south_of`, `east_of`, `west_of`, `northeast_of`, `southeast_of`, `southwest_of`, `northwest_of` | 90° Sector Wedge |

---

## Query Types

etter supports four query complexity levels through the `query_type` field in `GeoQuery`:

| Type | Status | Purpose | Example |
|------|--------|---------|---------|
| **`simple`** | ✅ Implemented | Single spatial relation + reference location | "north of Lausanne" |
| **`compound`** | 📋 Planned | Multi-step or hierarchical spatial queries | "north of Lausanne AND within 10km of a lake" |
| **`split`** | 📋 Planned | Queries that divide an area into regions | "areas of Switzerland between Lausanne and Geneva" |
| **`boolean`** | 📋 Planned | AND/OR/NOT logical operations on spatial relations | "within 5km of Geneva AND north of Bern" |

### Current Implementation (Phase 1)

Only `simple` queries are currently supported. A simple query has:
- **One spatial relation** (e.g., "north", "in", "near")
- **One reference location** (e.g., "Lausanne", a city, a canton)
- Optional: Buffer distance configuration

Example flow:
```
Input: "restaurants in Geneva"
  ↓
GeoQuery(
    query_type="simple",
    spatial_relation=SpatialRelation(relation="in", ...),
    reference_location=ReferenceLocation(name="Geneva", ...),
    ...
)
```

### Future Query Types (Phase 2+)

**Compound queries** would combine multiple spatial relations:
- "North of Lausanne AND within 10km of the lake"
- Requires: Multi-relation parsing, geometry intersection
- Datasource: Hierarchical location resolution

**Split queries** would divide areas by spatial relations:
- "Regions of Switzerland north of Bern"
- Requires: Area partitioning logic, polygon subdivision

**Boolean queries** would use explicit logical operators:
- "Within Geneva OR Bern, but not on lake shores"
- Requires: Union/Intersection/Difference operations on geometries

### Architecture Impact

To support compound queries, three layers would need enhancement:

1. **Parser (Layer 1)**: Detect and structure multiple spatial relations
2. **Datasource (Layer 2)**: Support hierarchical/nested location resolution
3. **Spatial Operations (Layer 3)**: Combine geometries (intersection, union, difference)

The current single-relation architecture is intentionally simple to support Phase 1 requirements. The `query_type` field provides forward compatibility for future expansion.

---

## Type System & Hierarchy

etter uses a **datasource-defined type system** with semantic grouping and fuzzy matching.

### Type Hierarchy

Types are organized into 11 semantic categories to support fuzzy matching:

| Category | Examples |
|----------|----------|
| **water** | lake, river, pond, spring, waterfall, glacier, dam |
| **landforms** | mountain, peak, hill, pass, valley, ridge, plain, boulder |
| **natural** | cave, forest, nature_reserve, alpine_pasture |
| **island** | island, peninsula |
| **administrative** | country, canton, municipality, region, area |
| **settlement** | city, town, village, hamlet, district |
| **building** | building, religious_building, tower, monument, fountain |
| **transport** | train_station, bus_stop, airport, road, bridge, railway, ferry, lift |
| **amenity** | restaurant, hospital, school, parking, park, swimming_pool, zoo, camping |
| **infrastructure** | power_plant, wastewater_treatment, landfill, quarry |
| **other** | viewpoint, field_name, local_name, historical_site |

### How It Works

1. **Datasource Declaration**: Each datasource declares available types via `get_available_types()`
   ```python
   source = SwissNames3DSource("data/")
   available_types = source.get_available_types()
   # → ["lake", "river", "city", "mountain", "peak", ...]
   ```

2. **Fuzzy Matching**: Type hints can be either concrete or categorical
   ```python
   results = source.search("Geneva", type="water")     # Matches: lake, river, pond, etc.
   results = source.search("Geneva", type="lake")      # Matches: only "lake"
   results = source.search("Geneva", type="settlement") # Matches: city, town, village, etc.
   ```

3. **LLM Integration**: The LLM is aware of the type hierarchy and uses it for better type inference
   - Can suggest types from the hierarchy when parsing queries
   - Understands categorical types for more flexible matching

### Defining Types for a New Datasource

When adding a new datasource (e.g., OpenStreetMap), implement the protocol:

```python
class MyDataSource:
    def get_available_types(self) -> list[str]:
        """Return concrete types this datasource can return."""
        return ["lake", "river", "city", "restaurant", "hospital"]
    
    def search(self, name: str, type: str | None = None, max_results: int = 10):
        # Map native types to standard hierarchy
        # Use location_types.get_matching_types(type) for fuzzy matching
        pass
```

See `location_types.py` for the complete type hierarchy and utilities.

---

## Project Structure

```
etter/
├── parser.py              # Layer 1: LLM Parser
├── models.py              # Pydantic models for Layer 1
├── spatial_config.py      # Spatial relation definitions
├── prompts.py             # LLM prompts
├── validators.py          # Validation pipeline
├── datasources/           # Layer 2: Data Resolution
│   ├── protocol.py        # GeoDataSource Protocol
│   ├── location_types.py  # Type hierarchy & fuzzy matching
│   ├── swissnames3d.py    # SwissNames3D Implementation (Shapefile)
│   ├── ign_bdcarto.py     # IGN BD-CARTO Implementation (GeoPackage)
│   ├── postgis.py         # PostGISDataSource (generic DB-backed)
│   └── composite.py       # Fan-out aggregator
├── spatial.py             # Layer 3: Geometry Transformation
└── __init__.py            # Public exports

demo/
├── main.py                # FastAPI demo server (file-based or PostGIS mode)
├── Dockerfile             # Image for the FastAPI service
├── docker-compose.yml     # PostGIS demo stack (see below)
└── static/                # OpenLayers map UI

scripts/
├── extract_bdcarto.sh     # Extract IGN 7z archive
└── load_data_postgis.py   # Load shapefiles/gpkg into PostGIS
```

---

## PostGIS Demo Stack

The `demo/docker-compose.yml` provides a fully containerised version of the
demo using PostGIS as the geodata backend.

### Services

| Service | Image / Build | Purpose |
|---|---|---|
| `postgis` | `postgis/postgis:18-3.6` | PostgreSQL 18 + PostGIS; stores data in `/var/lib/postgresql` |
| `data-loader` | `demo/Dockerfile` | One-shot container; runs `scripts/load_data_postgis.py` then exits |
| `api` | `demo/Dockerfile` | FastAPI server; starts after `data-loader` completes successfully |

### Normalized Table Schema

Both datasets are loaded into PostGIS using the same unified schema:

```sql
CREATE TABLE public.swissnames3d (
    id    TEXT,
    name  TEXT NOT NULL,
    type  TEXT,
    geom  GEOMETRY(Geometry, 4326)
);

CREATE TABLE public.ign_bdcarto (
    id    TEXT,
    name  TEXT NOT NULL,
    type  TEXT,
    geom  GEOMETRY(Geometry, 4326)
);
```

All geometries are stored in WGS84 (EPSG:4326). The loader reprojects from
the native CRS (EPSG:2056 for SwissNames3D, EPSG:2154 for IGN BD-CARTO) at
load time.

### Quick Start

```bash
# 1. Download geodata (if not already present)
make download-data          # SwissNames3D shapefiles → data/
make download-data-ign      # IGN BD-CARTO gpkg files → data/bdcarto/

# 2. Set your OpenAI API key
export OPENAI_API_KEY=sk-...

# 3. Start the full stack
docker compose -f demo/docker-compose.yml up

# The API is available at http://localhost:8000
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ETTER_DB_URL` | — | SQLAlchemy connection URL; enables PostGIS mode in `demo/main.py` |
| `POSTGRES_USER` | `etter` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `etter` | PostgreSQL password |
| `POSTGRES_DB` | `geodata` | PostgreSQL database name |
| `SWISSNAMES3D_TABLE` | `swissnames3d` | Target table for SwissNames3D |
| `IGN_BDCARTO_TABLE` | `ign_bdcarto` | Target table for IGN BD-CARTO |
| `DB_SCHEMA` | `public` | PostgreSQL schema |

### Demo Mode Selection

`demo/main.py` auto-detects which mode to use:

- **PostGIS mode** — when `ETTER_DB_URL` is set (used by docker-compose)
- **File mode** — when `ETTER_DB_URL` is absent (original behaviour; uses `SWISSNAMES3D_PATH` / `IGN_BDCARTO_PATH`)

---

### Installing the PostGIS Extra

To use `PostGISDataSource` outside the demo (e.g., in your own application):

```bash
pip install etter[postgis]          # installs sqlalchemy + geoalchemy2
pip install psycopg2-binary         # or your preferred driver
```

```python
from etter.datasources import PostGISDataSource

source = PostGISDataSource(
    connection="postgresql+psycopg2://user:pass@localhost/mydb",
    table="public.my_geodata",
)
results = source.search("Lausanne", type="city")
```

---

---

## Configuration

- **LLM**: Provider, Model, Temperature
- **Spatial**: Default distances, buffer offsets
- **Datasource (file mode)**: Path to SwissNames3D shapefiles / IGN BD-CARTO GeoPackages
- **Datasource (PostGIS mode)**: SQLAlchemy connection URL + table names

---

## Implementation Status

All three layers are **fully implemented and integrated**:

- ✅ **Layer 1 (Parser)**: Complete — Extracts spatial relations from natural language using LLM
- ✅ **Layer 2 (Datasource)**: Complete — Multiple implementations:
  - `SwissNames3DSource` — swisstopo shapefiles → WGS84 GeoJSON
  - `IGNBDCartoSource` — IGN BD-CARTO GeoPackages → WGS84 GeoJSON
  - `PostGISDataSource` — generic PostGIS table → WGS84 GeoJSON (DB-agnostic)
  - `CompositeDataSource` — fan-out aggregator
- ✅ **Layer 3 (Spatial Operations)**: Complete — Transforms geometries using spatial relations (buffers, directional sectors, etc.)
- ✅ **Integration**: Full end-to-end workflow with demo API server (file mode and PostGIS mode)

The demo API at `demo/main.py` demonstrates the complete pipeline:
```
Query → Parser → Datasource → Spatial Ops → GeoJSON Result
```

## Not Yet Implemented

- Complex query types: `compound` (multi-step), `split` (area division), `boolean` (AND/OR/NOT)
- Some edge cases in spatial operations
