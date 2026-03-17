"""
Location type hierarchy and fuzzy matching for geographic features.

This module defines the standard type hierarchy used across all datasources.
Each datasource maps its native types to this hierarchy, enabling consistent
type handling, fuzzy matching, and LLM-aware type suggestions.

The hierarchy is organized into categories (water, administrative, settlement, etc.)
to support fuzzy matching. For example, querying type="water" matches features
of type "lake", "river", "pond", etc.
"""

# Type hierarchy: category → list of concrete types
# This enables fuzzy matching (category matches multiple concrete types)
TYPE_HIERARCHY: dict[str, list[str]] = {
    "water": [
        "lake",
        "river",
        "pond",
        "spring",
        "waterfall",
        "glacier",
        "ditch",
        "weir",
        "dam",
    ],
    "landforms": [
        "mountain",
        "peak",
        "hill",
        "pass",
        "valley",
        "ridge",
        "plain",
        "rock_head",
        "boulder",
        "massif",
    ],
    "mountain": [
        "mountain",
        "peak",
    ],
    "natural": [
        "cave",
        "forest",
        "nature_reserve",
        "alpine_pasture",
    ],
    "island": [
        "island",
        "peninsula",
    ],
    "administrative": [
        "country",
        "canton",
        "municipality",
        "region",
        "department",
        "area",
        "border_marker",
        "arrondissement",
    ],
    "settlement": [
        "city",
        "town",
        "village",
        "hamlet",
        "district",
    ],
    "building": [
        "building",
        "religious_building",
        "tower",
        "monument",
        "fountain",
    ],
    "transport": [
        "train_station",
        "bus_stop",
        "boat_stop",
        "road",
        "bridge",
        "tunnel",
        "exit",
        "entrance_exit",
        "junction",
        "railway",
        "railway_area",
        "lift",
        "loading_station",
        "airport",
        "heliport",
        "ferry",
    ],
    "amenity": [
        "restaurant",
        "hospital",
        "school",
        "parking",
        "park",
        "swimming_pool",
        "sports_facility",
        "leisure_facility",
        "zoo",
        "camping",
        "rest_area",
        "standing_area",
        "cemetery",
        "fairground",
    ],
    "infrastructure": [
        "power_plant",
        "wastewater_treatment",
        "waste_incineration",
        "landfill",
        "quarry",
    ],
    "other": [
        "field_name",
        "local_name",
        "viewpoint",
        "private_driving_area",
        "correctional_facility",
        "military_training_area",
        "customs",
        "historical_site",
        "monastery",
        "unknown",
    ],
}

# Flatten hierarchy for easy lookup: concrete_type → category
TYPE_TO_CATEGORY: dict[str, str] = {}
for category, types in TYPE_HIERARCHY.items():
    for concrete_type in types:
        TYPE_TO_CATEGORY[concrete_type] = category

# All concrete types (sorted)
ALL_TYPES: list[str] = sorted(set(TYPE_TO_CATEGORY.keys()))

# All categories
ALL_CATEGORIES: list[str] = sorted(TYPE_HIERARCHY.keys())


def normalize_type(type_hint: str | None) -> str | None:
    """
    Normalize a type hint. If it's a concrete type, return as-is.
    If it's a category, keep as-is (will be used for fuzzy matching).
    If it's not in the hierarchy, convert to lowercase.
    """
    if type_hint is None:
        return None

    lowered = type_hint.lower().strip()

    # Valid concrete type or category
    if lowered in TYPE_TO_CATEGORY or lowered in TYPE_HIERARCHY:
        return lowered

    # Unknown type - return lowered
    return lowered


def get_matching_types(type_hint: str) -> list[str]:
    """
    Get concrete types matching a type hint (fuzzy matching).

    Examples:
        get_matching_types("lake") → ["lake"]
        get_matching_types("water") → ["lake", "river", "pond", "spring", ...]
        get_matching_types("unknown") → ["unknown"]
    """
    normalized = normalize_type(type_hint)
    if not normalized:
        return []

    # If it's a category, return all concrete types in that category
    if normalized in TYPE_HIERARCHY:
        return TYPE_HIERARCHY[normalized]

    # If it's a concrete type, return it
    if normalized in TYPE_TO_CATEGORY:
        return [normalized]

    # Unknown type - return empty (no match)
    return []
