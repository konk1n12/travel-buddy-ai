"""
Tests for POI filtering (radius, BlockType, and heuristic filters).
"""
import pytest

from src.domain.models import BlockType
from src.infrastructure.poi_providers import (
    haversine_distance_km,
    is_poi_suitable_for_block_type,
    BLOCK_TYPE_ALLOWED_CATEGORIES,
    MEAL_EXCLUDE_NAME_KEYWORDS,
)


class TestHaversineDistance:
    """Tests for Haversine distance calculation."""

    def test_same_point_distance_zero(self):
        """Test distance between same points is zero."""
        distance = haversine_distance_km(48.8566, 2.3522, 48.8566, 2.3522)
        assert distance == pytest.approx(0, abs=0.01)

    def test_paris_to_eiffel_tower(self):
        """Test known distance: Paris center to Eiffel Tower (~3km)."""
        # Paris city center (approx)
        paris_lat, paris_lon = 48.8566, 2.3522
        # Eiffel Tower
        eiffel_lat, eiffel_lon = 48.8584, 2.2945

        distance = haversine_distance_km(paris_lat, paris_lon, eiffel_lat, eiffel_lon)
        # Should be approximately 4-5 km
        assert 3 < distance < 6

    def test_paris_to_lyon(self):
        """Test longer distance: Paris to Lyon (~400km)."""
        paris_lat, paris_lon = 48.8566, 2.3522
        lyon_lat, lyon_lon = 45.7640, 4.8357

        distance = haversine_distance_km(paris_lat, paris_lon, lyon_lat, lyon_lon)
        # Should be approximately 390-420 km
        assert 380 < distance < 430

    def test_antipodal_points(self):
        """Test maximum distance (roughly half Earth circumference)."""
        # Approximately antipodal points
        distance = haversine_distance_km(0, 0, 0, 180)
        # Should be approximately 20,000 km (half of Earth's circumference)
        assert 19000 < distance < 21000


class TestBlockTypeFiltering:
    """Tests for BlockType-based POI filtering."""

    def test_restaurant_suitable_for_meal(self):
        """Test that restaurant is suitable for MEAL block."""
        assert is_poi_suitable_for_block_type(
            poi_name="Le Comptoir",
            poi_category="restaurant",
            poi_tags=["restaurant", "french"],
            block_type=BlockType.MEAL,
        )

    def test_restaurant_not_suitable_for_activity(self):
        """Test that restaurant is not suitable for ACTIVITY block."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Le Comptoir",
            poi_category="restaurant",
            poi_tags=["restaurant", "french"],
            block_type=BlockType.ACTIVITY,
        )

    def test_museum_suitable_for_activity(self):
        """Test that museum is suitable for ACTIVITY block."""
        assert is_poi_suitable_for_block_type(
            poi_name="Louvre Museum",
            poi_category="museum",
            poi_tags=["museum", "art"],
            block_type=BlockType.ACTIVITY,
        )

    def test_museum_not_suitable_for_meal(self):
        """Test that museum is not suitable for MEAL block."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Louvre Museum",
            poi_category="museum",
            poi_tags=["museum", "art"],
            block_type=BlockType.MEAL,
        )

    def test_nightclub_suitable_for_nightlife(self):
        """Test that nightclub is suitable for NIGHTLIFE block."""
        assert is_poi_suitable_for_block_type(
            poi_name="Concrete",
            poi_category="nightlife",
            poi_tags=["night_club", "techno"],
            block_type=BlockType.NIGHTLIFE,
        )

    def test_bar_suitable_for_nightlife(self):
        """Test that bar is suitable for NIGHTLIFE block."""
        assert is_poi_suitable_for_block_type(
            poi_name="The Bar",
            poi_category="bar",
            poi_tags=["bar"],
            block_type=BlockType.NIGHTLIFE,
        )

    def test_bar_suitable_for_meal(self):
        """Test that bar is also suitable for MEAL block (gastropub)."""
        assert is_poi_suitable_for_block_type(
            poi_name="The Gastropub",
            poi_category="bar",
            poi_tags=["bar", "food"],
            block_type=BlockType.MEAL,
        )

    def test_rest_block_always_passes(self):
        """Test that REST blocks accept any POI (or none)."""
        assert is_poi_suitable_for_block_type(
            poi_name="Any POI",
            poi_category="restaurant",
            poi_tags=[],
            block_type=BlockType.REST,
        )

    def test_travel_block_always_passes(self):
        """Test that TRAVEL blocks accept any POI (or none)."""
        assert is_poi_suitable_for_block_type(
            poi_name="Any POI",
            poi_category="museum",
            poi_tags=[],
            block_type=BlockType.TRAVEL,
        )


class TestMealHeuristicFilters:
    """Tests for name-based heuristic filters for meal blocks."""

    def test_cooking_class_excluded_from_meal(self):
        """Test that cooking class is excluded from meal blocks."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Paris Cooking Class",
            poi_category="restaurant",
            poi_tags=["restaurant"],
            block_type=BlockType.MEAL,
        )

    def test_cooking_school_excluded_from_meal(self):
        """Test that cooking school is excluded from meal blocks."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Le Cordon Bleu Cooking School",
            poi_category="restaurant",
            poi_tags=["restaurant"],
            block_type=BlockType.MEAL,
        )

    def test_wine_tasting_class_excluded_from_meal(self):
        """Test that wine tasting class is excluded from meal blocks."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Wine Tasting Class Paris",
            poi_category="restaurant",
            poi_tags=["restaurant", "bar"],
            block_type=BlockType.MEAL,
        )

    def test_workshop_excluded_from_meal(self):
        """Test that workshop is excluded from meal blocks."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Culinary Workshop Experience",
            poi_category="restaurant",
            poi_tags=["restaurant"],
            block_type=BlockType.MEAL,
        )

    def test_food_tour_excluded_from_meal(self):
        """Test that food tour is excluded from meal blocks."""
        assert not is_poi_suitable_for_block_type(
            poi_name="Paris Food Tour with Guide",
            poi_category="restaurant",
            poi_tags=["restaurant"],
            block_type=BlockType.MEAL,
        )

    def test_regular_restaurant_included_for_meal(self):
        """Test that regular restaurant is included for meal blocks."""
        assert is_poi_suitable_for_block_type(
            poi_name="Le Comptoir du Relais",
            poi_category="restaurant",
            poi_tags=["restaurant", "french"],
            block_type=BlockType.MEAL,
        )

    def test_cafe_included_for_meal(self):
        """Test that regular cafe is included for meal blocks."""
        assert is_poi_suitable_for_block_type(
            poi_name="Café de Flore",
            poi_category="cafe",
            poi_tags=["cafe", "breakfast"],
            block_type=BlockType.MEAL,
        )

    def test_case_insensitive_filtering(self):
        """Test that filtering is case-insensitive."""
        # "CLASS" should also be caught
        assert not is_poi_suitable_for_block_type(
            poi_name="FRENCH COOKING CLASS",
            poi_category="restaurant",
            poi_tags=["restaurant"],
            block_type=BlockType.MEAL,
        )


class TestBlockTypeAllowedCategories:
    """Tests for BlockType category allowlists."""

    def test_meal_allowed_categories(self):
        """Test that MEAL has expected categories."""
        expected = {"restaurant", "cafe", "bar", "bakery", "food"}
        assert BLOCK_TYPE_ALLOWED_CATEGORIES[BlockType.MEAL] == expected

    def test_activity_allowed_categories(self):
        """Test that ACTIVITY has expected categories."""
        expected = {"museum", "attraction", "park", "shopping", "wellness"}
        assert BLOCK_TYPE_ALLOWED_CATEGORIES[BlockType.ACTIVITY] == expected

    def test_nightlife_allowed_categories(self):
        """Test that NIGHTLIFE has expected categories."""
        expected = {"nightlife", "bar"}
        assert BLOCK_TYPE_ALLOWED_CATEGORIES[BlockType.NIGHTLIFE] == expected


class TestMealExcludeKeywords:
    """Tests for meal exclude keywords."""

    def test_expected_keywords_present(self):
        """Test that expected keywords are in the exclude list."""
        expected_keywords = ["class", "school", "course", "workshop", "tour"]
        for keyword in expected_keywords:
            assert keyword in MEAL_EXCLUDE_NAME_KEYWORDS, f"Missing keyword: {keyword}"

    def test_regular_food_words_not_excluded(self):
        """Test that regular food-related words are not in exclude list."""
        non_excluded = ["restaurant", "cafe", "bistro", "brasserie", "food"]
        for word in non_excluded:
            assert word not in MEAL_EXCLUDE_NAME_KEYWORDS, f"Should not exclude: {word}"
