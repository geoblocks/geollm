# GeoLLM Architecture

## Core Principle

**GeoLLM has ONE responsibility: Extract & Execute geographic filters from natural language queries.**

### What GeoLLM Does ✅

- **Layer 1: Parsing** - Extract structured `GeoQuery` from text ("north of Lausanne")
- **Layer 2: Resolution** - Resolve "Lausanne" to a physical geometry using a datasource
- **Layer 3: Spatial Operations** - Transform that geometry using the spatial relation (e.g., generate a "north" sector)

### What GeoLLM Does NOT Do ❌

- Subject/feature identification ("hiking", "restaurants")
- Attribute filtering ("with children", "vegetarian")
- Final search execution or result ranking (this is the parent app's job)

---

## Integration Pattern

GeoLLM fits into a search pipeline:

```
User Query: "Hiking with children north of Lausanne"
     ↓
Parent System → Extracts: Activity="Hiking", Audience="children"
     ↓
GeoLLM.parser → Parses: relation="north_of", location="Lausanne"
     ↓
GeoLLM.datasource → Resolves: "Lausanne" → Point(6.63, 46.52)
     ↓
GeoLLM.spatial → Transforms: Point → Polygon(North Sector)
     ↓
Parent System → Database Query: WHERE activity='hiking' AND ST_Intersects(location, sector_polygon)
```

---

## Component Overview

### 1. GeoFilterParser (Layer 1)

Extracts intent from text using an LLM.

- **Input**: "near Bern"
- **Output**: `GeoQuery` object (Pydantic model)
- **Key Features**:
  - Multilingual support
  - 12 spatial relations (containment, buffer, directional)
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

## Spatial Relations (10 Total)

| Category | Relations | Behavior |
|----------|-----------|----------|
| **Containment** | `in` | Exact geometry match |
| **Buffer** | `near`, `along` | Circular/Linear buffer with context-aware distances |
| **Ring** | `on_shores_of` | Buffer - Original (Donut) |
| **Erosion** | `in_the_heart_of` | Negative buffer (shrink) with context-aware depth |
| **Directional** | `north_of`, `south_of`, ... | 90° Sector Wedge |

---

## Type System & Hierarchy

GeoLLM uses a **datasource-defined type system** with semantic grouping and fuzzy matching.

### Type Hierarchy

Types are organized into 10 semantic categories to support fuzzy matching:

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
geollm/
├── parser.py              # Layer 1: LLM Parser
├── models.py              # Pydantic models for Layer 1
├── spatial_config.py      # Spatial relation definitions
├── prompts.py             # LLM prompts
├── validators.py          # Validation pipeline
├── datasources/           # Layer 2: Data Resolution
│   ├── protocol.py        # GeoDataSource Protocol
│   ├── location_types.py  # Type hierarchy & fuzzy matching
│   └── swissnames3d.py    # SwissNames3D Implementation
├── spatial.py             # Layer 3: Geometry Transformation
└── __init__.py            # Public exports
```

---

## Configuration

- **LLM**: Provider, Model, Temperature
- **Spatial**: Default distances, buffer offsets
- **Datasource**: Path to SwissNames3D data file

---

## Status

- ✅ **Layer 1 (Parser)**: Complete
- ✅ **Layer 2 (Datasource)**: Complete (SwissNames3D implemented)
- ✅ **Layer 3 (Spatial)**: Complete (Shapely-based ops)
- ✅ **Integration**: Full flow implemented
