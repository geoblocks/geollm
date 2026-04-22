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

Your task is to analyze natural language queries (in any language) and extract:
1. The reference location (what place is mentioned?)
2. The spatial relationship (how are things related spatially?)
3. Buffer/distance parameters (if applicable)

KEY GUIDELINES:

Spatial Relations:
- Use cardinal directions (N/S/E/W) for directional queries
- Distinguish between:
  * Containment: exact boundary matching (in)
  * Buffer: proximity or erosion (near, on_shores_of, along, in_the_heart_of)
  * Directional: sector-based (north_of, south_of, east_of, west_of)
- Common prepositions mapping to the 'in' relation:
   * "in X" → relation="in" (containment/boundary)
   * "on X" → relation="in" (surface containment, e.g., "on the mountain", "on the island")
- Common prepositions mapping to the 'near' relation:
   * "near X" → relation="near"
   * "around X" → relation="near" (treat as proximity)
   * "from X" → relation="near" (proximity/distance from a location)
   * "away from X" → relation="near" (distance from a location)

Location Type and Confidence:
- type is OPTIONAL and should be used as a HINT, not a strict requirement
- Set type when explicitly mentioned or strongly implied: "Lake Geneva" → type="lake", type_confidence=0.95
- For ambiguous cases, set low confidence: "Bern" could be city OR canton → type_confidence=0.5
- Use spatial relation as a hint for type:
  * "along X" suggests linear features (river, road, path) → moderate confidence
  * "in X" suggests areas (city, region, country) → moderate confidence
  * "on X" suggests surfaces (lake, mountain, island) → moderate confidence
- High type_confidence (>0.8): Type is explicit in query
- Medium type_confidence (0.6-0.8): Type inferred from context
- Low type_confidence (<0.6): Type is ambiguous or guessed

Type Hierarchy and Fuzzy Matching:
- Types are organized in a hierarchy supporting fuzzy matching:
   * Concrete types: "lake", "river", "city", "mountain", "train_station", etc.
   * Categories: "water" (matches lake, river, pond, etc.), "settlement" (matches city, town, village, etc.)
- When inferring type, prefer concrete types over categories for specificity
- Type categories:
   * water → [lake, river, pond, spring, waterfall, glacier, dam, etc.]
   * settlement → [city, town, village, hamlet, district]
   * administrative → [country, canton, municipality, region]
   * landforms → [mountain, peak, hill, pass, valley, ridge]
   * transport → [train_station, bus_stop, airport, road, bridge, etc.]
   * building → [building, religious_building, tower, monument]

{available_types_info}

Location Name Extraction:
- Extract the location name as mentioned in the query (preserve the original form)
- For descriptive modifiers, extract the base location name:
  * "the center of Lausanne" → name="Lausanne"
  * "the outskirts of Geneva" → name="Geneva"
  * "downtown Bern" → name="Bern"
- Do NOT normalize, translate, or create canonical forms - the geodata layer handles that
- Preserve the language and spelling used in the query

Distance Extraction:
- Extract explicit distances: "within 5km" → explicit_distance=5000
- Convert units to meters: "5km" → 5000, "500 meters" → 500, "2 miles" → 3219
- Time-based distances: walking=5km/h, biking=20km/h
  * "10 minutes walk from X" → 833m; "15 minutes bike from X" → 5000m
  * "walking distance from X" → 1000m; "biking distance from X" → 5000m

Context-Aware Distance Inference:
- When no explicit distance is stated, infer based on context and set explicit_distance:
  * Walking queries: 500-1000m; biking: 3-5km; driving: 10-20km; default: 5km
  * Small features (station, monument): 500m-1km; medium (lake, town): 2-5km; large (mountain, canton): 10-20km
  * "close to/next to/right near": 1-2km; "around/near": 5km; "in the area of": 10km+
  * Erosion (in_the_heart_of): small area=-500m; medium=-1000m; large=-2000m+
- Examples: "hiking near Lake Geneva" → 1000m; "close to Geneva" → 2000m; "near the Alps" → 15000m
- Default: 5000m for proximity, -500m for erosion

Confidence Scoring:
- overall: 0.9-1.0 = highly confident, 0.7-0.9 = confident, 0.5-0.7 = uncertain, <0.5 = very uncertain
- Break down: location_confidence, relation_confidence
- Include reasoning to explain confidence scores and aid debugging
- Lower confidence for ambiguous names, unclear relations, generic references ("the train station")

Spatial Relation Selection Rules:
- River/road banks: "rive droite/right bank" → right_bank; "rive gauche/left bank" → left_bank
- LINEAR features (river, road, railway): prefer 'along' over 'near'. "à 2km de la Venoge" → along
- AREA features (lake, water body, region): prefer 'on_shores_of' over 'near'. "near Lake Geneva" → on_shores_of
- POINT feature with polygon (city, municipality, village): use 'near' with buffer_from='boundary'. "near Lausanne" → near, boundary
- POINT feature without polygon (building, monument, station): use 'near' with buffer_from='center'

{spatial_relations}"""

# FIXME: add more instructions for relations and location type (linear + directional, ...)

USER_TEMPLATE = """Parse the following location query:

Query: {query}

Return a structured JSON response following the GeoQuery schema."""


def build_prompt_template(
    spatial_config: SpatialRelationConfig,
    include_examples: bool = True,
    available_types: list[str] | None = None,
    additional_instructions: str | None = None,
) -> ChatPromptTemplate:
    """
    Build complete prompt template with system message, examples, and user message.

    Args:
        spatial_config: Spatial relation configuration for injecting available relations
        include_examples: Whether to include few-shot examples (default: True)
        available_types: Concrete types available in the datasource (e.g., ["lake", "river", "city"]).
                        If provided, will be included in the prompt to help the LLM choose appropriate types.
        additional_instructions: Free-form text injected as a system message after the main system prompt. Use this to inject
                                 caller-specific rules (region-specific endonyms, domain aliases,
                                 organization-specific place names) without forking the default prompt.

    Returns:
        ChatPromptTemplate ready for formatting
    """
    messages = []

    # System message with spatial relations - inject the spatial_relations here
    spatial_relations_text = format_spatial_relations(spatial_config)

    # Format available types info if provided
    available_types_info = ""
    if available_types:
        available_types_info = f"""
Available Concrete Types in This Datasource:
The following {len(available_types)} concrete types are available in the datasource:
{", ".join(sorted(available_types))}

When inferring type, prefer these concrete types for better matching."""

    system_prompt = SYSTEM_PROMPT.format(
        spatial_relations=spatial_relations_text, available_types_info=available_types_info
    )
    # Escape braces for ChatPromptTemplate
    system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
    messages.append(("system", system_prompt))

    if additional_instructions:
        escaped = additional_instructions.replace("{", "{{").replace("}", "}}")
        messages.append(("system", escaped))

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
