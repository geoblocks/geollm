# Spatial Relations

etter supports 15 built-in spatial relations across three categories.

## Containment

| Relation | Behavior | Default distance |
|----------|----------|-----------------|
| `in` | Exact geometry match — passthrough | — |

**Example:** `"restaurants in Geneva"` → returns Geneva's boundary polygon as-is.

## Buffer / Proximity

| Relation | Behavior | Default distance |
|----------|----------|-----------------|
| `near` | Circular buffer from centroid | 5 km |
| `along` | Linear buffer along a feature | 500 m |
| `left_bank` | Left bank of a linear feature (relative to flow direction) | 500 m |
| `right_bank` | Right bank of a linear feature (relative to flow direction) | 500 m |
| `on_shores_of` | Ring buffer around a water boundary, excluding the water body | 1 km ring |
| `in_the_heart_of` | Negative buffer (erosion) toward center | −500 m |

**One-sided buffers:** `left_bank` and `right_bank` produce a buffer on a single side of a linear feature (river, road) relative to its direction of flow.

**Ring buffer:** `on_shores_of` uses `ring_only=True` — the reference geometry itself is subtracted, leaving only the surrounding ring.

## Directional

All directional relations produce a 90° sector wedge extending outward from the reference geometry centroid.

| Relation | Direction | Default radius |
|----------|-----------|---------------|
| `north_of` | 0° | 10 km |
| `northeast_of` | 45° | 10 km |
| `east_of` | 90° | 10 km |
| `southeast_of` | 135° | 10 km |
| `south_of` | 180° | 10 km |
| `southwest_of` | 225° | 10 km |
| `west_of` | 270° | 10 km |
| `northwest_of` | 315° | 10 km |

**Example:** `"5km north of Lausanne"` → 90° sector polygon extending 5km north from Lausanne's centroid.

## Registering Custom Relations

```python
from etter import SpatialRelationConfig, RelationConfig

config = SpatialRelationConfig()
config.register_relation(RelationConfig(
    name="close_to",
    category="buffer",
    description="Very close proximity, under 1km",
    default_distance_m=1000,
    buffer_from="center",
))
```

See [`SpatialRelationConfig`](../api/etter.html#SpatialRelationConfig) and [`RelationConfig`](../api/etter.html#RelationConfig) for all available options.

## Output Geometry Format

By default `apply_spatial_relation()` returns a GeoJSON geometry dict. Use the `geometry_format` parameter to request WKT or WKB instead:

```python
from etter import apply_spatial_relation
from etter.models import SpatialRelation, BufferConfig

geometry = datasource.search("Lausanne")[0]["geometry"]

# GeoJSON dict (default)
result = apply_spatial_relation(geometry, relation, buffer_config)

# WKT string
result_wkt = apply_spatial_relation(geometry, relation, buffer_config, geometry_format="wkt")

# WKB hex string
result_wkb = apply_spatial_relation(geometry, relation, buffer_config, geometry_format="wkb")
```

To convert raw datasource feature dicts, use `convert_feature_geometry()`:

```python
from etter import convert_feature_geometry

feature = datasource.search("Lausanne")[0]
feature_wkt = convert_feature_geometry(feature, "wkt")
# feature_wkt["geometry"] is now a WKT string
```


## Querying Available Relations

```python
# All relations
parser.get_available_relations()

# By category
parser.get_available_relations(category="directional")

# Description of a specific relation
parser.describe_relation("on_shores_of")
```
