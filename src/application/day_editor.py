"""
Day Editor service for modifying individual days in trip itineraries.

Supports both deterministic changes (add/replace/remove specific POIs) and
context-based changes (settings, presets, wishes) that rebuild the day.
"""
import logging
from uuid import UUID
from typing import List, Optional, Dict, Any, Set
from datetime import datetime, time as dt_time
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.config import settings, Settings
from src.domain.models import (
    ItineraryDay, ItineraryBlock, POICandidate, BlockType,
    DaySkeleton, SkeletonBlock
)
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_planner import POIPlanner
from src.application.route_optimizer import RouteTimeOptimizer
from src.application.poi_agent import POIPreferenceAgent, POIPreferenceProfile
from src.infrastructure.models import TripModel, ItineraryModel
from src.infrastructure.poi_providers import get_poi_provider, POIProvider

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Types of changes that can be applied to a day."""
    UPDATE_SETTINGS = "update_settings"
    SET_PRESET = "set_preset"
    ADD_PLACE = "add_place"
    REPLACE_PLACE = "replace_place"
    REMOVE_PLACE = "remove_place"
    ADD_WISH_MESSAGE = "add_wish_message"


@dataclass
class DayChange:
    """A single change to apply to a day."""
    type: ChangeType
    data: Dict[str, Any]


@dataclass
class DayContext:
    """Context for rebuilding a day."""
    tempo: str = "medium"
    start_time: str = "08:00"
    end_time: str = "18:00"
    budget: str = "medium"
    preset: Optional[str] = None
    wishes: List[str] = None

    def __post_init__(self):
        if self.wishes is None:
            self.wishes = []


class DayEditor:
    """
    Service for editing individual days in trip itineraries.

    Handles both deterministic changes (add/replace/remove POIs) and
    context-based changes (settings, presets, wishes) that trigger day rebuilding.

    Key features:
    - Preserves trip quality by reusing planning algorithms
    - Supports deterministic POI manipulations
    - Supports AI-based day reconstruction from user wishes/presets
    - Only rebuilds the affected day, not the entire trip
    """

    def __init__(
        self,
        app_settings: Optional[Settings] = None
    ):
        """
        Initialize Day Editor.

        Args:
            app_settings: Settings override (for testing)
        """
        self._settings = app_settings or settings
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()
        self.poi_planner = POIPlanner()
        self.route_optimizer = RouteTimeOptimizer()

    async def apply_changes_to_day(
        self,
        trip_id: UUID,
        day_number: int,
        changes: List[DayChange],
        db: AsyncSession,
    ) -> ItineraryDay:
        """
        Apply a batch of changes to a single day and regenerate the route.

        Args:
            trip_id: Trip UUID
            day_number: Day number (1-indexed)
            changes: List of changes to apply
            db: Database session

        Returns:
            Updated ItineraryDay

        Raises:
            ValueError: If trip/day not found or changes invalid
        """
        print(f"\n🔥 DayEditor.apply_changes_to_day() ENTERED")
        print(f"   trip_id={trip_id}, day_number={day_number}, changes={len(changes)}")

        logger.info(f"📝 Applying {len(changes)} changes to day {day_number} of trip {trip_id}")

        # Log each change type
        for i, change in enumerate(changes, 1):
            print(f"   Change {i}: {change.type.value} - {change.data}")
            logger.info(f"  Change {i}/{len(changes)}: {change.type.value}")

        # 1. Load trip and current itinerary
        print(f"📂 Loading trip and itinerary...")
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        itinerary_result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = itinerary_result.scalar_one_or_none()

        if not itinerary_model or not itinerary_model.days:
            raise ValueError(f"No itinerary found for trip {trip_id}. Generate one first.")

        # 2. Find the day to edit
        days_data = itinerary_model.days if isinstance(itinerary_model.days, list) else itinerary_model.days.get("days", [])
        day_data = None
        day_index = -1
        for idx, d in enumerate(days_data):
            if d.get("day_number") == day_number:
                day_data = d
                day_index = idx
                break

        if not day_data:
            raise ValueError(f"Day {day_number} not found in itinerary")

        # 3. Classify changes
        deterministic_changes = []  # add/replace/remove POI
        context_changes = []  # settings/preset/wishes

        for change in changes:
            if change.type in [ChangeType.ADD_PLACE, ChangeType.REPLACE_PLACE, ChangeType.REMOVE_PLACE]:
                deterministic_changes.append(change)
            else:
                context_changes.append(change)

        logger.info(f"  Deterministic changes: {len(deterministic_changes)}, Context changes: {len(context_changes)}")

        # 4. Build updated context from changes
        day_context = self._extract_day_context(day_data, trip_spec)
        day_context = self._apply_context_changes(day_context, context_changes)

        # 5. Decide rebuild strategy
        needs_full_rebuild = (
            len(context_changes) > 0 or
            len(deterministic_changes) > 0
        )

        if not needs_full_rebuild:
            # No changes, return current day
            return self._parse_itinerary_day(day_data)

        # 6. Apply changes and rebuild
        # CRITICAL FIX (2026-01-20): Track explicitly removed POIs to exclude from rebuild
        explicitly_removed_poi_ids: Set[UUID] = set()

        if len(deterministic_changes) > 0:
            # Collect removed POI IDs BEFORE applying changes
            for change in deterministic_changes:
                if change.type == ChangeType.REMOVE_PLACE:
                    place_id_str = change.data.get("place_id")
                    if place_id_str:
                        try:
                            explicitly_removed_poi_ids.add(UUID(place_id_str))
                        except (ValueError, TypeError):
                            pass

                # CRITICAL FIX (2026-01-24): Also exclude from_place_id when replacing
                # When user replaces a place, they don't want to see it again in rebuilds
                elif change.type == ChangeType.REPLACE_PLACE:
                    from_place_id_str = change.data.get("from_place_id")
                    if from_place_id_str:
                        try:
                            explicitly_removed_poi_ids.add(UUID(from_place_id_str))
                            print(f"📝 Excluding replaced POI {from_place_id_str} from rebuild")
                        except (ValueError, TypeError):
                            pass

            if explicitly_removed_poi_ids:
                print(f"📝 Tracking {len(explicitly_removed_poi_ids)} explicitly removed/replaced POIs to exclude from rebuild")
                logger.info(
                    f"📝 Tracking {len(explicitly_removed_poi_ids)} explicitly removed POIs "
                    f"to exclude from rebuild"
                )

            # Apply deterministic POI changes first
            day_data = await self._apply_deterministic_changes(
                day_data, deterministic_changes, day_context, trip_id, db
            )

            # CRITICAL FIX (2026-01-20): Check if day became empty/sparse after removals
            blocks_after_changes = day_data.get("blocks", [])
            poi_count = len([b for b in blocks_after_changes if b.get("poi")])

            MIN_POI_COUNT = 4  # 3 meals + 1 activity
            if poi_count < MIN_POI_COUNT:
                logger.warning(
                    f"⚠️ Day {day_number} has only {poi_count} POIs after deterministic changes. "
                    f"Triggering rebuild to maintain minimum {MIN_POI_COUNT} POIs."
                )
                # Force rebuild even without context_changes
                # CRITICAL: Pass explicitly removed POIs to prevent them from returning
                day_data = await self._rebuild_day_with_context(
                    trip_id, day_number, day_context, day_data, db,
                    explicitly_removed_poi_ids=explicitly_removed_poi_ids
                )

        if len(context_changes) > 0:
            # Rebuild day with new context
            # CRITICAL: Pass explicitly removed POIs to prevent them from returning
            day_data = await self._rebuild_day_with_context(
                trip_id, day_number, day_context, day_data, db,
                explicitly_removed_poi_ids=explicitly_removed_poi_ids
            )

        # 7. Optimize route with travel times
        updated_day = await self._optimize_day_route(
            trip_id, day_number, day_data, day_context, db
        )

        # 8. Update itinerary in database
        print(f"💾 Saving to database...")
        print(f"   Day index: {day_index}")
        print(f"   Updated day blocks: {len(updated_day.blocks)}")
        print(f"   Updated day POIs: {sum(1 for b in updated_day.blocks if b.poi)}")

        days_data[day_index] = updated_day.model_dump(mode='json')
        itinerary_model.days = days_data
        itinerary_model.updated_at = datetime.utcnow()

        # CRITICAL: Tell SQLAlchemy that JSONB column was modified
        flag_modified(itinerary_model, 'days')
        print(f"🚩 Flagged 'days' column as modified")

        print(f"🔒 Calling db.commit()...")
        await db.commit()
        print(f"✅ db.commit() completed successfully")

        logger.info(f"✅ Successfully updated day {day_number} of trip {trip_id}")
        logger.info(f"   Final state: {len(updated_day.blocks)} blocks, {sum(1 for b in updated_day.blocks if b.poi)} POIs")

        print(f"🎉 DayEditor.apply_changes_to_day() COMPLETED")
        return updated_day

    def _extract_day_context(self, day_data: dict, trip_spec: Any) -> DayContext:
        """Extract current context from day data."""
        # Get timing from first and last blocks
        blocks = day_data.get("blocks", [])
        start_time = blocks[0].get("start_time", "08:00") if blocks else "08:00"
        end_time = blocks[-1].get("end_time", "18:00") if blocks else "18:00"

        # Format time strings
        if isinstance(start_time, str) and ":" in start_time:
            start_str = start_time[:5]  # HH:MM
        else:
            start_str = "08:00"

        if isinstance(end_time, str) and ":" in end_time:
            end_str = end_time[:5]
        else:
            end_str = "18:00"

        return DayContext(
            tempo=trip_spec.pace.value if trip_spec.pace else "medium",
            start_time=start_str,
            end_time=end_str,
            budget=trip_spec.budget.value if trip_spec.budget else "medium",
            preset=None,
            wishes=[]
        )

    def _apply_context_changes(
        self,
        context: DayContext,
        changes: List[DayChange]
    ) -> DayContext:
        """Apply context changes to day context."""
        for change in changes:
            if change.type == ChangeType.UPDATE_SETTINGS:
                if "tempo" in change.data:
                    context.tempo = change.data["tempo"]
                if "start_time" in change.data:
                    context.start_time = change.data["start_time"]
                if "end_time" in change.data:
                    context.end_time = change.data["end_time"]
                if "budget" in change.data:
                    context.budget = change.data["budget"]

            elif change.type == ChangeType.SET_PRESET:
                context.preset = change.data.get("preset")

            elif change.type == ChangeType.ADD_WISH_MESSAGE:
                wish_text = change.data.get("text", "").strip()
                if wish_text:
                    context.wishes.append(wish_text)

        return context

    async def _apply_deterministic_changes(
        self,
        day_data: dict,
        changes: List[DayChange],
        context: DayContext,
        trip_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Apply deterministic POI changes (add/replace/remove).

        These changes directly modify the POI list without full day rebuild.
        """
        blocks = day_data.get("blocks", [])

        for change in changes:
            if change.type == ChangeType.REMOVE_PLACE:
                place_id = change.data.get("place_id")
                if place_id:
                    # Remove block with this POI (convert both to string for comparison)
                    place_id_str = str(place_id)
                    initial_count = len(blocks)
                    print(f"🗑️  REMOVE_PLACE: looking for place_id={place_id_str}")
                    print(f"   Initial blocks: {initial_count}")

                    # Debug: print all POI IDs in blocks
                    for i, b in enumerate(blocks):
                        poi = b.get("poi")
                        if poi:
                            poi_id = poi.get("poi_id", "")
                            print(f"   Block {i}: poi_id={poi_id} (type: {type(poi_id)})")

                    blocks = [b for b in blocks if not (b.get("poi") and str(b.get("poi").get("poi_id", "")) == place_id_str)]
                    removed_count = initial_count - len(blocks)
                    print(f"   Final blocks: {len(blocks)}")
                    print(f"   ✅ Removed {removed_count} blocks")
                    logger.info(f"Removed {removed_count} blocks matching place {place_id}")

            elif change.type == ChangeType.REPLACE_PLACE:
                from_place_id = change.data.get("from_place_id")
                to_place_id = change.data.get("to_place_id")  # Optional: if None, auto-select

                if from_place_id:
                    # Find block to replace
                    from_place_id_str = str(from_place_id)
                    for block in blocks:
                        poi = block.get("poi")
                        if poi and str(poi.get("poi_id", "")) == from_place_id_str:
                            # If to_place_id is provided, use it (legacy behavior)
                            if to_place_id:
                                new_poi = await self._fetch_poi_details(to_place_id, trip_id, db)
                                if new_poi:
                                    block["poi"] = new_poi.model_dump()
                                    logger.info(f"✅ Replaced place {from_place_id} with {to_place_id} (manual selection)")
                            else:
                                # NEW: Auto-select best replacement (mark-for-replacement UX)
                                logger.info(f"🔄 Auto-selecting replacement for {from_place_id}")
                                replacement = await self._find_best_replacement_auto(
                                    poi, day_data, trip_id, db
                                )
                                if replacement:
                                    block["poi"] = replacement.model_dump()
                                    logger.info(f"✅ Auto-replaced {from_place_id} with {replacement.name} (score-based)")
                                else:
                                    logger.warning(f"⚠️ No suitable replacement found for {from_place_id}")
                            break

            elif change.type == ChangeType.ADD_PLACE:
                place_id = change.data.get("place_id")
                placement = change.data.get("placement", {})

                if place_id:
                    # Fetch POI details
                    new_poi = await self._fetch_poi_details(place_id, trip_id, db)
                    if new_poi:
                        # Create new block for this POI
                        new_block = self._create_block_from_poi(
                            new_poi, placement, context
                        )

                        # Insert block based on placement strategy
                        blocks = self._insert_block(blocks, new_block, placement)
                        logger.info(f"Added place {place_id}")

        # Update day data
        day_data["blocks"] = blocks
        return day_data

    async def _fetch_poi_details(
        self,
        place_id: str,
        trip_id: UUID,
        db: AsyncSession
    ) -> Optional[POICandidate]:
        """Fetch POI details from provider."""
        try:
            # Get trip city
            trip_result = await db.execute(
                select(TripModel).where(TripModel.id == trip_id)
            )
            trip = trip_result.scalar_one_or_none()
            if not trip:
                return None

            provider = get_poi_provider(db)

            # Search for this specific POI
            # Note: This is a workaround. Ideally we'd have a get_poi_by_id method
            # Try searching by generic category first
            candidates = await provider.search_pois(
                city=trip.city,
                desired_categories=["tourist_attraction", "point_of_interest", "restaurant", "cafe"],
                limit=50
            )

            # Filter to find the specific POI by ID or name
            matching = [c for c in candidates if str(c.poi_id) == place_id or c.name == place_id]
            if matching:
                return matching[0]

            # If not found, return None (POI may need to be searched differently)
            logger.warning(f"Could not find POI {place_id} among {len(candidates)} candidates")
            return None

        except Exception as e:
            logger.error(f"Failed to fetch POI {place_id}: {e}")
            return None

    def _create_block_from_poi(
        self,
        poi: POICandidate,
        placement: dict,
        context: DayContext
    ) -> dict:
        """Create an itinerary block from a POI."""
        # Determine block type from category
        category = poi.category.lower()
        if any(meal in category for meal in ["cafe", "restaurant", "food", "breakfast", "lunch", "dinner"]):
            block_type = BlockType.MEAL
        elif "night" in category or "bar" in category or "club" in category:
            block_type = BlockType.NIGHTLIFE
        else:
            block_type = BlockType.ACTIVITY

        # Create block (times will be optimized later)
        return {
            "block_type": block_type.value,
            "start_time": context.start_time,
            "end_time": context.start_time,
            "theme": poi.category,
            "poi": poi.model_dump(),
            "travel_time_from_prev": 0,
            "travel_distance_meters": 0,
        }

    def _insert_block(
        self,
        blocks: List[dict],
        new_block: dict,
        placement: dict
    ) -> List[dict]:
        """Insert block into day based on placement strategy."""
        placement_type = placement.get("type", "auto")

        if placement_type == "in_slot":
            slot_index = placement.get("slot_index", 0)
            # Insert at specific position
            blocks.insert(min(slot_index, len(blocks)), new_block)

        elif placement_type == "at_time":
            # TODO: Insert at specific time (requires time parsing)
            # For now, append at end
            blocks.append(new_block)

        else:  # "auto"
            # Append at end (route optimizer will reorder)
            blocks.append(new_block)

        return blocks

    async def _rebuild_day_with_context(
        self,
        trip_id: UUID,
        day_number: int,
        context: DayContext,
        current_day_data: dict,
        db: AsyncSession,
        explicitly_removed_poi_ids: Optional[Set[UUID]] = None,
    ) -> dict:
        """
        Rebuild day from scratch with new context (preset, wishes, settings).

        Uses macro planner + POI planner to regenerate the day structure.

        Args:
            explicitly_removed_poi_ids: POI IDs that user explicitly removed.
                These will be excluded from the rebuild to respect user's choice.
        """
        logger.info(f"Rebuilding day {day_number} with context: preset={context.preset}, wishes={len(context.wishes)}")

        # Build modified trip spec with day-specific overrides
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)

        # Build preference profile
        preference_agent = POIPreferenceAgent(app_settings=self._settings)
        preference_profile = await preference_agent.build_profile(trip_spec, timeout_seconds=15.0)

        # Generate new macro skeleton for this day only
        # Apply preset and wishes as additional context
        additional_context = self._build_additional_context(context)

        # Generate macro plan for single day
        day_skeleton = await self._generate_day_skeleton(
            trip_spec, day_number, context, additional_context, db
        )

        # CRITICAL FIX (2026-01-20): Fetch trip-level used POIs for deduplication
        trip_used_poi_ids, trip_used_poi_names = await self._get_trip_used_pois(
            trip_id, db, exclude_day=day_number
        )

        # CRITICAL: Add explicitly removed POIs to exclusion list
        # This prevents removed places from returning after rebuild
        if explicitly_removed_poi_ids:
            trip_used_poi_ids = trip_used_poi_ids | explicitly_removed_poi_ids
            logger.info(
                f"   + {len(explicitly_removed_poi_ids)} explicitly removed POIs "
                f"(total exclusions: {len(trip_used_poi_ids)})"
            )

        # Generate POI candidates for the day
        day_blocks = await self._generate_day_pois(
            trip_id, day_number, day_skeleton, preference_profile, db,
            exclude_poi_ids=trip_used_poi_ids
        )

        # Convert to day data format
        new_day_data = {
            "day_number": day_number,
            "date": current_day_data.get("date"),
            "theme": day_skeleton.theme,
            "blocks": []
        }

        # Populate blocks with POIs
        for block_data in day_blocks:
            new_day_data["blocks"].append(block_data)

        return new_day_data

    def _build_additional_context(self, context: DayContext) -> str:
        """Build additional context string for LLM from preset and wishes."""
        parts = []

        if context.preset:
            preset_hints = {
                "overview": "Create an overview day covering major highlights and iconic sites",
                "food": "Focus heavily on culinary experiences, cafes, restaurants, and food markets",
                "walks": "Emphasize scenic walking routes, parks, and pedestrian-friendly areas",
                "avoid_crowds": "Choose less touristy locations and quieter times to avoid crowds",
                "art": "Focus on art galleries, museums, street art, and creative spaces",
                "architecture": "Emphasize architectural landmarks, historic buildings, and design highlights",
                "cozy": "Create a relaxed, cozy day with cafes, bookshops, and intimate spaces",
                "nightlife": "Plan for evening/night activities like bars, clubs, and night markets",
            }
            hint = preset_hints.get(context.preset, "")
            if hint:
                parts.append(f"Preset guidance: {hint}")

        if context.wishes:
            wishes_text = " ".join(context.wishes)
            parts.append(f"User wishes: {wishes_text}")

        return "\n".join(parts)

    async def _generate_day_skeleton(
        self,
        trip_spec: Any,
        day_number: int,
        context: DayContext,
        additional_context: str,
        db: AsyncSession,
    ) -> DaySkeleton:
        """Generate macro skeleton for a single day."""
        from datetime import date, timedelta

        # Parse times
        start_hour = int(context.start_time.split(":")[0])
        start_minute = int(context.start_time.split(":")[1])
        end_hour = int(context.end_time.split(":")[0])
        end_minute = int(context.end_time.split(":")[1])

        # Calculate day date
        start_date = trip_spec.start_date if hasattr(trip_spec, 'start_date') else date.today()
        if isinstance(start_date, str):
            from datetime import datetime as dt
            start_date = dt.fromisoformat(start_date).date()
        day_date = start_date + timedelta(days=day_number - 1)

        # Build simplified skeleton with meal and activity blocks
        # This is a simplified version - ideally we'd call macro_planner with day-specific context
        blocks = []

        # Breakfast (CRITICAL FIX 2026-01-24: Add breakfast block for morning starts)
        if start_hour < 10:  # Day starts in morning
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=dt_time(start_hour, start_minute),
                end_time=dt_time(min(start_hour + 1, 10), 0),
                theme="breakfast"
            ))

        # Morning activity (after breakfast or from start if late morning)
        if start_hour < 12:
            # If we had breakfast, start activity after it; otherwise from start_time
            activity_start_hour = start_hour + 1 if start_hour < 10 else start_hour
            blocks.append(SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=dt_time(activity_start_hour, 0),
                end_time=dt_time(12, 0),
                theme="morning exploration"
            ))

        # Lunch
        if end_hour >= 13:
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=dt_time(12, 30),
                end_time=dt_time(13, 30),
                theme="lunch"
            ))

        # Afternoon activities
        if end_hour >= 15:
            blocks.append(SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=dt_time(14, 0),
                end_time=dt_time(17, 0),
                theme="afternoon activities"
            ))

        # Dinner (CRITICAL FIX 2026-01-24: Make less restrictive - include if day extends past early afternoon)
        if end_hour >= 17:  # Changed from >= 19 to include early evening days
            # If day ends before 19:00, schedule dinner earlier
            dinner_start = 19 if end_hour >= 19 else max(17, end_hour - 2)
            dinner_end = min(dinner_start + 1, end_hour)
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=dt_time(dinner_start, 0),
                end_time=dt_time(dinner_end, end_minute if dinner_end == end_hour else 0),
                theme="dinner"
            ))

        # Evening (if nightlife preset or late end time)
        if end_hour >= 21 or context.preset == "nightlife":
            blocks.append(SkeletonBlock(
                block_type=BlockType.NIGHTLIFE,
                start_time=dt_time(20, 30),
                end_time=dt_time(end_hour, end_minute),
                theme="evening entertainment"
            ))

        return DaySkeleton(
            day_number=day_number,
            date=day_date,
            theme=f"Day {day_number} - {context.preset or 'custom'}",
            blocks=blocks
        )

    async def _get_trip_used_pois(
        self,
        trip_id: UUID,
        db: AsyncSession,
        exclude_day: Optional[int] = None
    ) -> tuple[Set[UUID], Set[str]]:
        """
        Fetch all POI IDs and names used in trip (excluding specified day).

        CRITICAL FIX (2026-01-20): Enables trip-level POI deduplication.
        Returns POIs from ALL days except the one being edited.

        Args:
            trip_id: Trip UUID
            db: Database session
            exclude_day: Day number to exclude (typically the day being edited)

        Returns:
            Tuple of (set of poi_ids, set of poi_names) for trip-level deduplication
        """
        from src.infrastructure.models import ItineraryModel

        # Get itinerary
        itinerary_result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = itinerary_result.scalar_one_or_none()

        if not itinerary_model or not itinerary_model.days:
            return set(), set()

        poi_ids = set()
        poi_names = set()

        days_data = itinerary_model.days if isinstance(itinerary_model.days, list) else itinerary_model.days.get("days", [])

        for day_data in days_data:
            day_num = day_data.get("day_number")

            # Skip the day being edited
            if exclude_day is not None and day_num == exclude_day:
                continue

            blocks = day_data.get("blocks", [])
            for block in blocks:
                poi = block.get("poi")
                if poi:
                    # Extract POI ID
                    poi_id = poi.get("poi_id")
                    if poi_id:
                        try:
                            poi_ids.add(UUID(str(poi_id)))
                        except (ValueError, TypeError):
                            pass

                    # Extract POI name
                    poi_name = poi.get("name")
                    if poi_name:
                        poi_names.add(poi_name.lower().strip())

        logger.info(
            f"Trip-level POI deduplication: Found {len(poi_ids)} unique POI IDs "
            f"from other days (excluding day {exclude_day})"
        )

        return poi_ids, poi_names

    async def _generate_day_pois(
        self,
        trip_id: UUID,
        day_number: int,
        day_skeleton: DaySkeleton,
        preference_profile: POIPreferenceProfile,
        db: AsyncSession,
        exclude_poi_ids: Optional[Set[UUID]] = None,
    ) -> List[dict]:
        """
        Generate POI candidates for day blocks.

        Args:
            exclude_poi_ids: POI IDs to exclude (from other days + explicitly removed)
        """
        if exclude_poi_ids is None:
            exclude_poi_ids = set()
        # Get trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)

        # Use POI planner to get candidates for each block
        poi_provider = get_poi_provider(db)

        day_blocks = []
        used_poi_ids = set()

        for block_idx, skeleton_block in enumerate(day_skeleton.blocks):
            if skeleton_block.block_type not in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]:
                continue

            # Search for POIs matching block theme
            category_query = skeleton_block.theme or skeleton_block.block_type.value

            # Convert theme to category list
            if skeleton_block.block_type == BlockType.MEAL:
                desired_categories = ["restaurant", "cafe", "food"]
            elif skeleton_block.block_type == BlockType.NIGHTLIFE:
                desired_categories = ["bar", "nightclub", "night_club"]
            else:  # ACTIVITY
                desired_categories = ["tourist_attraction", "museum", "art_gallery", "park"]

            candidates = await poi_provider.search_pois(
                city=trip_spec.city,
                desired_categories=desired_categories,
                limit=10
            )

            # Filter out already used POIs (within this day + from other days + explicitly removed)
            available = [c for c in candidates
                        if c.poi_id not in used_poi_ids
                        and c.poi_id not in exclude_poi_ids]

            if available:
                # Select best candidate
                selected = available[0]
                used_poi_ids.add(selected.poi_id)

                # Create block
                block_data = {
                    "block_type": skeleton_block.block_type.value,
                    "start_time": skeleton_block.start_time.strftime("%H:%M"),
                    "end_time": skeleton_block.end_time.strftime("%H:%M"),
                    "theme": skeleton_block.theme,
                    "poi": selected.model_dump(),
                    "travel_time_from_prev": 0,
                    "travel_distance_meters": 0,
                }
                day_blocks.append(block_data)
            else:
                # CRITICAL FIX (2026-01-24): Log when blocks are dropped due to no available POIs
                print(
                    f"⚠️ No POI available for {skeleton_block.block_type.value} block "
                    f"at {skeleton_block.start_time.strftime('%H:%M')} (theme: {skeleton_block.theme}). "
                    f"Found {len(candidates)} candidates but all were filtered out "
                    f"(used: {len(used_poi_ids)}, excluded: {len(exclude_poi_ids)})"
                )
                logger.warning(
                    f"⚠️ No POI available for {skeleton_block.block_type.value} block "
                    f"at {skeleton_block.start_time.strftime('%H:%M')} (theme: {skeleton_block.theme}). "
                    f"All {len(candidates)} candidates were filtered out."
                )

        return day_blocks

    async def _optimize_day_route(
        self,
        trip_id: UUID,
        day_number: int,
        day_data: dict,
        context: DayContext,
        db: AsyncSession,
    ) -> ItineraryDay:
        """
        Optimize day route with travel times and distances.

        Uses route optimizer to calculate optimal order and travel times.
        """
        # Parse blocks into POI candidates
        blocks = day_data.get("blocks", [])

        # Calculate travel times between consecutive blocks
        prev_lat, prev_lon = None, None

        for block in blocks:
            poi = block.get("poi")
            if not poi:
                continue

            curr_lat = poi.get("lat")
            curr_lon = poi.get("lon")

            if prev_lat is not None and curr_lat is not None:
                # Calculate travel time
                from src.infrastructure.poi_providers import haversine_distance_km
                distance_km = haversine_distance_km(prev_lat, prev_lon, curr_lat, curr_lon)
                distance_m = int(distance_km * 1000)

                # Estimate walking time (4 km/h average)
                travel_time_minutes = int((distance_km / 4.0) * 60)

                block["travel_distance_meters"] = distance_m
                block["travel_time_from_prev"] = travel_time_minutes

            prev_lat, prev_lon = curr_lat, curr_lon

        # Parse into ItineraryDay model
        itinerary_day = self._parse_itinerary_day(day_data)

        return itinerary_day

    def _parse_itinerary_day(self, day_data: dict) -> ItineraryDay:
        """Parse day data dict into ItineraryDay model."""
        blocks = []

        for block_data in day_data.get("blocks", []):
            poi_data = block_data.get("poi")
            poi = None

            if poi_data:
                # Handle poi_id which might already be a UUID
                raw_poi_id = poi_data.get("poi_id") or poi_data.get("id")
                if isinstance(raw_poi_id, UUID):
                    poi_id = raw_poi_id
                elif raw_poi_id:
                    poi_id = UUID(str(raw_poi_id))
                else:
                    poi_id = UUID("00000000-0000-0000-0000-000000000000")

                poi = POICandidate(
                    poi_id=poi_id,
                    name=poi_data.get("name", "Unknown"),
                    category=poi_data.get("category", "other"),
                    tags=poi_data.get("tags", []),
                    rating=poi_data.get("rating"),
                    location=poi_data.get("location"),
                    lat=poi_data.get("lat"),
                    lon=poi_data.get("lon"),
                    rank_score=poi_data.get("rank_score", 0.0)
                )

            block = ItineraryBlock(
                block_type=BlockType(block_data.get("block_type", "activity")),
                start_time=block_data.get("start_time", ""),
                end_time=block_data.get("end_time", ""),
                theme=block_data.get("theme"),
                poi=poi,
                travel_time_from_prev=block_data.get("travel_time_from_prev", 0),
                travel_distance_meters=block_data.get("travel_distance_meters", 0),
            )
            blocks.append(block)

        return ItineraryDay(
            day_number=day_data.get("day_number", 1),
            date=day_data.get("date", ""),
            theme=day_data.get("theme", ""),
            blocks=blocks
        )

    async def _find_best_replacement_auto(
        self,
        current_poi: dict,
        day_data: dict,
        trip_id: UUID,
        db: AsyncSession
    ) -> Optional[POICandidate]:
        """
        Automatically find best replacement for a POI using scoring algorithm.

        NEW FEATURE (2026-01-24): Mark-for-replacement UX.
        Instead of user selecting replacement, backend auto-selects best alternative.

        Scoring formula (same as PlaceReplacementService):
        - 60% proximity (closer to original location = better)
        - 30% rating (higher rating = better)
        - 10% popularity (more reviews = better)

        Args:
            current_poi: The POI being replaced (dict with category, lat, lon)
            day_data: Current day data (to collect used POI IDs)
            trip_id: Trip UUID
            db: Database session

        Returns:
            Best replacement POI candidate, or None if no suitable replacement found
        """
        import math

        # Extract current POI data
        current_category = current_poi.get("category", "restaurant")
        current_lat = current_poi.get("lat")
        current_lon = current_poi.get("lon")
        current_name = current_poi.get("name", "")

        if not current_lat or not current_lon:
            logger.warning(f"Cannot find replacement for {current_name}: missing coordinates")
            return None

        # Get trip city
        trip_result = await db.execute(select(TripModel).where(TripModel.id == trip_id))
        trip = trip_result.scalar_one_or_none()
        if not trip:
            logger.error(f"Trip {trip_id} not found")
            return None

        # Collect all used POI IDs in this day (to exclude from candidates)
        used_poi_ids = set()
        for block in day_data.get("blocks", []):
            poi = block.get("poi")
            if poi:
                poi_id = poi.get("poi_id")
                if poi_id:
                    try:
                        used_poi_ids.add(UUID(str(poi_id)))
                    except (ValueError, TypeError):
                        pass

        # Search for POI candidates in the same category
        poi_provider = get_poi_provider(db)

        # Determine desired categories based on current category
        if current_category in ["restaurant", "cafe", "food"]:
            desired_categories = ["restaurant", "cafe", "food"]
        elif current_category in ["bar", "nightclub", "night_club"]:
            desired_categories = ["bar", "nightclub", "night_club"]
        else:
            desired_categories = ["tourist_attraction", "museum", "art_gallery", "park", "monument"]

        logger.info(f"🔍 Searching for replacement in categories: {desired_categories}")

        candidates = await poi_provider.search_pois(
            city=trip.city,
            desired_categories=desired_categories,
            limit=50  # Get more candidates for better scoring
        )

        logger.info(f"📦 Found {len(candidates)} candidates")

        # Filter and score candidates
        max_distance_m = 3000  # 3km max distance from original location
        scored_options = []

        for candidate in candidates:
            # Filter: Skip if already used in this day
            if candidate.poi_id in used_poi_ids:
                continue

            # Filter: Skip if it's the same place
            if candidate.name.lower().strip() == current_name.lower().strip():
                continue

            # Filter: Must have coordinates
            if not candidate.lat or not candidate.lon:
                continue

            # Calculate distance using Haversine formula
            lat1, lon1 = math.radians(current_lat), math.radians(current_lon)
            lat2, lon2 = math.radians(candidate.lat), math.radians(candidate.lon)

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            c = 2 * math.asin(math.sqrt(a))
            distance_m = 6371000 * c  # Earth radius in meters

            # Filter: Max distance
            if distance_m > max_distance_m:
                continue

            # Calculate scores
            proximity_score = 1.0 - (distance_m / max_distance_m)
            rating_score = (candidate.rating or 3.0) / 5.0
            reviews = candidate.user_ratings_total or 50
            popularity_score = min(1.0, (reviews / 10000) ** 0.5)

            # Weighted total (60% proximity, 30% rating, 10% popularity)
            total_score = (
                0.6 * proximity_score +
                0.3 * rating_score +
                0.1 * popularity_score
            )

            scored_options.append({
                "candidate": candidate,
                "score": total_score,
                "distance_m": int(distance_m),
            })

        if not scored_options:
            logger.warning(f"⚠️ No suitable replacements found for {current_name}")
            return None

        # Sort by score descending
        scored_options.sort(key=lambda x: x["score"], reverse=True)

        # Return best option
        best = scored_options[0]
        logger.info(
            f"✅ Best replacement: {best['candidate'].name} "
            f"(score: {best['score']:.3f}, distance: {best['distance_m']}m, "
            f"rating: {best['candidate'].rating})"
        )

        return best["candidate"]
