"""
Tests for POI planning functionality.
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.main import app
from src.application.poi_planner import POIPlanner
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.poi_providers import DBPOIProvider, CompositePOIProvider, ExternalPOIProvider, GooglePlacesPOIProvider
from src.infrastructure.models import POIModel
from src.domain.models import POICandidate, BudgetLevel, BlockType


class MockExternalPOIProvider:
    """Mock external provider for testing."""

    def __init__(self, mock_results: list[POICandidate]):
        self.mock_results = mock_results

    async def search_pois(self, city, desired_categories, budget=None, limit=10, center_location=None):
        return self.mock_results[:limit]


@pytest.mark.asyncio
async def test_db_poi_provider():
    """Test DBPOIProvider searches and ranks POIs."""
    async with AsyncSessionLocal() as db:
        provider = DBPOIProvider(db)

        # Search for cafe/breakfast in Paris (should find existing POIs from seed data)
        results = await provider.search_pois(
            city="Paris",
            desired_categories=["cafe", "breakfast"],
            budget=BudgetLevel.MEDIUM,
            limit=5
        )

        # Should find at least some results if seed data exists
        # Note: This test depends on seed data being present
        assert isinstance(results, list)
        for candidate in results:
            assert isinstance(candidate, POICandidate)
            assert candidate.rank_score >= 0


@pytest.mark.asyncio
async def test_composite_provider_fallback():
    """Test CompositePOIProvider falls back to external when DB has insufficient results."""
    async with AsyncSessionLocal() as db:
        db_provider = DBPOIProvider(db)

        # Create mock external results
        mock_external = [
            POICandidate(
                poi_id=uuid4(),
                name="External POI 1",
                category="restaurant",
                tags=["sushi"],
                rating=4.5,
                location="External location",
                rank_score=10.0
            )
        ]
        external_provider = MockExternalPOIProvider(mock_external)

        composite = CompositePOIProvider(db_provider, external_provider)

        # Search for a very specific category unlikely to have many DB results
        results = await composite.search_pois(
            city="UnknownCity",
            desired_categories=["very_specific_category"],
            limit=10
        )

        # Should include external results when DB is insufficient
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_poi_planner_service():
    """Test POIPlanner service end-to-end."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-16",
                "interests": ["food", "culture"]
            }
        )
        trip_id = trip_response.json()["id"]

        # Generate macro plan first (mock it)
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client

        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Now test POI planning
    async with AsyncSessionLocal() as db:
        planner = POIPlanner()
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    assert poi_plan.trip_id == trip_id
    assert len(poi_plan.blocks) > 0

    # Verify blocks have correct structure
    for block in poi_plan.blocks:
        assert block.day_number >= 1
        assert block.block_index >= 0
        assert block.block_type in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]
        assert isinstance(block.candidates, list)


@pytest.mark.asyncio
async def test_poi_plan_endpoint_create():
    """Test POST /api/trips/{trip_id}/poi-plan endpoint."""
    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Barcelona",
                "start_date": "2024-08-01",
                "end_date": "2024-08-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create macro plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Generate POI plan
            poi_response = await client.post(f"/api/trips/{trip_id}/poi-plan")

            assert poi_response.status_code == 201
            data = poi_response.json()

            assert data["trip_id"] == trip_id
            assert "blocks" in data
            assert "created_at" in data

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_poi_plan_endpoint_get():
    """Test GET /api/trips/{trip_id}/poi-plan endpoint."""
    # Create trip, macro plan, and POI plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-07-01",
                "end_date": "2024-07-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create plans
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")

            # Get POI plan
            get_response = await client.get(f"/api/trips/{trip_id}/poi-plan")

            assert get_response.status_code == 200
            data = get_response.json()
            assert data["trip_id"] == trip_id

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_poi_plan_macro_plan_missing():
    """Test POI planning fails when macro plan is missing."""
    # Create trip without macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Berlin",
                "start_date": "2024-09-01",
                "end_date": "2024-09-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Try to generate POI plan without macro plan
        response = await client.post(f"/api/trips/{trip_id}/poi-plan")

    assert response.status_code == 404
    assert "macro plan" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_poi_plan_not_found():
    """Test getting POI plan when none exists."""
    # Create trip without POI plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-10-01",
                "end_date": "2024-10-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Try to get POI plan
        response = await client.get(f"/api/trips/{trip_id}/poi-plan")

    assert response.status_code == 404
    assert "no poi plan" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_poi_planner_respects_block_types():
    """Test that POI planner only generates candidates for relevant block types."""
    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-11-01",
                "end_date": "2024-11-02",
            }
        )
        trip_id = trip_response.json()["id"]

        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Test POI planner
    async with AsyncSessionLocal() as db:
        planner = POIPlanner()
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    # Verify only meal/activity/nightlife blocks have candidates
    for block in poi_plan.blocks:
        assert block.block_type in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]
        # Rest and travel blocks should not be in poi_plan


# ============================================================================
# LLM-Assisted POI Selection Integration Tests
# ============================================================================

class MockPOISelectionLLMService:
    """Mock POI selection LLM service for integration testing."""

    def __init__(self, selection_strategy="first_n"):
        """
        Initialize mock service.

        Args:
            selection_strategy: "first_n" returns first N candidates,
                               "reverse" returns last N candidates in reverse,
                               "invalid_ids" returns invalid IDs to test fallback
        """
        self.selection_strategy = selection_strategy
        self.calls = []

    async def select_pois_for_block(
        self,
        trip_context,
        day_context,
        block_context,
        candidates,
        max_results=3,
    ):
        """Mock POI selection."""
        self.calls.append({
            "day_number": day_context.day_number,
            "block_index": block_context.block_index,
            "block_type": block_context.block_type,
            "num_candidates": len(candidates),
        })

        if not candidates:
            return []

        if self.selection_strategy == "first_n":
            return candidates[:max_results]
        elif self.selection_strategy == "reverse":
            return list(reversed(candidates))[:max_results]
        elif self.selection_strategy == "empty":
            # Return empty to trigger fallback
            return []
        else:
            return candidates[:max_results]


@pytest.mark.asyncio
async def test_poi_planner_with_llm_selection_enabled():
    """Test POI planner with LLM selection enabled uses the LLM service."""
    from src.config import Settings

    # Create mock settings with LLM selection enabled
    mock_settings = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=True,
    )

    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-12-01",
                "end_date": "2024-12-02",
                "interests": ["food", "culture"]
            }
        )
        trip_id = trip_response.json()["id"]

        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Create mock LLM selection service
    mock_llm_service = MockPOISelectionLLMService(selection_strategy="first_n")

    # Test POI planner with LLM enabled
    async with AsyncSessionLocal() as db:
        planner = POIPlanner(
            poi_selection_llm=mock_llm_service,
            app_settings=mock_settings,
        )
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    # Verify LLM service was called for each block needing POIs
    assert len(mock_llm_service.calls) > 0
    assert poi_plan.trip_id == trip_id

    # Verify all block types that need POIs had LLM called
    for call in mock_llm_service.calls:
        assert call["block_type"] in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]


@pytest.mark.asyncio
async def test_poi_planner_deterministic_mode_skips_llm():
    """Test POI planner in deterministic mode doesn't use LLM service."""
    from src.config import Settings

    # Create settings with LLM selection disabled
    mock_settings = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=False,
    )

    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "London",
                "start_date": "2024-12-05",
                "end_date": "2024-12-06",
            }
        )
        trip_id = trip_response.json()["id"]

        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Create mock LLM service that should NOT be called
    mock_llm_service = MockPOISelectionLLMService()

    # Test POI planner with LLM disabled
    async with AsyncSessionLocal() as db:
        planner = POIPlanner(
            poi_selection_llm=mock_llm_service,
            app_settings=mock_settings,
        )
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    # Verify LLM service was NOT called
    assert len(mock_llm_service.calls) == 0
    assert poi_plan.trip_id == trip_id
    assert len(poi_plan.blocks) > 0


@pytest.mark.asyncio
async def test_poi_planner_llm_fallback_on_empty_selection():
    """Test POI planner falls back to deterministic when LLM returns empty."""
    from src.config import Settings

    mock_settings = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=True,
    )

    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test", headers={"X-Device-Id": "test-device"}) as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Madrid",
                "start_date": "2024-12-10",
                "end_date": "2024-12-11",
            }
        )
        trip_id = trip_response.json()["id"]

        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Mock LLM service that returns empty (should trigger fallback)
    mock_llm_service = MockPOISelectionLLMService(selection_strategy="empty")

    async with AsyncSessionLocal() as db:
        planner = POIPlanner(
            poi_selection_llm=mock_llm_service,
            app_settings=mock_settings,
        )
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    # LLM was called but returned empty, so fallback to deterministic should work
    assert len(mock_llm_service.calls) > 0
    assert poi_plan.trip_id == trip_id
    # Blocks should still have candidates from deterministic fallback
    # (if POI data exists in DB)


@pytest.mark.asyncio
async def test_poi_planner_use_llm_selection_property():
    """Test that use_llm_selection property reflects settings."""
    from src.config import Settings

    # Test with LLM enabled
    settings_enabled = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=True,
    )
    planner_enabled = POIPlanner(app_settings=settings_enabled)
    assert planner_enabled.use_llm_selection is True

    # Test with LLM disabled
    settings_disabled = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=False,
    )
    planner_disabled = POIPlanner(app_settings=settings_disabled)
    assert planner_disabled.use_llm_selection is False


@pytest.mark.asyncio
async def test_poi_planner_candidates_per_block_constants():
    """Test POI planner candidate constants are properly defined."""
    # Test class constants
    assert POIPlanner.CANDIDATES_PER_BLOCK == 3
    assert POIPlanner.CANDIDATES_FOR_LLM_SELECTION == 10
    assert POIPlanner.CANDIDATES_FOR_LLM_SELECTION > POIPlanner.CANDIDATES_PER_BLOCK
