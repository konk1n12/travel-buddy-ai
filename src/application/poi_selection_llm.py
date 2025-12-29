"""
LLM-based POI Selection service.

This service uses LLM to select and re-rank POI candidates that have ALREADY
been filtered deterministically (by city radius, block type, category).

CRITICAL SAFETY INVARIANT:
- The LLM can ONLY choose from candidates provided to it.
- The LLM MUST NOT invent new places.
- All LLM outputs are validated against the provided candidate list.
- On any failure (invalid JSON, unknown IDs, etc.), we fall back to deterministic ranking.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.config import settings, Settings
from src.domain.models import POICandidate, BlockType, BudgetLevel, PaceLevel
from src.domain.schemas import TripResponse
from src.infrastructure.llm_client import LLMClient, get_poi_selection_llm_client

logger = logging.getLogger(__name__)


# ============================================================================
# Context dataclasses for LLM
# ============================================================================

@dataclass
class DayContext:
    """Context about the current day being planned."""
    day_number: int
    date: str
    theme: str
    already_selected_poi_ids: list[UUID]  # POIs already selected for this day


@dataclass
class BlockContext:
    """Context about the current block being filled."""
    block_index: int
    block_type: BlockType
    start_time: str
    end_time: str
    theme: Optional[str]
    desired_categories: list[str]


@dataclass
class TripContext:
    """Summarized trip context for LLM."""
    city: str
    pace: PaceLevel
    budget: BudgetLevel
    interests: list[str]
    additional_notes: Optional[str]


# ============================================================================
# POI Selection LLM Service
# ============================================================================

class POISelectionLLMService:
    """
    LLM-based POI selection service.

    Selects and re-ranks POI candidates using LLM, with strict validation
    to ensure the LLM never invents new places.
    """

    # System prompt - VERY STRICT about not inventing places
    SYSTEM_PROMPT = """You are a POI curator for a travel itinerary. Your ONLY job is to SELECT places from a given list of candidates.

CRITICAL RULES - YOU MUST FOLLOW THESE EXACTLY:
1. You MUST ONLY choose from the candidates provided in the input.
2. You MUST NOT invent, imagine, or suggest any place that is not in the candidate list.
3. You MUST NOT modify candidate IDs or names in any way.
4. If none of the candidates are suitable, return an empty selection - DO NOT make up alternatives.
5. Return ONLY valid JSON matching the exact schema specified.

Your goal is to select the best POIs from the given candidates based on:
- User preferences (pace, interests, budget)
- Block context (meal, activity, nightlife, etc.)
- Diversity (avoid repetition within the day)
- Quality (prefer higher-rated places when appropriate)

IMPORTANT: If you are unsure about a place or it seems to not fit well, simply do not select it.
Do NOT try to fill all slots if the candidates are not good matches."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize POI Selection LLM Service.

        Args:
            llm_client: Optional LLM client (for dependency injection / testing)
            app_settings: Optional settings override (for testing)
        """
        self._llm_client = llm_client
        self._settings = app_settings or settings

    @property
    def llm_client(self) -> LLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            self._llm_client = get_poi_selection_llm_client(self._settings)
        return self._llm_client

    def _build_candidate_description(self, candidate: POICandidate) -> dict:
        """Build a compact description of a candidate for the LLM."""
        return {
            "candidate_id": str(candidate.poi_id),
            "name": candidate.name,
            "category": candidate.category,
            "tags": candidate.tags[:5] if candidate.tags else [],  # Limit tags
            "rating": candidate.rating,
            "location": candidate.location[:100] if candidate.location else "",  # Truncate
        }

    def _build_user_prompt(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        block_context: BlockContext,
        candidates: list[POICandidate],
        max_results: int,
    ) -> str:
        """Build the user prompt for POI selection."""
        # Build candidate list
        candidate_descriptions = [
            self._build_candidate_description(c) for c in candidates
        ]

        # Build list of already-used POI IDs (as strings for comparison)
        already_used = [str(poi_id) for poi_id in day_context.already_selected_poi_ids]

        prompt = f"""Select the best places for this trip block.

## Trip Information
- City: {trip_context.city}
- Pace: {trip_context.pace.value} (slow=relaxed, few activities; medium=balanced; fast=packed schedule)
- Budget: {trip_context.budget.value} (low=budget-friendly; medium=moderate; high=premium)
- Interests: {', '.join(trip_context.interests) if trip_context.interests else 'general sightseeing'}
{f'- Notes: {trip_context.additional_notes}' if trip_context.additional_notes else ''}

## Current Day
- Day {day_context.day_number}: {day_context.theme}

## Block to Fill
- Type: {block_context.block_type.value}
- Time: {block_context.start_time} - {block_context.end_time}
{f'- Theme: {block_context.theme}' if block_context.theme else ''}
- Looking for: {', '.join(block_context.desired_categories)}

## Already Selected Today (DO NOT REPEAT)
{json.dumps(already_used) if already_used else '[]'}

## Available Candidates
```json
{json.dumps(candidate_descriptions, indent=2)}
```

## Instructions
1. Select up to {max_results} places from the candidates above.
2. Order them by preference (best first).
3. Do NOT select any place from the "Already Selected Today" list.
4. Use ONLY the exact candidate_id values from the candidates list.
5. Do NOT invent new places or IDs.

## Required Response Format (JSON only, no other text)
```json
{{
  "selected_places": [
    {{
      "candidate_id": "uuid-from-candidates",
      "reason": "Brief reason for selection (optional)"
    }}
  ]
}}
```

Respond with JSON only. No explanations outside the JSON."""

        return prompt

    def _parse_and_validate_response(
        self,
        llm_response: dict,
        candidates: list[POICandidate],
        already_selected_ids: set[UUID],
        max_results: int,
    ) -> list[POICandidate]:
        """
        Parse and validate LLM response against the candidate list.

        This is the critical safety layer that ensures we never use
        any POI that wasn't in our original candidate list.

        Args:
            llm_response: Parsed JSON from LLM
            candidates: Original candidate list
            already_selected_ids: POI IDs already used today
            max_results: Maximum results to return

        Returns:
            Validated list of POICandidate objects (subset of candidates)
        """
        # Build lookup map: string UUID -> POICandidate
        candidate_map: dict[str, POICandidate] = {
            str(c.poi_id): c for c in candidates
        }

        # Extract selected places from LLM response
        selected_places = llm_response.get("selected_places", [])
        if not isinstance(selected_places, list):
            logger.warning("LLM response 'selected_places' is not a list, ignoring")
            return []

        validated_candidates: list[POICandidate] = []
        seen_ids: set[str] = set()

        for item in selected_places:
            if not isinstance(item, dict):
                logger.debug(f"Skipping non-dict item in selected_places: {item}")
                continue

            candidate_id = item.get("candidate_id")
            if not candidate_id:
                logger.debug("Skipping item without candidate_id")
                continue

            candidate_id_str = str(candidate_id)

            # Check if this ID exists in our candidates
            if candidate_id_str not in candidate_map:
                logger.warning(
                    f"LLM returned unknown candidate_id '{candidate_id_str}' - IGNORING. "
                    "This could be an attempt to invent a new place."
                )
                continue

            # Check for duplicates in this response
            if candidate_id_str in seen_ids:
                logger.debug(f"Skipping duplicate candidate_id: {candidate_id_str}")
                continue

            # Check if already used today
            candidate = candidate_map[candidate_id_str]
            if candidate.poi_id in already_selected_ids:
                logger.debug(f"Skipping already-selected POI: {candidate.name}")
                continue

            # Valid selection!
            validated_candidates.append(candidate)
            seen_ids.add(candidate_id_str)

            # Stop if we have enough
            if len(validated_candidates) >= max_results:
                break

        return validated_candidates

    async def select_pois_for_block(
        self,
        trip_context: TripContext,
        day_context: DayContext,
        block_context: BlockContext,
        candidates: list[POICandidate],
        max_results: int = 3,
    ) -> list[POICandidate]:
        """
        Use LLM to select POIs for a block from the given candidates.

        This method has a strict fallback: if anything goes wrong with the LLM
        (invalid response, parsing error, etc.), it falls back to returning
        the original candidates in their deterministic order.

        Args:
            trip_context: Summary of trip preferences
            day_context: Context about the current day
            block_context: Context about the current block
            candidates: Pre-filtered candidate POIs (from deterministic layer)
            max_results: Maximum POIs to select

        Returns:
            List of selected POICandidate objects (always a subset of candidates)
        """
        if not candidates:
            return []

        # Limit candidates to control cost (use top N by existing rank_score)
        max_candidates = self._settings.poi_selection_max_candidates
        limited_candidates = candidates[:max_candidates]

        # Build already-selected IDs set for validation
        already_selected_ids = set(day_context.already_selected_poi_ids)

        # Build prompt
        user_prompt = self._build_user_prompt(
            trip_context=trip_context,
            day_context=day_context,
            block_context=block_context,
            candidates=limited_candidates,
            max_results=max_results,
        )

        try:
            # Call LLM
            logger.info(
                f"Calling LLM for POI selection: day={day_context.day_number}, "
                f"block={block_context.block_index}, type={block_context.block_type.value}, "
                f"candidates={len(limited_candidates)}"
            )

            llm_response = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=512,  # POI selection responses are compact
            )

            # Validate and map back to candidates
            selected = self._parse_and_validate_response(
                llm_response=llm_response,
                candidates=limited_candidates,
                already_selected_ids=already_selected_ids,
                max_results=max_results,
            )

            if selected:
                logger.info(
                    f"LLM selected {len(selected)} POIs for block: "
                    f"{[c.name for c in selected]}"
                )
                return selected
            else:
                logger.warning(
                    "LLM returned no valid selections, falling back to deterministic"
                )
                # Fall through to fallback below

        except ValueError as e:
            # JSON parsing error from LLM client
            logger.warning(f"LLM POI selection failed (JSON error): {e}")
        except Exception as e:
            # Any other error (network, timeout, etc.)
            logger.warning(f"LLM POI selection failed (unexpected error): {e}")

        # FALLBACK: Use deterministic ranking (original candidate order)
        logger.info("Using deterministic fallback for POI selection")
        fallback_candidates = [
            c for c in limited_candidates
            if c.poi_id not in already_selected_ids
        ]
        return fallback_candidates[:max_results]


def build_trip_context_from_response(trip_spec: TripResponse) -> TripContext:
    """Build TripContext from TripResponse."""
    additional_notes = None
    if trip_spec.additional_preferences:
        # Extract relevant notes
        notes_parts = []
        if "note" in trip_spec.additional_preferences:
            notes_parts.append(trip_spec.additional_preferences["note"])
        if "avoid" in trip_spec.additional_preferences:
            avoid = trip_spec.additional_preferences["avoid"]
            if isinstance(avoid, list):
                notes_parts.append(f"Avoid: {', '.join(avoid)}")
            else:
                notes_parts.append(f"Avoid: {avoid}")
        if "dietary" in trip_spec.additional_preferences:
            dietary = trip_spec.additional_preferences["dietary"]
            if isinstance(dietary, list):
                notes_parts.append(f"Dietary: {', '.join(dietary)}")
            else:
                notes_parts.append(f"Dietary: {dietary}")
        if notes_parts:
            additional_notes = "; ".join(notes_parts)

    return TripContext(
        city=trip_spec.city,
        pace=trip_spec.pace,
        budget=trip_spec.budget,
        interests=trip_spec.interests,
        additional_notes=additional_notes,
    )
