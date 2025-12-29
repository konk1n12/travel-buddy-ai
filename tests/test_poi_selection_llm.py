"""
Tests for LLM-based POI selection service.

These tests use mock LLM clients to verify:
1. Valid selection from candidates
2. Unknown IDs are ignored
3. Duplicates are removed
4. Invalid JSON triggers fallback
5. Day-level deduplication works
"""
import pytest
from uuid import uuid4
from typing import Optional

from src.domain.models import POICandidate, BlockType, BudgetLevel, PaceLevel
from src.application.poi_selection_llm import (
    POISelectionLLMService,
    TripContext,
    DayContext,
    BlockContext,
    build_trip_context_from_response,
)
from src.infrastructure.llm_client import LLMClient
from src.config import Settings


# ============================================================================
# Mock LLM Client
# ============================================================================

class MockLLMClient(LLMClient):
    """
    Mock LLM client for testing POI selection.
    Returns predetermined responses for testing different scenarios.
    """

    def __init__(self, structured_response: Optional[dict] = None, raise_error: bool = False):
        """
        Initialize mock client.

        Args:
            structured_response: Dict to return from generate_structured
            raise_error: If True, raise ValueError to simulate JSON parsing failure
        """
        self._structured_response = structured_response or {"selected_places": []}
        self._raise_error = raise_error
        self.calls = []  # Track calls for verification

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Not used in POI selection."""
        return ""

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> dict:
        """Return mock structured response."""
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
        })

        if self._raise_error:
            raise ValueError("Simulated JSON parsing failure")

        return self._structured_response


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_candidates():
    """Create sample POI candidates for testing."""
    return [
        POICandidate(
            poi_id=uuid4(),
            name="Le Comptoir du Relais",
            category="restaurant",
            tags=["french", "bistro"],
            location="Paris, France",
            rating=4.5,
            rank_score=0.9,
        ),
        POICandidate(
            poi_id=uuid4(),
            name="Café de Flore",
            category="cafe",
            tags=["cafe", "historic"],
            location="Paris, France",
            rating=4.3,
            rank_score=0.85,
        ),
        POICandidate(
            poi_id=uuid4(),
            name="Bouillon Chartier",
            category="restaurant",
            tags=["french", "traditional"],
            location="Paris, France",
            rating=4.2,
            rank_score=0.8,
        ),
        POICandidate(
            poi_id=uuid4(),
            name="Pink Mamma",
            category="restaurant",
            tags=["italian", "trendy"],
            location="Paris, France",
            rating=4.4,
            rank_score=0.75,
        ),
        POICandidate(
            poi_id=uuid4(),
            name="Le Petit Cler",
            category="restaurant",
            tags=["french", "local"],
            location="Paris, France",
            rating=4.6,
            rank_score=0.7,
        ),
    ]


@pytest.fixture
def trip_context():
    """Create sample trip context."""
    return TripContext(
        city="Paris",
        pace=PaceLevel.MEDIUM,
        budget=BudgetLevel.MEDIUM,
        interests=["food", "culture", "history"],
        additional_notes=None,
    )


@pytest.fixture
def day_context():
    """Create sample day context."""
    return DayContext(
        day_number=1,
        date="2024-03-15",
        theme="French Cuisine & History",
        already_selected_poi_ids=[],
    )


@pytest.fixture
def block_context():
    """Create sample block context."""
    return BlockContext(
        block_index=0,
        block_type=BlockType.MEAL,
        start_time="12:00",
        end_time="14:00",
        theme="Lunch",
        desired_categories=["restaurant", "cafe"],
    )


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Settings(
        database_url="sqlite:///test.db",
        ionet_api_key="test_key",
        use_llm_for_poi_selection=True,
        poi_selection_max_candidates=15,
    )
    return settings


# ============================================================================
# Test Cases for POISelectionLLMService
# ============================================================================

class TestPOISelectionLLMService:
    """Tests for POISelectionLLMService."""

    # Case 1: LLM selects valid subset of candidates
    @pytest.mark.asyncio
    async def test_llm_selects_valid_subset(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that LLM can select a valid subset of candidates."""
        # Prepare mock response with valid candidate IDs
        candidate_ids = [str(c.poi_id) for c in sample_candidates]
        mock_response = {
            "selected_places": [
                {"candidate_id": candidate_ids[0], "reason": "Great French bistro"},
                {"candidate_id": candidate_ids[2], "reason": "Historic atmosphere"},
            ]
        }

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should return exactly the 2 selected candidates
        assert len(result) == 2
        assert result[0].poi_id == sample_candidates[0].poi_id
        assert result[1].poi_id == sample_candidates[2].poi_id

        # Verify LLM was called
        assert len(mock_client.calls) == 1

    # Case 2: LLM returns unknown IDs - should be ignored
    @pytest.mark.asyncio
    async def test_unknown_ids_are_ignored(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that unknown candidate IDs from LLM are ignored."""
        # Prepare mock response with some valid and some invalid IDs
        valid_id = str(sample_candidates[0].poi_id)
        fake_id = str(uuid4())  # This ID doesn't exist in candidates

        mock_response = {
            "selected_places": [
                {"candidate_id": fake_id, "reason": "Invented place"},
                {"candidate_id": valid_id, "reason": "Real restaurant"},
                {"candidate_id": "not-a-uuid", "reason": "Invalid format"},
            ]
        }

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should only return the 1 valid candidate
        assert len(result) == 1
        assert result[0].poi_id == sample_candidates[0].poi_id

    # Case 3: LLM returns duplicates - should be deduplicated
    @pytest.mark.asyncio
    async def test_duplicates_are_removed(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that duplicate candidate IDs are deduplicated."""
        candidate_id = str(sample_candidates[0].poi_id)

        mock_response = {
            "selected_places": [
                {"candidate_id": candidate_id, "reason": "First selection"},
                {"candidate_id": candidate_id, "reason": "Duplicate selection"},
                {"candidate_id": candidate_id, "reason": "Another duplicate"},
            ]
        }

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should only return 1 candidate (duplicates removed)
        assert len(result) == 1
        assert result[0].poi_id == sample_candidates[0].poi_id

    # Case 4: LLM returns invalid JSON - should fallback to deterministic
    @pytest.mark.asyncio
    async def test_invalid_json_triggers_fallback(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that JSON parsing failure triggers deterministic fallback."""
        mock_client = MockLLMClient(raise_error=True)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should fallback to first 3 candidates (deterministic order)
        assert len(result) == 3
        assert result[0].poi_id == sample_candidates[0].poi_id
        assert result[1].poi_id == sample_candidates[1].poi_id
        assert result[2].poi_id == sample_candidates[2].poi_id

    # Case 5: Already selected POIs are excluded
    @pytest.mark.asyncio
    async def test_already_selected_pois_excluded(
        self,
        sample_candidates,
        trip_context,
        block_context,
        mock_settings,
    ):
        """Test that POIs already selected for the day are excluded."""
        # Mark first candidate as already selected
        already_selected = [sample_candidates[0].poi_id]

        day_context = DayContext(
            day_number=1,
            date="2024-03-15",
            theme="French Cuisine",
            already_selected_poi_ids=already_selected,
        )

        # LLM tries to select the already-used POI
        mock_response = {
            "selected_places": [
                {"candidate_id": str(sample_candidates[0].poi_id), "reason": "Already used"},
                {"candidate_id": str(sample_candidates[1].poi_id), "reason": "Good cafe"},
            ]
        }

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should only return the second candidate (first was already selected)
        assert len(result) == 1
        assert result[0].poi_id == sample_candidates[1].poi_id

    # Case 6: Empty selection triggers fallback
    @pytest.mark.asyncio
    async def test_empty_selection_triggers_fallback(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that empty LLM selection triggers deterministic fallback."""
        mock_response = {"selected_places": []}

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should fallback to first 3 candidates
        assert len(result) == 3
        assert result[0].poi_id == sample_candidates[0].poi_id

    # Case 7: Empty candidates returns empty
    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(
        self,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that empty candidate list returns empty result."""
        mock_client = MockLLMClient()
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=[],
            max_results=3,
        )

        assert result == []
        # LLM should not be called for empty candidates
        assert len(mock_client.calls) == 0

    # Case 8: Max results limit is respected
    @pytest.mark.asyncio
    async def test_max_results_limit_respected(
        self,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
        mock_settings,
    ):
        """Test that max_results limit is respected."""
        # LLM returns all 5 candidates
        candidate_ids = [str(c.poi_id) for c in sample_candidates]
        mock_response = {
            "selected_places": [
                {"candidate_id": cid, "reason": "Selected"} for cid in candidate_ids
            ]
        }

        mock_client = MockLLMClient(structured_response=mock_response)
        service = POISelectionLLMService(
            llm_client=mock_client,
            app_settings=mock_settings,
        )

        result = await service.select_pois_for_block(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=2,  # Limit to 2
        )

        # Should only return 2 candidates
        assert len(result) == 2


class TestParseAndValidateResponse:
    """Tests for the _parse_and_validate_response method."""

    @pytest.fixture
    def service(self, mock_settings):
        """Create service instance."""
        return POISelectionLLMService(
            llm_client=MockLLMClient(),
            app_settings=mock_settings,
        )

    def test_malformed_response_structure(self, service, sample_candidates):
        """Test handling of malformed response structure."""
        # Missing selected_places key
        result = service._parse_and_validate_response(
            llm_response={"places": []},
            candidates=sample_candidates,
            already_selected_ids=set(),
            max_results=3,
        )
        assert result == []

    def test_non_list_selected_places(self, service, sample_candidates):
        """Test handling of non-list selected_places."""
        result = service._parse_and_validate_response(
            llm_response={"selected_places": "not a list"},
            candidates=sample_candidates,
            already_selected_ids=set(),
            max_results=3,
        )
        assert result == []

    def test_non_dict_items_in_list(self, service, sample_candidates):
        """Test handling of non-dict items in selected_places."""
        result = service._parse_and_validate_response(
            llm_response={"selected_places": ["string item", 123, None]},
            candidates=sample_candidates,
            already_selected_ids=set(),
            max_results=3,
        )
        assert result == []

    def test_missing_candidate_id(self, service, sample_candidates):
        """Test handling of items without candidate_id."""
        result = service._parse_and_validate_response(
            llm_response={
                "selected_places": [
                    {"name": "Some place", "reason": "Good"},
                ]
            },
            candidates=sample_candidates,
            already_selected_ids=set(),
            max_results=3,
        )
        assert result == []


class TestBuildTripContextFromResponse:
    """Tests for build_trip_context_from_response helper."""

    def test_basic_context_building(self):
        """Test building context from basic trip response."""
        from src.domain.schemas import TripResponse

        trip = TripResponse(
            id=uuid4(),
            city="Paris",
            start_date="2024-03-15",
            end_date="2024-03-18",
            traveler_count=2,
            pace=PaceLevel.MEDIUM,
            budget=BudgetLevel.MEDIUM,
            interests=["food", "history"],
        )

        context = build_trip_context_from_response(trip)

        assert context.city == "Paris"
        assert context.pace == PaceLevel.MEDIUM
        assert context.budget == BudgetLevel.MEDIUM
        assert context.interests == ["food", "history"]
        assert context.additional_notes is None

    def test_context_with_additional_preferences(self):
        """Test building context with additional preferences."""
        from src.domain.schemas import TripResponse

        trip = TripResponse(
            id=uuid4(),
            city="Tokyo",
            start_date="2024-04-01",
            end_date="2024-04-05",
            traveler_count=1,
            pace=PaceLevel.SLOW,
            budget=BudgetLevel.HIGH,
            interests=["anime", "food"],
            additional_preferences={
                "note": "First time in Japan",
                "avoid": ["crowded places", "spicy food"],
                "dietary": ["vegetarian"],
            },
        )

        context = build_trip_context_from_response(trip)

        assert context.city == "Tokyo"
        assert context.additional_notes is not None
        assert "First time in Japan" in context.additional_notes
        assert "crowded places" in context.additional_notes
        assert "vegetarian" in context.additional_notes


class TestPromptBuilding:
    """Tests for prompt building."""

    @pytest.fixture
    def service(self, mock_settings):
        """Create service instance."""
        return POISelectionLLMService(
            llm_client=MockLLMClient(),
            app_settings=mock_settings,
        )

    def test_prompt_contains_candidate_info(
        self,
        service,
        sample_candidates,
        trip_context,
        day_context,
        block_context,
    ):
        """Test that prompt contains candidate information."""
        prompt = service._build_user_prompt(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should contain candidate names
        assert "Le Comptoir du Relais" in prompt
        assert "Café de Flore" in prompt

        # Should contain trip info
        assert "Paris" in prompt
        assert "medium" in prompt.lower()

        # Should contain block info
        assert "MEAL" in prompt
        assert "12:00" in prompt

    def test_prompt_contains_already_selected(
        self,
        service,
        sample_candidates,
        trip_context,
        block_context,
    ):
        """Test that prompt includes already selected POI IDs."""
        already_selected_id = sample_candidates[0].poi_id

        day_context = DayContext(
            day_number=1,
            date="2024-03-15",
            theme="Test Day",
            already_selected_poi_ids=[already_selected_id],
        )

        prompt = service._build_user_prompt(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=sample_candidates,
            max_results=3,
        )

        # Should contain the already selected ID
        assert str(already_selected_id) in prompt


class TestSystemPrompt:
    """Tests for the system prompt."""

    def test_system_prompt_contains_safety_rules(self, mock_settings):
        """Test that system prompt contains critical safety rules."""
        service = POISelectionLLMService(
            llm_client=MockLLMClient(),
            app_settings=mock_settings,
        )

        prompt = service.SYSTEM_PROMPT

        # Must contain rules about not inventing places
        assert "ONLY" in prompt
        assert "candidates" in prompt.lower()
        assert "NOT" in prompt
        assert "invent" in prompt.lower() or "imagine" in prompt.lower()
