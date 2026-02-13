"""
Prompt templates and builders for LLM query parsing.
"""

from langchain_core.prompts import ChatPromptTemplate

from .examples import format_examples_for_prompt
from .spatial_config import SpatialRelationConfig

# System prompt defining the GIS expert role and guidelines
SYSTEM_PROMPT = """You are a GIS expert specialized in parsing location queries into structured geographic queries.

CRITICAL SCOPE LIMITATION:
Your ONLY task is to extract the GEOGRAPHIC FILTER from natural language queries.
- Extract: reference location + spatial relation + distance parameters
- IGNORE: The subject/activity/feature being searched for (e.g., "hiking", "restaurants", "hotels")
- The parent application handles subject/feature filtering - you focus solely on the geographic component

Examples of scope:
- "Hiking north of Lausanne" → Extract ONLY: "north of Lausanne" (ignore "Hiking")
- "Restaurants in Bern" → Extract ONLY: "in Bern" (ignore "Restaurants")
- "Hotels within 5km of Geneva" → Extract ONLY: "within 5km of Geneva" (ignore "Hotels")
- "Hiking with children near Lake Geneva" → Extract ONLY: "near Lake Geneva" (ignore "Hiking with children")

Your task is to analyze natural language queries (in any language) and extract:
1. The reference location (what place is mentioned?)
2. The spatial relationship (how are things related spatially?)
3. Buffer/distance parameters (if applicable)

KEY GUIDELINES:

Spatial Relations:
- Use cardinal directions (N/S/E/W) for directional queries
- Distinguish between:
  * Containment: exact boundary matching (in)
  * Buffer: proximity or erosion (near, around, on_shores_of, in_the_heart_of)
  * Directional: sector-based (north_of, south_of, east_of, west_of)

Location Type and Confidence:
- type is OPTIONAL and should be used as a HINT, not a strict requirement
- Set type when explicitly mentioned or strongly implied: "Lake Geneva" → type="lake", type_confidence=0.95
- For ambiguous cases, set low confidence or omit type entirely:
  * "Bern" could be city OR canton → type="city", type_confidence=0.5
  * "Rhone" could be river OR road → type="river", type_confidence=0.6
  * "Montreux" (unclear) → type=None, type_confidence=None
- Use spatial relation as a hint for type:
  * "along X" suggests linear features (river, road, path) → moderate confidence
  * "in X" suggests areas (city, region, country) → moderate confidence
  * "on X" suggests surfaces (lake, mountain, island) → moderate confidence
- High type_confidence (>0.8): Type is explicit in query
- Medium type_confidence (0.6-0.8): Type inferred from context
- Low type_confidence (<0.6): Type is ambiguous or guessed

Location Name Extraction:
- Extract the location name as mentioned in the query (preserve the original form)
- Examples: "Lausanne" → name="Lausanne", "Lake Geneva" → name="Lake Geneva", "Bern" → name="Bern"
- Do NOT normalize, translate, or create canonical forms - the geodata layer handles that
- Preserve the language and spelling used in the query

Location Disambiguation:
- Location ambiguity (e.g., "Paris" could be Paris, France or Paris, Texas) is handled by the geodata/geocoding layer
- Preserve location names exactly as mentioned in the query without trying to disambiguate
- The downstream geocoding service will handle ranking and disambiguation based on context, population, and prominence

Distance Extraction:
- Extract explicit distances: "within 5km" → explicit_distance=5000
- Convert units to meters: "5km" → 5000, "500 meters" → 500, "2 miles" → 3219
- Recognize and calculate time-based distances using these speeds:
  * Walking: 5 km/h
  * Biking: 20 km/h
- Examples:
  * "10 minutes walk from X" → 10 * (5000/60) = 833m
  * "15 minutes bike from X" → 15 * (20000/60) = 5000m
  * "walking distance from X" → 1000m (typical walk)
  * "biking distance from X" → 5000m (typical bike ride)
- Leave null if not explicitly stated (defaults will be applied)

Buffer Configuration:
- Positive distances = expansion (near, around)
- Negative distances = erosion (in_the_heart_of, deep_inside)
- ring_only=true excludes reference feature (e.g., "on shores of lake" excludes the water)
- buffer_from="center" for proximity, "boundary" for shores/erosion

Confidence Scoring:
- overall: 0.9-1.0 = highly confident, 0.7-0.9 = confident, 0.5-0.7 = uncertain, <0.5 = very uncertain
- Break down: location_confidence, relation_confidence
- Include reasoning for confidence < 0.7
- Lower confidence for:
  * Ambiguous location names
  * Unclear spatial relationships
  * Generic references ("the train station" without city)
  * Idiomatic expressions with multiple interpretations

Query Type:
- Always use "simple" for Phase 1
- Future support: "compound", "split", "boolean"

{spatial_relations}"""


USER_TEMPLATE = """Parse the following location query:

Query: {query}

Return a structured JSON response following the GeoQuery schema."""


def build_prompt_template(spatial_config: SpatialRelationConfig, include_examples: bool = True) -> ChatPromptTemplate:
    """
    Build complete prompt template with system message, examples, and user message.

    Args:
        spatial_config: Spatial relation configuration for injecting available relations
        include_examples: Whether to include few-shot examples (default: True)

    Returns:
        ChatPromptTemplate ready for formatting
    """
    messages = []

    # System message with spatial relations - inject the spatial_relations here
    spatial_relations_text = format_spatial_relations(spatial_config)
    system_prompt = SYSTEM_PROMPT.format(spatial_relations=spatial_relations_text)
    # Escape braces for ChatPromptTemplate
    system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
    messages.append(("system", system_prompt))

    # Few-shot examples (optional but recommended)
    if include_examples:
        examples_text = format_examples_for_prompt()
        examples_message = f"""EXAMPLES:

The following examples demonstrate correct parsing for various query types:

{examples_text}"""
        # Escape braces for ChatPromptTemplate
        examples_message = examples_message.replace("{", "{{").replace("}", "}}")
        messages.append(("system", examples_message))

    # User message template - only this has a placeholder for format_messages
    messages.append(("user", USER_TEMPLATE))

    return ChatPromptTemplate.from_messages(messages)


def format_spatial_relations(config: SpatialRelationConfig) -> str:
    """
    Format spatial relations for prompt injection.

    This is a helper that can be used when formatting the prompt.

    Args:
        config: Spatial relation configuration

    Returns:
        Formatted string describing available relations
    """
    return f"""
AVAILABLE SPATIAL RELATIONS:
{config.format_for_prompt()}

When parsing queries, use ONLY the relations listed above.
"""
