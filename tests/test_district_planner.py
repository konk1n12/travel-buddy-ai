"""
Tests for district planner service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, time
from uuid import uuid4

from src.application.district_planner import (
    DistrictPlanner,
    DistrictPlannerLLM,
    DistrictAssignment,
    DayDistrictPlan,
)
from src.application.geo_clustering import District, ClusteringResult
from src.domain.models import DaySkeleton, SkeletonBlock, BlockType, POICandidate


def create_test_district(
    district_id: str,
    name: str,
    lat: float,
    lon: float,
    categories: list[str] = None,
) -> District:
    """Create a test district with POIs."""
    district = District(
        district_id=district_id,
        name=name,
        center_lat=lat,
        center_lon=lon,
    )

    # Add some POIs with categories
    for i, cat in enumerate(categories or ["restaurant", "museum"]):
        poi = POICandidate(
            poi_id=uuid4(),
            name=f"{cat.title()} {i + 1}",
            category=cat,
            tags=[cat],
            rating=4.5 + (i * 0.1),
            location=f"{lat}, {lon}",
            lat=lat + (i * 0.001),
            lon=lon + (i * 0.001),
            rank_score=45 + i,
        )
        district.add_poi(poi)

    return district


def create_test_skeleton() -> DaySkeleton:
    """Create a test day skeleton with blocks."""
    return DaySkeleton(
        day_number=1,
        date=date(2024, 6, 15),
        theme="City Exploration",
        blocks=[
            SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=time(8, 30),
                end_time=time(9, 30),
                theme="Breakfast",
                desired_categories=["cafe", "breakfast"],
            ),
            SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=time(10, 0),
                end_time=time(12, 30),
                theme="Morning exploration",
                desired_categories=["museum", "attraction"],
            ),
            SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=time(13, 0),
                end_time=time(14, 0),
                theme="Lunch",
                desired_categories=["restaurant", "local cuisine"],
            ),
            SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=time(14, 30),
                end_time=time(17, 0),
                theme="Afternoon",
                desired_categories=["park", "viewpoint"],
            ),
            SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=time(19, 0),
                end_time=time(20, 30),
                theme="Dinner",
                desired_categories=["restaurant", "fine dining"],
            ),
        ],
    )


class TestDistrictAssignment:
    """Tests for DistrictAssignment dataclass."""

    def test_create_assignment(self):
        """Should create assignment with all fields."""
        assignment = DistrictAssignment(
            block_index=0,
            district_id="A",
            reason="Near hotel",
        )

        assert assignment.block_index == 0
        assert assignment.district_id == "A"
        assert assignment.reason == "Near hotel"


class TestDayDistrictPlan:
    """Tests for DayDistrictPlan dataclass."""

    def test_get_district_for_block(self):
        """Should return correct district for block index."""
        plan = DayDistrictPlan(
            day_number=1,
            assignments=[
                DistrictAssignment(0, "A"),
                DistrictAssignment(1, "A"),
                DistrictAssignment(2, "B"),
            ],
        )

        assert plan.get_district_for_block(0) == "A"
        assert plan.get_district_for_block(1) == "A"
        assert plan.get_district_for_block(2) == "B"
        assert plan.get_district_for_block(99) is None


class TestDistrictPlannerDeterministic:
    """Tests for deterministic district planning."""

    def test_starts_with_hotel_district(self):
        """First block should be in hotel district."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Hotel Area", 48.856, 2.352, ["cafe", "restaurant"]),
                "B": create_test_district("B", "Museum Area", 48.870, 2.360, ["museum", "attraction"]),
            },
            hotel_district_id="A",
        )

        plan = planner._plan_deterministic(skeleton, clustering)

        # First block (breakfast) should be in hotel district A
        assert plan.get_district_for_block(0) == "A"

    def test_stays_in_district_when_category_available(self):
        """Should stay in current district if categories are available."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        # District A has all needed categories
        clustering = ClusteringResult(
            districts={
                "A": create_test_district(
                    "A", "Full Service", 48.856, 2.352,
                    ["cafe", "restaurant", "museum", "attraction", "park"]
                ),
            },
            hotel_district_id="A",
        )

        plan = planner._plan_deterministic(skeleton, clustering)

        # All blocks should be in A since it has everything
        for assignment in plan.assignments:
            assert assignment.district_id == "A"

    def test_moves_to_district_with_required_category(self):
        """Should move to different district when category not available."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        # A only has meals, B only has activities
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Food District", 48.856, 2.352, ["cafe", "restaurant"]),
                "B": create_test_district("B", "Activity District", 48.870, 2.360, ["museum", "park", "attraction"]),
            },
            hotel_district_id="A",
        )

        plan = planner._plan_deterministic(skeleton, clustering)

        # Breakfast (block 0) - A (cafe)
        assert plan.get_district_for_block(0) == "A"
        # Morning activity (block 1) - B (museum)
        assert plan.get_district_for_block(1) == "B"

    def test_returns_to_hotel_for_dinner(self):
        """Last meal block should try to return to hotel district."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Hotel Area", 48.856, 2.352, ["cafe", "restaurant"]),
                "B": create_test_district("B", "Park Area", 48.870, 2.360, ["park", "viewpoint"]),
            },
            hotel_district_id="A",
        )

        plan = planner._plan_deterministic(skeleton, clustering)

        # Dinner (last block) should be in A (hotel district with restaurants)
        assert plan.get_district_for_block(4) == "A"


class TestDistrictPlannerLLM:
    """Tests for LLM-based district planning."""

    @pytest.mark.asyncio
    async def test_llm_response_parsing(self):
        """Should correctly parse valid LLM response."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Center", 48.856, 2.352),
                "B": create_test_district("B", "North", 48.870, 2.360),
            },
            hotel_district_id="A",
        )

        # Valid LLM response
        llm_response = {
            "assignments": [
                {"block_index": 0, "district_id": "A", "reason": "Near hotel"},
                {"block_index": 1, "district_id": "A", "reason": "Stay in center"},
                {"block_index": 2, "district_id": "A", "reason": "Lunch in center"},
                {"block_index": 3, "district_id": "B", "reason": "Park visit"},
                {"block_index": 4, "district_id": "A", "reason": "Return for dinner"},
            ]
        }

        assignments = planner._parse_llm_response(llm_response, skeleton, clustering)

        assert len(assignments) == 5
        assert assignments[0].district_id == "A"
        assert assignments[3].district_id == "B"

    @pytest.mark.asyncio
    async def test_llm_response_invalid_district(self):
        """Should ignore assignments with invalid district IDs."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Center", 48.856, 2.352),
            },
            hotel_district_id="A",
        )

        # Response with invalid district "Z"
        llm_response = {
            "assignments": [
                {"block_index": 0, "district_id": "A"},
                {"block_index": 1, "district_id": "Z"},  # Invalid
                {"block_index": 2, "district_id": "A"},
            ]
        }

        assignments = planner._parse_llm_response(llm_response, skeleton, clustering)

        # Should return empty (incomplete assignments)
        assert len(assignments) == 0

    @pytest.mark.asyncio
    async def test_llm_fallback_on_incomplete(self):
        """Should fallback when LLM doesn't assign all blocks."""
        planner = DistrictPlannerLLM()

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Center", 48.856, 2.352, ["cafe", "restaurant", "museum"]),
            },
            hotel_district_id="A",
        )

        # Only 3 of 5 blocks assigned
        llm_response = {
            "assignments": [
                {"block_index": 0, "district_id": "A"},
                {"block_index": 1, "district_id": "A"},
                {"block_index": 2, "district_id": "A"},
            ]
        }

        assignments = planner._parse_llm_response(llm_response, skeleton, clustering)

        # Should return empty (triggers fallback)
        assert len(assignments) == 0


class TestDistrictPlanner:
    """Tests for unified DistrictPlanner."""

    @pytest.mark.asyncio
    async def test_deterministic_mode(self):
        """Should use deterministic planning when LLM disabled."""
        planner = DistrictPlanner(use_llm=False)

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(
            districts={
                "A": create_test_district("A", "Center", 48.856, 2.352, ["cafe", "restaurant", "museum"]),
            },
            hotel_district_id="A",
        )

        plan = await planner.plan_districts(skeleton, clustering, "Paris")

        assert plan.day_number == 1
        assert len(plan.assignments) == 5

    @pytest.mark.asyncio
    async def test_empty_districts_returns_empty_plan(self):
        """Should return empty plan when no districts."""
        planner = DistrictPlanner(use_llm=False)

        skeleton = create_test_skeleton()
        clustering = ClusteringResult(districts={})

        plan = await planner.plan_districts(skeleton, clustering, "Paris")

        assert len(plan.assignments) == 0
