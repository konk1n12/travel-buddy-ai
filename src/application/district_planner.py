"""
LLM-based District Planner for route optimization.

Assigns geographic districts to time blocks to minimize travel
while maintaining route quality and logical flow.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.config import settings, Settings
from src.domain.models import DaySkeleton, SkeletonBlock, BlockType
from src.application.geo_clustering import ClusteringResult, District, haversine_distance_km
from src.infrastructure.llm_client import LLMClient, get_macro_planning_llm_client

logger = logging.getLogger(__name__)


@dataclass
class DistrictAssignment:
    """Assignment of a district to a skeleton block."""
    block_index: int
    district_id: str
    reason: Optional[str] = None


@dataclass
class DayDistrictPlan:
    """District plan for a single day."""
    day_number: int
    assignments: list[DistrictAssignment]

    def get_district_for_block(self, block_index: int) -> Optional[str]:
        """Get assigned district ID for a block."""
        for assignment in self.assignments:
            if assignment.block_index == block_index:
                return assignment.district_id
        return None


class DistrictPlannerLLM:
    """
    LLM-based district planner.

    Uses LLM to assign districts to time blocks for optimal routing:
    - Minimizes district changes (stay in one area)
    - Considers hotel location for start/end of day
    - Ensures required categories are available in assigned district
    """

    SYSTEM_PROMPT = """You are a travel route optimizer. Your task is to assign city districts to time blocks for a walking tour.

GOALS (in priority order):
1. MINIMIZE DISTRICT CHANGES - Consecutive blocks should be in the same district when possible
2. START/END NEAR HOTEL - First and last blocks should be near the hotel district
3. CATEGORY AVAILABILITY - Each block must be in a district with matching POI categories
4. LOGICAL FLOW - Route should feel natural (no backtracking)

RULES:
- You MUST assign EVERY block to a district
- You can ONLY use districts from the provided list
- Prefer staying in one district for 2-3 consecutive blocks
- Maximum 2-3 district changes per day

Output ONLY valid JSON matching the schema. No explanations."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        app_settings: Optional[Settings] = None,
    ):
        """Initialize district planner."""
        self._llm_client = llm_client
        self._settings = app_settings or settings

    @property
    def llm_client(self) -> LLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            self._llm_client = get_macro_planning_llm_client()
        return self._llm_client

    def _build_user_prompt(
        self,
        day_skeleton: DaySkeleton,
        clustering_result: ClusteringResult,
        city: str,
        district_summaries: Optional[list[dict]] = None,
        preference_summary: Optional[dict] = None,
        previous_day_anchor: Optional[dict] = None,
        previous_day_district_id: Optional[str] = None,
    ) -> str:
        """Build user prompt for district assignment."""
        # Build districts summary
        if district_summaries is not None:
            districts_info = district_summaries
        else:
            districts_info = []
            for district in clustering_result.districts.values():
                summary = district.to_llm_summary()
                districts_info.append(summary)

        # Build blocks info
        blocks_info = []
        for idx, block in enumerate(day_skeleton.blocks):
            block_info = {
                "block_index": idx,
                "type": block.block_type.value,
                "time": f"{block.start_time} - {block.end_time}",
                "theme": block.theme or "",
                "required_categories": block.desired_categories or [],
            }
            blocks_info.append(block_info)

        # Hotel district info
        hotel_info = "Unknown"
        if clustering_result.hotel_district_id:
            hotel_district = clustering_result.get_district(clustering_result.hotel_district_id)
            if hotel_district:
                hotel_info = f"District {hotel_district.district_id} ({hotel_district.name})"

        previous_day_info = {
            "anchor": previous_day_anchor,
            "district_id": previous_day_district_id,
        } if previous_day_anchor or previous_day_district_id else {}

        prompt = f"""Plan district assignments for Day {day_skeleton.day_number} in {city}.

## Preference Signals
{json.dumps(preference_summary, indent=2) if preference_summary else "{}"}

## Previous Day End (start near this if possible)
{json.dumps(previous_day_info, indent=2)}

## Available Districts
```json
{json.dumps(districts_info, indent=2)}
```

## Day Schedule (blocks to assign)
```json
{json.dumps(blocks_info, indent=2)}
```

## Hotel Location
{hotel_info}

## Task
Assign each block to a district. Minimize travel between districts.
For each block, ensure the district has POIs matching the required_categories.

## Required Response Format (JSON only)
```json
{{
  "assignments": [
    {{"block_index": 0, "district_id": "A", "reason": "Near hotel for breakfast"}},
    {{"block_index": 1, "district_id": "A", "reason": "Stay in same district for morning activity"}},
    ...
  ]
}}
```

Respond with JSON only."""

        return prompt

    async def plan_day_districts(
        self,
        day_skeleton: DaySkeleton,
        clustering_result: ClusteringResult,
        city: str,
        district_summaries: Optional[list[dict]] = None,
        preference_summary: Optional[dict] = None,
        previous_day_anchor: Optional[dict] = None,
        previous_day_district_id: Optional[str] = None,
    ) -> DayDistrictPlan:
        """
        Plan district assignments for a day using LLM.

        Falls back to deterministic planning on LLM failure.

        Args:
            day_skeleton: Day skeleton with blocks
            clustering_result: Clustering result with districts
            city: City name

        Returns:
            DayDistrictPlan with assignments for each block
        """
        if not clustering_result.districts:
            logger.warning("No districts available for planning")
            return DayDistrictPlan(day_number=day_skeleton.day_number, assignments=[])

        # Try LLM planning
        try:
            prompt = self._build_user_prompt(
                day_skeleton,
                clustering_result,
                city,
                district_summaries=district_summaries,
                preference_summary=preference_summary,
                previous_day_anchor=previous_day_anchor,
                previous_day_district_id=previous_day_district_id,
            )

            logger.info(f"Calling LLM for district planning: day={day_skeleton.day_number}")

            response = await self.llm_client.generate_structured(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=1024,
            )

            # Parse and validate response
            assignments = self._parse_llm_response(
                response,
                day_skeleton,
                clustering_result,
            )

            if assignments:
                logger.info(f"LLM district plan for day {day_skeleton.day_number}: "
                           f"{[a.district_id for a in assignments]}")
                return DayDistrictPlan(
                    day_number=day_skeleton.day_number,
                    assignments=assignments,
                )

        except Exception as e:
            logger.warning(f"LLM district planning failed: {e}")

        # Fallback to deterministic planning
        logger.info("Using deterministic fallback for district planning")
        return self._plan_deterministic(
            day_skeleton,
            clustering_result,
            previous_day_district_id=previous_day_district_id,
        )

    def _parse_llm_response(
        self,
        response: dict,
        day_skeleton: DaySkeleton,
        clustering_result: ClusteringResult,
    ) -> list[DistrictAssignment]:
        """Parse and validate LLM response."""
        assignments_data = response.get("assignments", [])
        if not isinstance(assignments_data, list):
            logger.warning("LLM response 'assignments' is not a list")
            return []

        valid_district_ids = set(clustering_result.districts.keys())
        assignments = []
        seen_indices = set()

        for item in assignments_data:
            if not isinstance(item, dict):
                continue

            block_index = item.get("block_index")
            district_id = item.get("district_id")

            # Validate block index
            if not isinstance(block_index, int) or block_index < 0:
                continue
            if block_index >= len(day_skeleton.blocks):
                continue
            if block_index in seen_indices:
                continue

            # Validate district ID
            if district_id not in valid_district_ids:
                logger.warning(f"LLM returned invalid district_id: {district_id}")
                continue

            seen_indices.add(block_index)
            assignments.append(DistrictAssignment(
                block_index=block_index,
                district_id=district_id,
                reason=item.get("reason"),
            ))

        # Check if all blocks are assigned
        if len(assignments) != len(day_skeleton.blocks):
            logger.warning(
                f"LLM assigned {len(assignments)} of {len(day_skeleton.blocks)} blocks, "
                "falling back to deterministic"
            )
            return []

        return assignments

    def _plan_deterministic(
        self,
        day_skeleton: DaySkeleton,
        clustering_result: ClusteringResult,
        previous_day_district_id: Optional[str] = None,
    ) -> DayDistrictPlan:
        """
        Deterministic district planning fallback.

        Strategy:
        1. Start with hotel district
        2. Stay in current district if it has required categories
        3. Move to nearest district with required categories if needed
        """
        if not clustering_result.districts:
            return DayDistrictPlan(day_number=day_skeleton.day_number, assignments=[])

        assignments = []

        # Start with previous day district, then hotel district or nearest to center
        current_district_id = previous_day_district_id or clustering_result.hotel_district_id
        if not current_district_id:
            # Use first district as fallback
            current_district_id = list(clustering_result.districts.keys())[0]

        current_district = clustering_result.get_district(current_district_id)

        for idx, block in enumerate(day_skeleton.blocks):
            required_categories = block.desired_categories or []

            # Check if current district has required categories
            if current_district and current_district.has_category(required_categories):
                # Stay in current district
                assignments.append(DistrictAssignment(
                    block_index=idx,
                    district_id=current_district_id,
                    reason="Staying in current district",
                ))
            else:
                # Find nearest district with required categories
                best_district = None
                best_distance = float('inf')

                for district in clustering_result.districts.values():
                    if not district.has_category(required_categories):
                        continue

                    if current_district:
                        distance = haversine_distance_km(
                            current_district.center_lat, current_district.center_lon,
                            district.center_lat, district.center_lon,
                        )
                    else:
                        distance = 0

                    if distance < best_distance:
                        best_distance = distance
                        best_district = district

                if best_district:
                    current_district = best_district
                    current_district_id = best_district.district_id

                assignments.append(DistrictAssignment(
                    block_index=idx,
                    district_id=current_district_id,
                    reason=f"Moved to district with {required_categories}" if best_district else "Fallback",
                ))

        # Optimization: try to return to hotel district for dinner/evening
        last_block = day_skeleton.blocks[-1] if day_skeleton.blocks else None
        if (
            last_block
            and last_block.block_type in (BlockType.MEAL, BlockType.REST)
            and clustering_result.hotel_district_id
            and assignments
        ):
            hotel_district = clustering_result.get_district(clustering_result.hotel_district_id)
            if hotel_district and hotel_district.has_category(last_block.desired_categories or []):
                assignments[-1] = DistrictAssignment(
                    block_index=len(day_skeleton.blocks) - 1,
                    district_id=clustering_result.hotel_district_id,
                    reason="Return to hotel district for evening",
                )

        return DayDistrictPlan(
            day_number=day_skeleton.day_number,
            assignments=assignments,
        )


class DistrictPlanner:
    """
    Unified district planner with LLM and deterministic modes.

    Provides a single interface for district planning regardless of mode.
    """

    def __init__(
        self,
        use_llm: bool = True,
        llm_client: Optional[LLMClient] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize district planner.

        Args:
            use_llm: Whether to use LLM for planning
            llm_client: Optional LLM client (for DI)
            app_settings: Optional settings override
        """
        self.use_llm = use_llm
        self._llm_planner = DistrictPlannerLLM(llm_client, app_settings)
        self._settings = app_settings or settings

    async def plan_districts(
        self,
        day_skeleton: DaySkeleton,
        clustering_result: ClusteringResult,
        city: str,
        district_summaries: Optional[list[dict]] = None,
        preference_summary: Optional[dict] = None,
        previous_day_anchor: Optional[dict] = None,
        previous_day_district_id: Optional[str] = None,
    ) -> DayDistrictPlan:
        """
        Plan district assignments for a day.

        Uses LLM if enabled, otherwise deterministic planning.
        """
        if self.use_llm:
            return await self._llm_planner.plan_day_districts(
                day_skeleton,
                clustering_result,
                city,
                district_summaries=district_summaries,
                preference_summary=preference_summary,
                previous_day_anchor=previous_day_anchor,
                previous_day_district_id=previous_day_district_id,
            )
        else:
            return self._llm_planner._plan_deterministic(
                day_skeleton,
                clustering_result,
                previous_day_district_id=previous_day_district_id,
            )
