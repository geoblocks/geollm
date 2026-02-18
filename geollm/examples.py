"""
Few-shot examples for LLM prompt to demonstrate query parsing.

These examples cover:
- Simple containment queries
- Buffer queries (positive and negative)
- Directional queries
- Multilingual support (English, German, French)
- Activity queries (demonstrating scope - activities are ignored)
"""

from dataclasses import dataclass

from .models import (
    BufferConfig,
    ConfidenceScore,
    GeoQuery,
    ReferenceLocation,
    SpatialRelation,
)


@dataclass
class ExampleQuery:
    """
    A single example query with expected output.

    Attributes:
        input: Natural language query
        output: Expected GeoQuery structure
        language: Language code (en, de, fr, it)
        description: What this example demonstrates
    """

    input: str
    output: GeoQuery
    language: str
    description: str


# Define 10 carefully selected examples covering key scenarios
EXAMPLES: list[ExampleQuery] = [
    # Example 1: Simple containment (English)
    ExampleQuery(
        input="in Bern",
        language="en",
        description="Simple containment query - reference location only",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="in", category="containment", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Bern",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=None,
            confidence_breakdown=ConfidenceScore(
                overall=0.95,
                location_confidence=0.95,
                relation_confidence=0.95,
                reasoning=None,
            ),
            original_query="in Bern",
        ),
    ),
    # Example 2: Simple containment (German)
    ExampleQuery(
        input="in Zürich",
        language="de",
        description="Simple containment query in German",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="in", category="containment", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Bern",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=None,
            confidence_breakdown=ConfidenceScore(
                overall=0.93,
                location_confidence=0.95,
                relation_confidence=0.92,
                reasoning=None,
            ),
            original_query="in Zürich",
        ),
    ),
    # Example 3: Query with subject (French) - subject ignored, only geo filter extracted
    ExampleQuery(
        input="restaurants à Lausanne",
        language="fr",
        description="Query with subject 'restaurants' - only geographic filter 'à Lausanne' is extracted",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="in", category="containment", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Lausanne",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=None,
            confidence_breakdown=ConfidenceScore(
                overall=0.95,
                location_confidence=0.95,
                relation_confidence=0.95,
                reasoning=None,
            ),
            original_query="restaurants à Lausanne",
        ),
    ),
    # Example 4: Buffer query with LLM-inferred distance (English)
    ExampleQuery(
        input="near Lake Geneva",
        language="en",
        description="Proximity buffer query - LLM infers 5km distance based on medium feature scale (lake)",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=5000),
            reference_location=ReferenceLocation(
                name="Lake Geneva",
                type="lake",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.88,
                location_confidence=0.90,
                relation_confidence=0.85,
                reasoning="Medium-scale feature (lake) → 5km proximity radius inferred by LLM",
            ),
            original_query="near Lake Geneva",
        ),
    ),
    # Example 5: Negative buffer (German)
    ExampleQuery(
        input="im Herzen von Bern",
        language="de",
        description="Negative buffer (erosion) - central area",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="in_the_heart_of", category="buffer", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Bern",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=-500, buffer_from="boundary", ring_only=False, inferred=True),
            confidence_breakdown=ConfidenceScore(
                overall=0.87,
                location_confidence=0.92,
                relation_confidence=0.82,
                reasoning="Idiomatic expression 'im Herzen von' may have slight ambiguity",
            ),
            original_query="im Herzen von Bern",
        ),
    ),
    # Example 6: Directional (English)
    ExampleQuery(
        input="north of Zurich",
        language="en",
        description="Directional sector query",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="north_of", category="directional", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Zürich",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=10000, buffer_from="center", ring_only=False, inferred=True),
            confidence_breakdown=ConfidenceScore(
                overall=0.94,
                location_confidence=0.95,
                relation_confidence=0.93,
                reasoning=None,
            ),
            original_query="north of Zurich",
        ),
    ),
    # Example 7: Query with subject near generic reference - context-aware distance (English)
    ExampleQuery(
        input="cafés near the train station",
        language="en",
        description="Subject 'cafés' ignored - only geographic filter 'near the train station' extracted. LLM infers 1km distance based on small feature scale (train station)",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=1000),
            reference_location=ReferenceLocation(
                name="train station",
                type="train_station",
                type_confidence=0.70,
            ),
            buffer_config=BufferConfig(distance_m=1000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.75,
                location_confidence=0.70,
                relation_confidence=0.80,
                reasoning="Small feature (train station) context → 1km buffer inferred by LLM. Generic location reference reduces overall confidence.",
            ),
            original_query="cafés near the train station",
        ),
    ),
    # Example 8: Query with subject and explicit distance (English)
    ExampleQuery(
        input="bus stations within 2km of Lausanne",
        language="en",
        description="Subject 'bus stations' ignored - only geographic filter 'within 2km of Lausanne' extracted",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=2000),
            reference_location=ReferenceLocation(
                name="Lausanne",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=2000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.95,
                location_confidence=0.95,
                relation_confidence=0.95,
                reasoning=None,
            ),
            original_query="bus stations within 2km of Lausanne",
        ),
    ),
    # Example 9: Activity query (English) - activity completely ignored
    ExampleQuery(
        input="Hiking north of Lausanne",
        language="en",
        description="Activity 'Hiking' ignored - only geographic filter 'north of Lausanne' extracted",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="north_of", category="directional", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Lausanne",
                type="city",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=10000, buffer_from="center", ring_only=False, inferred=True),
            confidence_breakdown=ConfidenceScore(
                overall=0.95,
                location_confidence=0.95,
                relation_confidence=0.95,
                reasoning=None,
            ),
            original_query="Hiking north of Lausanne",
        ),
    ),
    # Example 10: Complex activity query (English) - all activity details ignored
    ExampleQuery(
        input="Hiking with children near Lake Geneva",
        language="en",
        description="Activity 'Hiking with children' completely ignored - only 'near Lake Geneva' extracted. LLM infers 5km based on medium feature scale (lake)",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=5000),
            reference_location=ReferenceLocation(
                name="Lake Geneva",
                type="lake",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.90,
                location_confidence=0.90,
                relation_confidence=0.90,
                reasoning="Medium feature scale (lake) context → 5km buffer inferred by LLM. Activity 'hiking' considered but not used for distance calculation.",
            ),
            original_query="Hiking with children near Lake Geneva",
        ),
    ),
    # Example 11: Contextual distance - walking (English)
    ExampleQuery(
        input="Walking distance from Zurich main railway station",
        language="en",
        description="Contextual distance 'walking distance' converted to 1km explicit distance",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=1000),
            reference_location=ReferenceLocation(
                name="Zurich main railway station",
                type="train_station",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=1000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.90,
                location_confidence=0.90,
                relation_confidence=0.90,
                reasoning="'Walking distance' converted to 1km buffer.",
            ),
            original_query="Walking distance from Zurich main railway station",
        ),
    ),
    # Example 12: Contextual distance - biking (English)
    ExampleQuery(
        input="Biking distance from Lake Geneva",
        language="en",
        description="Contextual distance 'biking distance' converted to 5km explicit distance",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=5000),
            reference_location=ReferenceLocation(
                name="Lake Geneva",
                type="lake",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.90,
                location_confidence=0.90,
                relation_confidence=0.90,
                reasoning="'Biking distance' converted to 5km buffer.",
            ),
            original_query="Biking distance from Lake Geneva",
        ),
    ),
    # Example 13: Time-based distance - 10 minute walk
    ExampleQuery(
        input="10 minutes walk from Zurich main railway station",
        language="en",
        description="Time-based distance '10 minutes walk' converted to 800m explicit distance",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=800),
            reference_location=ReferenceLocation(
                name="Zurich main railway station",
                type="train_station",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=800, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.90,
                location_confidence=0.90,
                relation_confidence=0.90,
                reasoning="'10 minutes walk' converted to 800m buffer (5km/h walking speed).",
            ),
            original_query="10 minutes walk from Zurich main railway station",
        ),
    ),
    # Example 14: Time-based distance - 15 minute bike ride
    ExampleQuery(
        input="15 minutes bike from Lake Geneva",
        language="en",
        description="Time-based distance '15 minutes bike' converted to 5000m explicit distance",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=5000),
            reference_location=ReferenceLocation(
                name="Lake Geneva",
                type="lake",
                type_confidence=0.95,
            ),
            buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.90,
                location_confidence=0.90,
                relation_confidence=0.90,
                reasoning="'15 minutes bike' converted to 5000m buffer (20km/h biking speed).",
            ),
            original_query="15 minutes bike from Lake Geneva",
        ),
    ),
    # Example 15: French proximity with location type (French)
    ExampleQuery(
        input="près de la gare d'Yverdon",
        language="fr",
        description="French proximity query - 'près de' maps to 'near', full official location name used for correct geodata lookup",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=None),
            reference_location=ReferenceLocation(
                name="Yverdon-les-Bains",
                type="train_station",
                type_confidence=0.85,
            ),
            buffer_config=BufferConfig(distance_m=5000, buffer_from="center", ring_only=False, inferred=True),
            confidence_breakdown=ConfidenceScore(
                overall=0.88,
                location_confidence=0.85,
                relation_confidence=0.90,
                reasoning="'Près de la gare d'Yverdon' - extracted full official name 'Yverdon-les-Bains' to match SwissNames3D data with train_station type",
            ),
            original_query="près de la gare d'Yverdon",
        ),
    ),
    # Example 16: Explicit distance from location with type descriptor (English)
    ExampleQuery(
        input="500m from the Lausanne railway station",
        language="en",
        description="Explicit distance from a specific location type - 'from' maps to 'near', base location name extracted from descriptor",
        output=GeoQuery(
            query_type="simple",
            spatial_relation=SpatialRelation(relation="near", category="buffer", explicit_distance=500),
            reference_location=ReferenceLocation(
                name="Lausanne",
                type="railway_station",
                type_confidence=0.90,
            ),
            buffer_config=BufferConfig(distance_m=500, buffer_from="center", ring_only=False, inferred=False),
            confidence_breakdown=ConfidenceScore(
                overall=0.92,
                location_confidence=0.90,
                relation_confidence=0.95,
                reasoning="'500m from the Lausanne railway station' - explicit 500m distance, location type inferred from 'railway station', base location 'Lausanne' extracted",
            ),
            original_query="500m from the Lausanne railway station",
        ),
    ),
]


def format_examples_for_prompt() -> str:
    """
    Format examples as text for inclusion in LLM prompt.

    Returns:
        Formatted string with all examples
    """
    examples_text = []

    for i, ex in enumerate(EXAMPLES, 1):
        examples_text.append(f"Example {i} ({ex.language}): {ex.description}")
        examples_text.append(f"Input: {ex.input}")
        examples_text.append("Output:")
        # Use model_dump with JSON serialization for clean output, exclude None values
        examples_text.append(ex.output.model_dump_json(indent=2, exclude_none=True))
        examples_text.append("")  # Blank line between examples

    return "\n".join(examples_text)


def get_examples_by_language(language: str) -> list[ExampleQuery]:
    """
    Get examples filtered by language.

    Args:
        language: Language code (en, de, fr, it)

    Returns:
        List of examples in the specified language
    """
    return [ex for ex in EXAMPLES if ex.language == language]


def get_examples_by_category(category: str) -> list[ExampleQuery]:
    """
    Get examples filtered by spatial relation category.

    Args:
        category: Relation category (containment, buffer, directional)

    Returns:
        List of examples using that category
    """
    return [ex for ex in EXAMPLES if ex.output.spatial_relation.category == category]
