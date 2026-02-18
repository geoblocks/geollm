"""
Spatial relation configuration and built-in relation definitions.
"""

from dataclasses import dataclass
from typing import Literal

from .exceptions import UnknownRelationError


@dataclass
class RelationConfig:
    """
    Configuration for a single spatial relation.

    Attributes:
        name: Relation identifier (e.g., "in", "near", "north_of")
        category: Type of spatial operation
        description: Human-readable description for LLM prompt
        default_distance_m: Default buffer distance in meters
        buffer_from: Buffer origin
        ring_only: Exclude reference feature to create ring buffer
        sector_angle_degrees: Angular sector for directional queries
        direction_angle_degrees: Direction angle in degrees (0=North, 90=East, 180=South, 270=West, clockwise)
        applies_to: Feature types this relation is commonly used with
    """

    name: str
    category: Literal["containment", "buffer", "directional"]
    description: str
    default_distance_m: float | None = None
    buffer_from: Literal["center", "boundary"] | None = None
    ring_only: bool = False
    sector_angle_degrees: float | None = None
    direction_angle_degrees: float | None = None
    applies_to: list[str] | None = None


class SpatialRelationConfig:
    """
    Registry and configuration for spatial relations.

    Manages built-in and custom spatial relations with their default parameters.
    """

    def __init__(self):
        """Initialize with built-in spatial relations."""
        self.relations: dict[str, RelationConfig] = {}
        self._initialize_defaults()

    def _initialize_defaults(self):
        """Register built-in spatial relations from ARCHITECTURE.md."""

        # ===== CONTAINMENT RELATIONS =====
        self.register_relation(
            RelationConfig(
                name="in",
                category="containment",
                description="Feature is within the reference boundary",
            )
        )

        # ===== BUFFER/PROXIMITY RELATIONS =====
        self.register_relation(
            RelationConfig(
                name="near",
                category="buffer",
                description="Proximity search with default 5km radius",
                default_distance_m=5000,
                buffer_from="center",
            )
        )

        self.register_relation(
            RelationConfig(
                name="on_shores_of",
                category="buffer",
                description="Ring buffer around lake/water boundary, excluding the water body itself",
                default_distance_m=1000,
                buffer_from="boundary",
                ring_only=True,
                applies_to=["lake", "water_body", "sea"],
            )
        )

        self.register_relation(
            RelationConfig(
                name="along",
                category="buffer",
                description="Buffer following a linear feature like a river or road",
                default_distance_m=500,
                buffer_from="boundary",
                applies_to=["river", "road", "railway", "linear_feature"],
            )
        )

        self.register_relation(
            RelationConfig(
                name="in_the_heart_of",
                category="buffer",
                description="Central area excluding periphery (negative buffer - erosion)",
                default_distance_m=-500,
                buffer_from="boundary",
            )
        )

        # ===== DIRECTIONAL RELATIONS =====
        # All directional relations use consistent defaults:
        # - Distance: 10km radius (default_distance_m=10000)
        # - Sector: 90° angular wedge (sector_angle_degrees=90)
        # - Origin: Centroid of reference location (buffer_from="center" set in enrich_with_defaults)
        # These defaults are applied automatically by enrich_with_defaults() for any directional query.
        # Convention: 0° = North, angles increase clockwise (90° = East, 180° = South, 270° = West)
        self.register_relation(
            RelationConfig(
                name="north_of",
                category="directional",
                description="Directional sector north of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=0,
            )
        )

        self.register_relation(
            RelationConfig(
                name="south_of",
                category="directional",
                description="Directional sector south of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=180,
            )
        )

        self.register_relation(
            RelationConfig(
                name="east_of",
                category="directional",
                description="Directional sector east of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=90,
            )
        )

        self.register_relation(
            RelationConfig(
                name="west_of",
                category="directional",
                description="Directional sector west of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=270,
            )
        )

        # ===== DIAGONAL DIRECTIONAL RELATIONS =====
        self.register_relation(
            RelationConfig(
                name="northeast_of",
                category="directional",
                description="Directional sector northeast of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=45,
            )
        )

        self.register_relation(
            RelationConfig(
                name="southeast_of",
                category="directional",
                description="Directional sector southeast of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=135,
            )
        )

        self.register_relation(
            RelationConfig(
                name="southwest_of",
                category="directional",
                description="Directional sector southwest of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=225,
            )
        )

        self.register_relation(
            RelationConfig(
                name="northwest_of",
                category="directional",
                description="Directional sector northwest of reference",
                default_distance_m=10000,
                sector_angle_degrees=90,
                direction_angle_degrees=315,
            )
        )

    def register_relation(self, config: RelationConfig) -> None:
        """Register a new spatial relation."""
        self.relations[config.name] = config

    def has_relation(self, name: str) -> bool:
        """Check if a relation is registered."""
        return name in self.relations

    def get_config(self, name: str) -> RelationConfig:
        """Get configuration for a relation. Raises UnknownRelationError if not found."""
        if not self.has_relation(name):
            raise UnknownRelationError(
                f"Unknown spatial relation: '{name}'. Available relations: {', '.join(sorted(self.relations.keys()))}",
                relation_name=name,
            )
        return self.relations[name]

    def list_relations(self, category: Literal["containment", "buffer", "directional"] | None = None) -> list[str]:
        """List available relation names."""
        if category is None:
            return sorted(self.relations.keys())
        return sorted(r.name for r in self.relations.values() if r.category == category)

    def format_for_prompt(self) -> str:
        """Format relations for inclusion in LLM prompt."""
        lines = []

        # Group by category
        for category in ["containment", "buffer", "directional"]:
            category_relations = [r for r in self.relations.values() if r.category == category]
            if not category_relations:
                continue

            lines.append(f"\n{category.upper()} RELATIONS:")

            for rel in sorted(category_relations, key=lambda r: r.name):
                # Build distance info
                dist_info = ""
                if rel.default_distance_m is not None:
                    dist_str = f"{abs(rel.default_distance_m)}m"
                    if rel.default_distance_m < 0:
                        dist_info = f" (default: {dist_str} erosion)"
                    else:
                        dist_info = f" (default: {dist_str})"

                # Build special flags
                flags = []
                if rel.ring_only:
                    flags.append("ring buffer")
                if rel.buffer_from:
                    flags.append(f"from {rel.buffer_from}")
                flag_info = f" [{', '.join(flags)}]" if flags else ""

                # Format line
                lines.append(f"  • {rel.name}{dist_info}{flag_info}")
                lines.append(f"    {rel.description}")

                # Add applies_to info
                if rel.applies_to:
                    lines.append(f"    (commonly used with: {', '.join(rel.applies_to)})")

        # Add notes
        lines.append("\nNOTES:")
        lines.append("  • Negative distances indicate erosion/shrinking (e.g., in_the_heart_of)")
        lines.append("  • Ring buffers exclude the reference feature itself (e.g., shores of lake)")
        lines.append("  • Buffer from 'center' vs 'boundary' determines buffer origin")

        return "\n".join(lines)
