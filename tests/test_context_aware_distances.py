"""
Tests for context-aware distance inference by LLM.

These tests verify that the LLM intelligently infers appropriate buffer distances
based on:
- Feature scale context (small/medium/large features)
- Query intent signals ("close to", "near", "in the area of")
- Erosion context for in_the_heart_of relation

These tests require an LLM with the updated context-aware prompt.
"""

import os

import pytest
from langchain.chat_models import init_chat_model

from geollm import GeoFilterParser


@pytest.fixture
def parser():
    """Create parser with OpenAI LLM for testing."""
    # Skip tests if no API key is available
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    llm = init_chat_model(model="gpt-4o", model_provider="openai", temperature=0)
    return GeoFilterParser(llm=llm)


# ===== FEATURE SCALE CONTEXT TESTS =====


def test_small_feature_context_train_station(parser):
    """Test that 'near train station' uses small feature distance (~1km)."""
    result = parser.parse("Near Zurich main railway station")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    # Small feature: expect 500m-2km range (should be ~1km)
    assert 500 <= result.buffer_config.distance_m <= 2000


def test_small_feature_context_monument(parser):
    """Test that 'near monument' uses small feature distance (~1km)."""
    result = parser.parse("Near the Matterhorn monument")

    assert result.spatial_relation.relation == "near"
    # Small feature: expect 500m-2km range
    assert 500 <= result.buffer_config.distance_m <= 2000


def test_medium_feature_context_lake(parser):
    """Test that 'near lake' uses medium feature distance (~5km)."""
    result = parser.parse("Near Lake Geneva")

    assert result.spatial_relation.relation == "near"
    assert result.spatial_relation.category == "buffer"
    # Medium feature: expect 3km-7km range (should be ~5km)
    assert 3000 <= result.buffer_config.distance_m <= 7000


def test_medium_feature_context_city(parser):
    """Test that 'near city' uses medium feature distance (~5km)."""
    result = parser.parse("Near Lausanne")

    assert result.spatial_relation.relation == "near"
    # Medium feature: expect 3km-7km range
    assert 3000 <= result.buffer_config.distance_m <= 7000


def test_large_feature_context_mountain(parser):
    """Test that 'near mountain' uses large feature distance (~10-15km)."""
    result = parser.parse("Near the Matterhorn")

    assert result.spatial_relation.relation == "near"
    # Large feature: expect 8km-20km range (should be ~10-15km)
    assert 8000 <= result.buffer_config.distance_m <= 20000


def test_large_feature_context_region(parser):
    """Test that 'near region' uses large feature distance (~10-15km)."""
    result = parser.parse("Near the Valais canton")

    assert result.spatial_relation.relation == "near"
    # Large feature: expect 8km-20km range
    assert 8000 <= result.buffer_config.distance_m <= 20000


# ===== QUERY INTENT CONTEXT TESTS =====


def test_intent_close_to(parser):
    """Test that 'close to' signals tight proximity (~1-2km)."""
    result = parser.parse("Close to Lake Geneva")

    assert result.spatial_relation.relation == "near"
    # "Close to" intent: expect 1km-3km range (should be ~2km)
    assert 1000 <= result.buffer_config.distance_m <= 3000


def test_intent_next_to(parser):
    """Test that 'next to' signals very tight proximity (~500m-1km)."""
    result = parser.parse("Next to Zurich main station")

    assert result.spatial_relation.relation == "near"
    # "Next to" intent: expect 300m-2km range
    assert 300 <= result.buffer_config.distance_m <= 2000


def test_intent_right_near(parser):
    """Test that 'right near' signals tight proximity (~1-2km)."""
    result = parser.parse("Right near Bern")

    assert result.spatial_relation.relation == "near"
    # "Right near" intent: expect 500m-3km range
    assert 500 <= result.buffer_config.distance_m <= 3000


def test_intent_in_area_of(parser):
    """Test that 'in the area of' signals wide area (~10km+)."""
    result = parser.parse("In the area of Geneva")

    assert result.spatial_relation.relation == "near"
    # "In the area of" intent: expect 8km-15km range
    assert 8000 <= result.buffer_config.distance_m <= 15000


def test_intent_in_region_of(parser):
    """Test that 'in the region of' signals wide area (~10km+)."""
    result = parser.parse("In the region of Lausanne")

    assert result.spatial_relation.relation == "near"
    # "In the region of" intent: expect 8km-20km range
    assert 8000 <= result.buffer_config.distance_m <= 20000


# ===== COMBINED CONTEXT TESTS =====


def test_combined_small_feature_close_to(parser):
    """Test combining small feature scale + 'close to' intent."""
    result = parser.parse("Close to Zurich train station")

    assert result.spatial_relation.relation == "near"
    # Small feature + "close to": expect very tight ~500m-1500m
    assert 300 <= result.buffer_config.distance_m <= 2000


def test_combined_large_feature_wide_intent(parser):
    """Test combining large feature + wide area intent."""
    result = parser.parse("In the area of the Matterhorn")

    assert result.spatial_relation.relation == "near"
    # Large feature + wide intent: expect very wide ~15km+
    assert 10000 <= result.buffer_config.distance_m <= 25000


# ===== EROSION CONTEXT TESTS (in_the_heart_of) =====


def test_erosion_small_area_neighborhood(parser):
    """Test that 'in the heart of' small area uses shallow erosion (-500m)."""
    result = parser.parse("In the heart of Lausanne old town")

    assert result.spatial_relation.relation == "in_the_heart_of"
    assert result.spatial_relation.category == "buffer"
    # Small area: expect -300m to -800m erosion (should be ~-500m)
    assert -800 <= result.buffer_config.distance_m <= -300


def test_erosion_medium_area_city(parser):
    """Test that 'in the heart of' medium area uses medium erosion (~-1000m)."""
    result = parser.parse("In the heart of Zurich")

    assert result.spatial_relation.relation == "in_the_heart_of"
    # Medium area: expect -700m to -1500m erosion
    assert -1500 <= result.buffer_config.distance_m <= -700


def test_erosion_large_area_region(parser):
    """Test that 'in the heart of' large area uses deep erosion (~-2000m+)."""
    result = parser.parse("In the heart of Valais")

    assert result.spatial_relation.relation == "in_the_heart_of"
    # Large area: expect -1500m to -3000m erosion
    assert -3000 <= result.buffer_config.distance_m <= -1500


# ===== FALLBACK TO DEFAULT TESTS =====


def test_fallback_generic_near_no_context(parser):
    """Test that generic 'near' without context falls back to 5km default."""
    result = parser.parse("Near XYZ123")  # Non-existent location

    assert result.spatial_relation.relation == "near"
    # Should use 5km default when no clear context
    # Allow some flexibility if LLM infers context: 3km-7km
    assert 3000 <= result.buffer_config.distance_m <= 7000


def test_fallback_in_heart_of_no_context(parser):
    """Test that 'in the heart of' without context falls back to -500m default."""
    result = parser.parse("In the heart of XYZ123")  # Non-existent location

    assert result.spatial_relation.relation == "in_the_heart_of"
    # Should use -500m default when no clear context
    # Allow some flexibility: -300m to -800m
    assert -800 <= result.buffer_config.distance_m <= -300


# ===== EXPLICIT DISTANCE OVERRIDES CONTEXT =====


def test_explicit_distance_overrides_feature_scale(parser):
    """Test that explicit distance overrides feature scale context."""
    result = parser.parse("Near the Matterhorn within 2km")

    # Explicit "2km" should override large feature context
    assert result.spatial_relation.explicit_distance == 2000
    assert result.buffer_config.distance_m == 2000


def test_explicit_distance_overrides_intent_signal(parser):
    """Test that explicit distance overrides intent signals."""
    result = parser.parse("Close to Lake Geneva within 10km")

    # Explicit "10km" should override "close to" intent
    assert result.spatial_relation.explicit_distance == 10000
    assert result.buffer_config.distance_m == 10000


def test_explicit_erosion_overrides_area_context(parser):
    """Test that explicit erosion distance overrides area context."""
    result = parser.parse("In the heart of Valais with 3km erosion")

    # Explicit "3km erosion" should override large area context
    assert result.spatial_relation.explicit_distance == -3000
    assert result.buffer_config.distance_m == -3000
