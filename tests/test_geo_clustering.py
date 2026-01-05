"""
Tests for geographic clustering service.
"""
import pytest
from uuid import uuid4

from src.application.geo_clustering import (
    GeoClusterer,
    District,
    ClusteringResult,
    haversine_distance_km,
)
from src.domain.models import POICandidate


def create_test_poi(
    name: str,
    lat: float,
    lon: float,
    category: str = "restaurant",
    rating: float = 4.5,
    tags: list[str] = None,
) -> POICandidate:
    """Create a test POI candidate."""
    return POICandidate(
        poi_id=uuid4(),
        name=name,
        category=category,
        tags=tags or [category],
        rating=rating,
        location=f"{lat}, {lon}",
        lat=lat,
        lon=lon,
        rank_score=rating * 10,
    )


class TestHaversineDistance:
    """Tests for haversine distance calculation."""

    def test_same_point_returns_zero(self):
        """Same point should return 0 distance."""
        distance = haversine_distance_km(48.8566, 2.3522, 48.8566, 2.3522)
        assert distance == 0.0

    def test_known_distance_paris_to_london(self):
        """Test known distance: Paris to London ~343 km."""
        # Paris
        lat1, lon1 = 48.8566, 2.3522
        # London
        lat2, lon2 = 51.5074, -0.1278

        distance = haversine_distance_km(lat1, lon1, lat2, lon2)

        # Should be approximately 343 km (allow 5% tolerance)
        assert 325 < distance < 360

    def test_short_distance_within_city(self):
        """Test short distance within a city (< 5km)."""
        # Eiffel Tower
        lat1, lon1 = 48.8584, 2.2945
        # Louvre
        lat2, lon2 = 48.8606, 2.3376

        distance = haversine_distance_km(lat1, lon1, lat2, lon2)

        # Should be approximately 3.3 km
        assert 3.0 < distance < 4.0


class TestDistrict:
    """Tests for District class."""

    def test_add_poi_updates_stats(self):
        """Adding POI should update category counts and average rating."""
        district = District(
            district_id="A",
            name="Test District",
            center_lat=48.8566,
            center_lon=2.3522,
        )

        poi1 = create_test_poi("Cafe 1", 48.8570, 2.3530, "cafe", 4.5)
        poi2 = create_test_poi("Restaurant 1", 48.8560, 2.3510, "restaurant", 4.8)

        district.add_poi(poi1)
        assert district.total_pois == 1
        assert district.category_counts["cafe"] == 1
        assert district.avg_rating == 4.5

        district.add_poi(poi2)
        assert district.total_pois == 2
        assert district.category_counts["restaurant"] == 1
        assert district.avg_rating == pytest.approx(4.65, rel=0.01)

    def test_has_category_matches_exact(self):
        """has_category should match exact category."""
        district = District(
            district_id="A",
            name="Test",
            center_lat=48.8566,
            center_lon=2.3522,
        )
        district.add_poi(create_test_poi("Cafe", 48.8570, 2.3530, "cafe"))

        assert district.has_category(["cafe"])
        assert not district.has_category(["museum"])

    def test_has_category_matches_tags(self):
        """has_category should match POI tags."""
        district = District(
            district_id="A",
            name="Test",
            center_lat=48.8566,
            center_lon=2.3522,
        )
        poi = create_test_poi("Brunch Place", 48.8570, 2.3530, "restaurant", tags=["breakfast", "brunch"])
        district.add_poi(poi)

        assert district.has_category(["breakfast"])
        assert district.has_category(["brunch"])
        assert not district.has_category(["dinner"])

    def test_get_pois_by_category_filters_rating(self):
        """get_pois_by_category should filter by minimum rating."""
        district = District(
            district_id="A",
            name="Test",
            center_lat=48.8566,
            center_lon=2.3522,
        )
        district.add_poi(create_test_poi("Good Cafe", 48.8570, 2.3530, "cafe", 4.8))
        district.add_poi(create_test_poi("Bad Cafe", 48.8571, 2.3531, "cafe", 3.5))

        pois = district.get_pois_by_category(["cafe"], min_rating=4.5)

        assert len(pois) == 1
        assert pois[0].name == "Good Cafe"

    def test_get_pois_by_category_excludes_ids(self):
        """get_pois_by_category should exclude specified POI IDs."""
        district = District(
            district_id="A",
            name="Test",
            center_lat=48.8566,
            center_lon=2.3522,
        )
        poi1 = create_test_poi("Cafe 1", 48.8570, 2.3530, "cafe", 4.8)
        poi2 = create_test_poi("Cafe 2", 48.8571, 2.3531, "cafe", 4.7)
        district.add_poi(poi1)
        district.add_poi(poi2)

        pois = district.get_pois_by_category(["cafe"], exclude_ids={poi1.poi_id})

        assert len(pois) == 1
        assert pois[0].name == "Cafe 2"

    def test_to_llm_summary(self):
        """to_llm_summary should return proper structure."""
        district = District(
            district_id="A",
            name="Historic Center",
            center_lat=48.8566,
            center_lon=2.3522,
        )
        district.add_poi(create_test_poi("Museum 1", 48.8570, 2.3530, "museum", 4.8))
        district.add_poi(create_test_poi("Museum 2", 48.8571, 2.3531, "museum", 4.6))
        district.add_poi(create_test_poi("Cafe", 48.8572, 2.3532, "cafe", 4.5))

        summary = district.to_llm_summary()

        assert summary["district_id"] == "A"
        assert summary["name"] == "Historic Center"
        assert summary["total_pois"] == 3
        assert "museum" in summary["top_categories"]


class TestGeoClusterer:
    """Tests for GeoClusterer."""

    def test_cluster_empty_list(self):
        """Empty POI list should return empty result."""
        clusterer = GeoClusterer()
        result = clusterer.cluster_pois([])

        assert len(result.districts) == 0

    def test_cluster_single_poi(self):
        """Single POI should create one district."""
        clusterer = GeoClusterer(min_pois_per_district=1)
        pois = [create_test_poi("Test POI", 48.8566, 2.3522)]

        result = clusterer.cluster_pois(pois)

        assert len(result.districts) == 1
        district = list(result.districts.values())[0]
        assert district.total_pois == 1

    def test_cluster_nearby_pois_same_district(self):
        """Nearby POIs (< cell_size) should be in same district."""
        clusterer = GeoClusterer(cell_size_km=2.0, min_pois_per_district=1)

        # All POIs within ~500m of each other
        pois = [
            create_test_poi("POI 1", 48.8566, 2.3522),
            create_test_poi("POI 2", 48.8570, 2.3530),
            create_test_poi("POI 3", 48.8560, 2.3510),
        ]

        result = clusterer.cluster_pois(pois)

        # Should all be in same district
        assert len(result.districts) == 1
        district = list(result.districts.values())[0]
        assert district.total_pois == 3

    def test_cluster_distant_pois_different_districts(self):
        """Distant POIs should be in different districts."""
        clusterer = GeoClusterer(cell_size_km=1.0, min_pois_per_district=1)

        # POIs ~5km apart
        pois = [
            create_test_poi("North POI", 48.88, 2.35),  # ~2.7km north
            create_test_poi("South POI", 48.83, 2.35),  # ~2.7km south
            create_test_poi("East POI", 48.855, 2.40),  # ~3.5km east
        ]

        result = clusterer.cluster_pois(pois)

        # Should be in different districts
        assert len(result.districts) >= 2

    def test_hotel_district_identification(self):
        """Hotel should be assigned to nearest district."""
        clusterer = GeoClusterer(cell_size_km=2.0, min_pois_per_district=1)

        pois = [
            create_test_poi("POI 1", 48.8566, 2.3522),
            create_test_poi("POI 2", 48.8570, 2.3530),
        ]

        # Hotel right next to POIs
        result = clusterer.cluster_pois(
            pois,
            hotel_lat=48.8568,
            hotel_lon=2.3525,
        )

        assert result.hotel_district_id is not None

    def test_max_districts_limit(self):
        """Should not exceed max_districts."""
        clusterer = GeoClusterer(
            cell_size_km=0.5,  # Small cells = many clusters
            min_pois_per_district=1,
            max_districts=3,
        )

        # Many distant POIs
        pois = [
            create_test_poi(f"POI {i}", 48.8 + i * 0.05, 2.3 + i * 0.05)
            for i in range(10)
        ]

        result = clusterer.cluster_pois(pois)

        assert len(result.districts) <= 3


class TestClusteringResult:
    """Tests for ClusteringResult."""

    def test_get_district(self):
        """get_district should return correct district."""
        district_a = District("A", "Test A", 48.8566, 2.3522)
        district_b = District("B", "Test B", 48.8600, 2.3600)

        result = ClusteringResult(
            districts={"A": district_a, "B": district_b}
        )

        assert result.get_district("A") == district_a
        assert result.get_district("C") is None

    def test_get_nearest_district(self):
        """get_nearest_district should return closest district."""
        district_a = District("A", "North", 48.87, 2.35)
        district_b = District("B", "South", 48.84, 2.35)

        result = ClusteringResult(
            districts={"A": district_a, "B": district_b}
        )

        # Point closer to South district
        nearest = result.get_nearest_district(48.845, 2.35)
        assert nearest.district_id == "B"

    def test_get_nearest_district_with_category_filter(self):
        """get_nearest_district should filter by category."""
        district_a = District("A", "Museum District", 48.87, 2.35)
        district_a.add_poi(create_test_poi("Museum", 48.87, 2.35, "museum"))

        district_b = District("B", "Restaurant District", 48.84, 2.35)
        district_b.add_poi(create_test_poi("Restaurant", 48.84, 2.35, "restaurant"))

        result = ClusteringResult(
            districts={"A": district_a, "B": district_b}
        )

        # Even though B is closer, A has museums
        nearest = result.get_nearest_district(48.845, 2.35, categories=["museum"])
        assert nearest.district_id == "A"

    def test_get_districts_sorted_by_distance(self):
        """get_districts_sorted_by_distance should return sorted list."""
        district_a = District("A", "Far", 48.90, 2.35)
        district_b = District("B", "Close", 48.856, 2.352)
        district_c = District("C", "Medium", 48.87, 2.35)

        result = ClusteringResult(
            districts={"A": district_a, "B": district_b, "C": district_c}
        )

        sorted_districts = result.get_districts_sorted_by_distance(48.855, 2.351)

        # B should be first (closest), then C, then A
        assert sorted_districts[0][0].district_id == "B"
        assert sorted_districts[1][0].district_id == "C"
        assert sorted_districts[2][0].district_id == "A"
