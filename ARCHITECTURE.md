# GeoLLM Architecture

## Core Principle

**GeoLLM has ONE responsibility: Extract geographic filters from natural language queries.**

### What GeoLLM Does ✅

- Parse spatial relations: "north of", "in", "near", "within 5km"
- Extract reference locations: "Lausanne", "Lake Geneva"
- Parse distance parameters: "within 5km", "2 kilometers"
- Return structured geographic filter criteria

### What GeoLLM Does NOT Do ❌

- Subject/feature identification ("hiking", "restaurants", "hotels")
- Attribute filtering ("with children", "vegetarian", "4-star")
- Search execution or result ranking
- Geometry resolution (future enhancement)

---

## Integration Pattern

GeoLLM is designed to work within larger search systems:

```
User Query: "Hiking with children north of Lausanne"
     ↓
Parent System → Extracts: Activity="Hiking", Audience="children"
     ↓
GeoLLM → Extracts: relation="north_of", location="Lausanne"
     ↓
Parent System → Combines: activity + audience + geo_filter
     ↓
Database Query → Results
```

**Example:** Outdoor Activity Search Engine

- Parent system: "Hiking with children" → activity filter
- GeoLLM: "north of Lausanne" → geographic filter
- Combined query: WHERE activity='hiking' AND audience='children' AND ST_Within(geom, north_of_lausanne)

---

## Component Overview

### 1. GeoFilterParser (Entry Point)

Main API class for parsing queries.

**Configuration:**

- LLM provider (OpenAI, Anthropic, local models)
- Spatial relation config
- Confidence threshold
- Strict/permissive mode

**Methods:**

- `parse(query: str) -> GeoQuery` - Parse single query
- `parse_batch(queries: List[str]) -> List[GeoQuery]` - Parse multiple
- `get_available_relations(category: Optional[str]) -> List[str]` - List relations
- `describe_relation(name: str) -> str` - Get relation description

### 2. LLM Integration

- **Model:** Configurable (default: GPT-4o with strict schema)
- **Prompt:** Multilingual input handling with few-shot examples
- **Output:** Structured Pydantic models with validation
- **Framework:** LangChain with structured output

#### How the LLM Chooses Spatial Relations

The LLM selects spatial relations through **semantic matching** based on relation descriptions provided in the system prompt. Here's the complete flow:

**Step 1: Relation Definitions with Descriptions**

Each spatial relation is defined in `spatial_config.py:51-216` with metadata including a `description` field:

```python
RelationConfig(
    name="on_shores_of",
    category="buffer",
    description="Ring buffer around lake/water boundary, excluding the water body itself",
    default_distance_m=1000,
    buffer_from="boundary",
    ring_only=True,
    applies_to=["lake", "water_body", "sea"]  # Feature type hints
)
```

**Step 2: Formatting for the Prompt**

The `format_for_prompt()` method (`spatial_config.py:273-322`) transforms relations into structured text:

```
BUFFER RELATIONS:
  • on_shores_of (default: 1000m) [ring buffer, from boundary]
    Ring buffer around lake/water boundary, excluding the water body itself
    (commonly used with: lake, water_body, sea)
```

**Step 3: Injection into System Prompt**

The formatted relations are injected into the system prompt template (`prompts.py:11-90, 113-115`):

```python
system_prompt = SYSTEM_PROMPT.format(spatial_relations=spatial_relations_text)
```

The system prompt includes:

- Complete list of available spatial relations with descriptions
- Key guidelines: "When parsing queries, use ONLY the relations listed above"
- Category distinctions (containment vs buffer vs directional)

**Step 4: LLM Selection Process**

When the LLM receives a query like "villages on shores of Lake Geneva":

1. **Semantic Matching**: Matches query language to description semantics
   - Query phrase: "on shores of"
   - Description: "Ring buffer around lake/water boundary..."
   - Match confidence: High

2. **Context Clues**: Uses `applies_to` hints
   - Reference feature: "Lake Geneva" (type: lake)
   - Relation applies_to: ["lake", "water_body", "sea"]
   - Contextual fit: Strong

3. **Category Understanding**: Distinguishes relation types
   - "in" = containment (exact boundary)
   - "on_shores_of" = buffer (ring around boundary)
   - "north_of" = directional (sector)

4. **Default Distance Awareness**: Considers implicit distances
   - "near" → 5km default
   - "around" → 3km default
   - "on_shores_of" → 1km default

**Step 5: Structured Output**

The LLM returns a structured `SpatialRelation` object:

```json
{
  "relation": "on_shores_of",
  "category": "buffer",
  "explicit_distance": null
}
```

**Step 6: Validation & Enrichment**

The validation pipeline (`validators.py:12-76`) ensures correctness:

1. **Relation Validation**: Checks if selected relation exists in config
2. **Default Enrichment**: Applies technical parameters from `RelationConfig`
   - `default_distance_m` → `BufferConfig.distance_m`
   - `buffer_from` → `BufferConfig.buffer_from`
   - `ring_only` → `BufferConfig.ring_only`

**Description Design Patterns:**

1. **Explicit Use Cases**: "Ring buffer around lake/water boundary..."
2. **Distinguishing Similar Relations**: "near" (5km) vs "around" (3km)
3. **Semantic Meaning**: "in_the_heart_of" = negative buffer/erosion
4. **Feature Type Hints**: `applies_to=["river", "road"]` for "along"

**Key Insight:** The architecture elegantly separates concerns:

- **Descriptions** guide LLM semantic understanding (natural language → relation name)
- **Configs** provide technical parameters (relation name → geometric operations)
- **Validation** ensures LLM stays within allowed relations and enriches with defaults

#### Context-Dependent Distance Handling

GeoLLM recognizes context-dependent distance expressions and converts them to explicit buffer distances using standard transportation speeds:

**Speed Definitions:**
- **Walking**: 5 km/h
- **Biking**: 20 km/h

**Supported Expressions:**

1. **Time-based distances**: "X minutes [walk|bike] from [location]"
   - LLM calculates distance using speed formula: distance = minutes × (speed_km/h × 1000 / 60)
   - Examples:
     - "10 minutes walk from X" → 10 × (5000/60) ≈ 833m
     - "15 minutes bike from X" → 15 × (20000/60) = 5000m

2. **Contextual distances**: "[walking|biking] distance from [location]"
   - Walking distance → 1000m
   - Biking distance → 5000m

3. **Explicit numeric distances**: "within 5km", "500 meters", "2 miles"
   - Directly converted to meters

**How It Works:**

1. LLM recognizes distance expression (time-based, contextual, or numeric)
2. Calculates explicit distance using speed definitions or contextual defaults
3. Sets `explicit_distance` field with computed value
4. Validation pipeline applies this as buffer distance (`validators.py:64-74`)
5. `inferred=False` (treated as user-specified, not default)

**Examples:**
```python
# Query: "10 minutes walk from Zurich"
GeoQuery(
    spatial_relation=SpatialRelation(
        relation="near",
        explicit_distance=833  # ← Computed: 10 min × (5 km/h / 60)
    ),
    buffer_config=BufferConfig(
        distance_m=833,
        inferred=False
    )
)

# Query: "Walking distance from Zurich"
GeoQuery(
    spatial_relation=SpatialRelation(
        relation="near",
        explicit_distance=1000  # ← Contextual default
    ),
    buffer_config=BufferConfig(
        distance_m=1000,
        inferred=False
    )
)

# Query: "15 minutes bike from Bern"
GeoQuery(
    spatial_relation=SpatialRelation(
        relation="near",
        explicit_distance=5000  # ← Computed: 15 min × (20 km/h / 60)
    ),
    buffer_config=BufferConfig(
        distance_m=5000,
        inferred=False
    )
)
```

**Implementation:**
- **Prompt guidance**: System prompt defines speeds and calculation formula (`prompts.py:65-76`)
- **Few-shot examples**: Examples 11-12 in `examples.py` demonstrate expected behavior
- **Validation**: Standard pipeline handles converted distances like explicit user-specified values

**Extension Point**: Future support for additional modes or time formats (hours, seconds) can be added by extending speed definitions in the prompt template.

### 3. Data Models (Pydantic v2)

```python
GeoQuery(
    query_type: str,                    # "simple" (future: "compound", etc)
    spatial_relation: SpatialRelation,
    reference_location: ReferenceLocation,
    buffer_config: Optional[BufferConfig],
    confidence_breakdown: ConfidenceScore,
    original_query: str
)

SpatialRelation(
    relation: str,                      # e.g., "north_of", "in", "near"
    category: str,                      # "containment", "buffer", "directional"
    description: str
)

ReferenceLocation(
    name: str,                          # Location name as mentioned in query
    type: str,                          # "city", "lake", "region" (optional)
    type_confidence: float,             # Confidence in type (0-1)
)

BufferConfig(
    distance_m: int,                    # Positive (expand) or negative (erode)
    buffer_from: str,                   # "center" or "boundary"
    ring_only: bool                     # true for ring buffers
)

ConfidenceScore(
    overall: float,
    spatial_relation_confidence: float,
    reference_location_confidence: float,
    reasoning: str
)
```

### 4. Spatial Relations (12 Total)

#### Containment (2)

- `in` - Exact boundary matching

#### Buffer/Proximity (6)

- `near` - 5km radius from center
- `around` - 3km radius from center
- `on_shores_of` - 1km ring buffer around boundary
- `along` - 500m buffer along linear features
- `in_the_heart_of` - -500m erosion (central area)
- `deep_inside` - -1km erosion (deep interior)

#### Directional (8)

- **Cardinal**: `north_of`, `south_of`, `east_of`, `west_of` (10km, 90° sectors)
- **Diagonal**: `northeast_of`, `southeast_of`, `southwest_of`, `northwest_of` (10km, 90° sectors)

**Buffer Notes:**

- Positive buffers expand outward
- Negative buffers erode inward
- Ring buffers (`ring_only: true`) exclude the reference feature
- `buffer_from` determines whether buffer originates from center or boundary

### 5. Processing Pipeline

```
Raw Query Text
    ↓
LangChain LLM Call (with prompt + examples)
    ↓
Structured Output Parsing (Pydantic validation)
    ↓
Business Logic Validation
    ├─ Check relation is registered
    ├─ Apply default parameters
    └─ Check confidence thresholds
    ↓
Return GeoQuery (or raise error)
```

### 6. Validation

**Schema Validation:** Automatic via Pydantic

- Type checking
- Required field checking
- Format validation

**Business Logic Validation:**

- Is spatial_relation registered in config?
- Are required parameters present?
- Does confidence meet threshold?
- Strict vs permissive mode handling

---

## Error Handling

| Error | Cause | Response |
|-------|-------|----------|
| ParsingError | LLM failed to parse | Return error with raw response |
| ValidationError | Schema mismatch | Return validation error details |
| UnknownRelationError | Relation not registered | Return available relations |
| LowConfidenceError | Confidence below threshold (strict mode) | Raise or warn based on mode |

---

## Phase 1 Scope

**What's Implemented:**

- ✅ Natural language → GeoQuery (Pydantic model)
- ✅ Multilingual input handling
- ✅ 12 spatial relations
- ✅ Confidence scoring with reasoning
- ✅ Flexible configuration
- ✅ Comprehensive validation

**What's NOT Implemented (Future):**

- ❌ Geometry resolution (converting locations to polygons)
- ❌ Data source integration (SwissNames3D, OpenStreetMap)
- ❌ Complex query types (compound, boolean, nested)
- ❌ Target feature extraction (handled by parent system)

---

## Configuration Points

- LLM model selection and parameters
- Spatial relation defaults (distances, buffer settings)
- Confidence thresholds and mode (strict/permissive)
- Custom relation registration
- Language and localization

---

## Extension Points

- Add new spatial relations
- Configure existing relations (distances, angles)
- Custom validation rules
- Pre/post-processing hooks
- Language-specific handling
- Future: Complex query handlers

---

## Project Structure

```
geollm/
├── parser.py              # Main API entry point
├── models.py              # Pydantic models
├── spatial_config.py      # Relations registry (12 relations)
├── prompts.py            # LLM prompt templates
├── examples.py           # Few-shot examples (8, multilingual)
├── validators.py         # Validation pipeline
├── exceptions.py         # Error hierarchy
└── __init__.py          # Public exports
```

---

## Next Steps (Phase 2+)

When ready to expand:

1. Data source interface (abstract base)
2. SwissNames3D adapter (location resolution)
3. Query execution (geometric operations)
4. Result aggregation (geometry collection)
