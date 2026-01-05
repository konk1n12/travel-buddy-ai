"""
Geographic Clustering service for POI grouping by districts.

Groups POIs into geographic clusters (districts) for route optimization.
Uses grid-based clustering with adaptive cell merging.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from src.domain.models import POICandidate, BlockType

logger = logging.getLogger(__name__)


# Earth radius in km for haversine calculations
EARTH_RADIUS_KM = 6371.0


@dataclass
class District:
    """A geographic district containing clustered POIs."""
    district_id: str
    name: str
    center_lat: float
    center_lon: float
    pois: list[POICandidate] = field(default_factory=list)

    # Category summary for LLM planning
    category_counts: dict[str, int] = field(default_factory=dict)

    # Metadata
    avg_rating: float = 0.0
    total_pois: int = 0

    def add_poi(self, poi: POICandidate):
        """Add a POI to this district and update stats."""
        self.pois.append(poi)
        self.total_pois = len(self.pois)

        # Update category counts
        if poi.category:
            self.category_counts[poi.category] = self.category_counts.get(poi.category, 0) + 1

        # Update average rating
        ratings = [p.rating for p in self.pois if p.rating]
        self.avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

    def has_category(self, categories: list[str]) -> bool:
        """Check if district has POIs matching any of the categories."""
        if not categories:
            return True
        for cat in categories:
            if cat.lower() in [c.lower() for c in self.category_counts.keys()]:
                return True
            # Also check POI tags
            for poi in self.pois:
                if poi.tags and any(cat.lower() in tag.lower() for tag in poi.tags):
                    return True
        return False

    def get_pois_by_category(
        self,
        categories: list[str],
        min_rating: float = 4.5,
        exclude_ids: Optional[set[UUID]] = None,
    ) -> list[POICandidate]:
        """Get POIs matching categories with minimum rating."""
        exclude_ids = exclude_ids or set()
        result = []

        for poi in self.pois:
            # Skip excluded POIs
            if poi.poi_id in exclude_ids:
                continue

            # Check rating
            if poi.rating and poi.rating < min_rating:
                continue

            # Check category match
            category_match = False
            if not categories:
                category_match = True
            elif poi.category and poi.category.lower() in [c.lower() for c in categories]:
                category_match = True
            elif poi.tags:
                for cat in categories:
                    if any(cat.lower() in tag.lower() for tag in poi.tags):
                        category_match = True
                        break

            if category_match:
                result.append(poi)

        # Sort by rating (descending)
        result.sort(key=lambda p: p.rating or 0.0, reverse=True)
        return result

    def to_llm_summary(self) -> dict:
        """Convert to summary dict for LLM prompt."""
        top_categories = sorted(
            self.category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            "district_id": self.district_id,
            "name": self.name,
            "center": {"lat": round(self.center_lat, 4), "lon": round(self.center_lon, 4)},
            "total_pois": self.total_pois,
            "avg_rating": round(self.avg_rating, 2),
            "top_categories": [cat for cat, count in top_categories],
        }


@dataclass
class ClusteringResult:
    """Result of geographic clustering."""
    districts: dict[str, District]  # district_id -> District
    hotel_district_id: Optional[str] = None
    city_center_lat: Optional[float] = None
    city_center_lon: Optional[float] = None

    def get_district(self, district_id: str) -> Optional[District]:
        """Get district by ID."""
        return self.districts.get(district_id)

    def get_nearest_district(
        self,
        lat: float,
        lon: float,
        categories: Optional[list[str]] = None,
    ) -> Optional[District]:
        """Find nearest district to a location, optionally filtering by categories."""
        nearest = None
        nearest_distance = float('inf')

        for district in self.districts.values():
            # Skip if categories required but not present
            if categories and not district.has_category(categories):
                continue

            distance = haversine_distance_km(lat, lon, district.center_lat, district.center_lon)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest = district

        return nearest

    def get_districts_sorted_by_distance(
        self,
        lat: float,
        lon: float,
    ) -> list[tuple[District, float]]:
        """Get all districts sorted by distance from a point."""
        result = []
        for district in self.districts.values():
            distance = haversine_distance_km(lat, lon, district.center_lat, district.center_lon)
            result.append((district, distance))
        result.sort(key=lambda x: x[1])
        return result


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in km."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def _lat_lon_to_grid_cell(lat: float, lon: float, cell_size_km: float) -> tuple[int, int]:
    """Convert lat/lon to grid cell coordinates."""
    # Approximate km per degree at equator (good enough for small areas)
    km_per_lat_degree = 111.0
    km_per_lon_degree = 111.0 * math.cos(math.radians(lat))

    cell_lat = int(lat * km_per_lat_degree / cell_size_km)
    cell_lon = int(lon * km_per_lon_degree / cell_size_km)

    return (cell_lat, cell_lon)


def _grid_cell_to_center(cell: tuple[int, int], cell_size_km: float, ref_lat: float) -> tuple[float, float]:
    """Convert grid cell back to approximate lat/lon center."""
    km_per_lat_degree = 111.0
    km_per_lon_degree = 111.0 * math.cos(math.radians(ref_lat))

    center_lat = (cell[0] + 0.5) * cell_size_km / km_per_lat_degree
    center_lon = (cell[1] + 0.5) * cell_size_km / km_per_lon_degree

    return (center_lat, center_lon)


def _generate_district_name(index: int, categories: dict[str, int]) -> str:
    """Generate a human-readable district name."""
    # Use top category if available
    if categories:
        top_category = max(categories.items(), key=lambda x: x[1])[0]
        return f"District {chr(65 + index)} ({top_category.title()})"
    return f"District {chr(65 + index)}"


class GeoClusterer:
    """
    Geographic clustering service for POIs.

    Uses grid-based clustering with adaptive merging:
    1. Assign POIs to grid cells
    2. Merge small cells into larger districts
    3. Compute district centers and statistics
    """

    def __init__(
        self,
        cell_size_km: float = 1.5,
        min_pois_per_district: int = 5,
        max_districts: int = 8,
    ):
        """
        Initialize clusterer.

        Args:
            cell_size_km: Grid cell size in km (larger = fewer, bigger districts)
            min_pois_per_district: Minimum POIs to form a standalone district
            max_districts: Maximum number of districts (will merge smallest)
        """
        self.cell_size_km = cell_size_km
        self.min_pois_per_district = min_pois_per_district
        self.max_districts = max_districts

    def cluster_pois(
        self,
        pois: list[POICandidate],
        hotel_lat: Optional[float] = None,
        hotel_lon: Optional[float] = None,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
    ) -> ClusteringResult:
        """
        Cluster POIs into geographic districts.

        Args:
            pois: List of POI candidates to cluster
            hotel_lat: Hotel latitude (for hotel district identification)
            hotel_lon: Hotel longitude
            city_center_lat: City center latitude
            city_center_lon: City center longitude

        Returns:
            ClusteringResult with districts and metadata
        """
        if not pois:
            return ClusteringResult(districts={})

        # Filter POIs with valid coordinates
        valid_pois = [p for p in pois if p.lat is not None and p.lon is not None]
        if not valid_pois:
            logger.warning("No POIs with valid coordinates for clustering")
            return ClusteringResult(districts={})

        logger.info(f"Clustering {len(valid_pois)} POIs with cell_size={self.cell_size_km}km")

        # Step 1: Assign POIs to grid cells
        cell_pois: dict[tuple[int, int], list[POICandidate]] = {}
        for poi in valid_pois:
            cell = _lat_lon_to_grid_cell(poi.lat, poi.lon, self.cell_size_km)
            if cell not in cell_pois:
                cell_pois[cell] = []
            cell_pois[cell].append(poi)

        logger.debug(f"Initial grid cells: {len(cell_pois)}")

        # Step 2: Merge small cells into nearest larger ones
        cell_pois = self._merge_small_cells(cell_pois)

        # Step 3: Limit to max_districts by merging smallest
        while len(cell_pois) > self.max_districts:
            cell_pois = self._merge_smallest_cell(cell_pois)

        logger.info(f"Final districts: {len(cell_pois)}")

        # Step 4: Create District objects
        districts: dict[str, District] = {}
        ref_lat = city_center_lat or valid_pois[0].lat

        for idx, (cell, cell_poi_list) in enumerate(sorted(cell_pois.items())):
            # Calculate actual center from POIs
            avg_lat = sum(p.lat for p in cell_poi_list) / len(cell_poi_list)
            avg_lon = sum(p.lon for p in cell_poi_list) / len(cell_poi_list)

            district_id = chr(65 + idx)  # A, B, C, ...

            # Count categories
            category_counts: dict[str, int] = {}
            for poi in cell_poi_list:
                if poi.category:
                    category_counts[poi.category] = category_counts.get(poi.category, 0) + 1

            district = District(
                district_id=district_id,
                name=_generate_district_name(idx, category_counts),
                center_lat=avg_lat,
                center_lon=avg_lon,
                category_counts=category_counts,
            )

            for poi in cell_poi_list:
                district.add_poi(poi)

            districts[district_id] = district

        # Step 5: Find hotel district
        hotel_district_id = None
        if hotel_lat is not None and hotel_lon is not None:
            nearest_distance = float('inf')
            for district in districts.values():
                distance = haversine_distance_km(
                    hotel_lat, hotel_lon,
                    district.center_lat, district.center_lon
                )
                if distance < nearest_distance:
                    nearest_distance = distance
                    hotel_district_id = district.district_id

            if hotel_district_id:
                logger.info(f"Hotel is in District {hotel_district_id} ({nearest_distance:.2f}km)")

        return ClusteringResult(
            districts=districts,
            hotel_district_id=hotel_district_id,
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
        )

    def _merge_small_cells(
        self,
        cell_pois: dict[tuple[int, int], list[POICandidate]],
    ) -> dict[tuple[int, int], list[POICandidate]]:
        """Merge cells with few POIs into nearest larger cells."""
        # Find small cells
        small_cells = [
            cell for cell, pois in cell_pois.items()
            if len(pois) < self.min_pois_per_district
        ]

        if not small_cells:
            return cell_pois

        # For each small cell, find nearest large cell and merge
        large_cells = [
            cell for cell, pois in cell_pois.items()
            if len(pois) >= self.min_pois_per_district
        ]

        if not large_cells:
            # All cells are small - just return as-is
            return cell_pois

        for small_cell in small_cells:
            # Find nearest large cell (by grid distance)
            nearest = min(
                large_cells,
                key=lambda c: abs(c[0] - small_cell[0]) + abs(c[1] - small_cell[1])
            )

            # Merge
            cell_pois[nearest].extend(cell_pois[small_cell])
            del cell_pois[small_cell]

        return cell_pois

    def _merge_smallest_cell(
        self,
        cell_pois: dict[tuple[int, int], list[POICandidate]],
    ) -> dict[tuple[int, int], list[POICandidate]]:
        """Merge the smallest cell into its nearest neighbor."""
        if len(cell_pois) <= 1:
            return cell_pois

        # Find smallest cell
        smallest_cell = min(cell_pois.keys(), key=lambda c: len(cell_pois[c]))

        # Find nearest other cell
        other_cells = [c for c in cell_pois.keys() if c != smallest_cell]
        nearest = min(
            other_cells,
            key=lambda c: abs(c[0] - smallest_cell[0]) + abs(c[1] - smallest_cell[1])
        )

        # Merge
        cell_pois[nearest].extend(cell_pois[smallest_cell])
        del cell_pois[smallest_cell]

        return cell_pois
