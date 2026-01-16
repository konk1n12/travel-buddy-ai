"""
Fast Draft Planner - Optimized for p95 latency under 20 seconds.

This planner generates a draft itinerary as fast as possible:
1. Uses simplified LLM prompt with reduced token limit
2. 15-second hard timeout on LLM call
3. Template-based fallback for instant response if LLM times out
4. Fetches REAL POIs from database (no placeholders)
"""
import asyncio
from uuid import UUID
from typing import Optional
from datetime import datetime, date, time, timedelta
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    DaySkeleton, SkeletonBlock, BlockType, PaceLevel, BudgetLevel,
    ItineraryDay, ItineraryBlock, POICandidate
)
from src.domain.schemas import ItineraryResponse
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_trip_chat_llm_client
from src.infrastructure.poi_providers import POIProvider, get_poi_provider
from src.infrastructure.geocoding import get_geocoding_service
from src.infrastructure.models import ItineraryModel


# Hard timeout for LLM call (seconds)
# Keep short to avoid iOS request timeout (fast draft must be quick)
LLM_TIMEOUT_SECONDS = 20

# Maximum tokens for draft (reduced for speed)
DRAFT_MAX_TOKENS = 1024

# Total deadline for POI fetching (seconds)
# iOS fast-draft timeout is 90s, LLM takes up to 20s, leave buffer for response
POI_FETCH_DEADLINE_SECONDS = 55

# Concurrency for external API calls (Google Places)
# Higher = faster but more API pressure; 8 is safe for Google's rate limits
POI_FETCH_CONCURRENCY = 8

# POIs per category from external API (reduced for speed)
# We only need 1 POI per block, 6 candidates is sufficient with deduplication
EXTERNAL_POI_LIMIT_PER_CATEGORY = 6

# =============================================================================
# Hybrid Fetch Strategy: DB + Google for personalization and DB enrichment
# =============================================================================

# Minimum ratio of categories to fetch from Google (even if DB has results)
# 0.5 = at least 50% of categories will query Google for fresh/personalized results
GOOGLE_FETCH_MIN_RATIO = 0.5

# Categories that ALWAYS go to Google (high personalization value)
# These benefit most from fresh, personalized results based on user taste
ALWAYS_FETCH_FROM_GOOGLE_CATEGORIES = {
    "restaurant", "cafe", "bar",       # Meals vary by taste
    "nightlife",                        # User preferences matter a lot
    "shopping",                         # Personal taste
}

# Boost for POIs matching user interests/keywords (applied to rank_score)
PERSONALIZATION_BOOST = 5.0

# Block types that need POI candidates
BLOCK_TYPES_NEEDING_POIS = {
    BlockType.MEAL,
    BlockType.ACTIVITY,
    BlockType.NIGHTLIFE,
}


class FastDraftPlanner:
    """
    Fast draft planner optimized for p95 < 20 seconds.

    Strategy:
    1. Try LLM with 15s timeout
    2. If timeout/error, immediately fall back to template
    3. Fetch REAL POIs from database for each block
    4. Return draft itinerary with real places
    """

    # Simplified system prompt for faster generation
    SYSTEM_PROMPT = """You are a travel planner. Generate a trip skeleton as JSON.

Output ONLY valid JSON:
{
  "days": [
    {
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "theme": "Day theme",
      "blocks": [
        {"block_type": "meal|activity|nightlife|rest", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "theme": "Block theme", "desired_categories": ["category1", "category2"]}
      ]
    }
  ]
}

Rules:
- Each day: breakfast, 2-3 activities, lunch, dinner
- Respect wake/sleep times
- Match pace level
- Add desired_categories for POI search (e.g., ["cafe", "breakfast"], ["museum", "culture"], ["restaurant", "local cuisine"])
- NO explanations, ONLY JSON"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        poi_provider: Optional[POIProvider] = None,
    ):
        self.llm_client = llm_client or get_trip_chat_llm_client()
        self.poi_provider = poi_provider  # Will be set per request if None
        self.trip_spec_collector = TripSpecCollector()

    async def generate_fast_draft(
        self,
        trip_id: UUID,
        db: AsyncSession,
        include_trace: bool = True,
        enable_extended_trace: bool = False,
    ) -> ItineraryResponse:
        """
        Generate draft itinerary with p95 < 20 seconds guarantee.

        Uses LLM with timeout, falls back to template on failure.
        Then fetches REAL POIs from database.

        Args:
            trip_id: UUID of the trip
            db: Database session
            include_trace: Include basic trace information
            enable_extended_trace: Include extended debug trace (generator params, provider calls, ranking)
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(
            trip_id,
            db,
            refresh_city_photo=True,
        )
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Initialize route trace if requested
        from src.domain.route_trace import RouteTrace, GeneratorInputParams
        route_trace = None

        if include_trace:
            num_days = (trip_spec.end_date - trip_spec.start_date).days + 1

            route_trace = RouteTrace(
                trip_id=trip_id,
                city=trip_spec.city,
                total_days=num_days,
                pace=trip_spec.pace.value,
                budget=trip_spec.budget.value,
                interests=trip_spec.interests,
            )

            # Add extended trace with generator input params
            if enable_extended_trace:
                route_trace.generator_input = GeneratorInputParams(
                    trip_id=trip_id,
                    city_name=trip_spec.city,
                    city_center_lat=trip_spec.city_center_lat,
                    city_center_lon=trip_spec.city_center_lon,
                    start_date=trip_spec.start_date,
                    end_date=trip_spec.end_date,
                    total_days=num_days,
                    pace=trip_spec.pace.value,
                    budget=trip_spec.budget.value,
                    interests=trip_spec.interests,
                    num_travelers=trip_spec.num_travelers,
                    wake_time=trip_spec.daily_routine.wake_time,
                    sleep_time=trip_spec.daily_routine.sleep_time,
                    breakfast_window=(trip_spec.daily_routine.breakfast_window[0], trip_spec.daily_routine.breakfast_window[1]),
                    lunch_window=(trip_spec.daily_routine.lunch_window[0], trip_spec.daily_routine.lunch_window[1]),
                    dinner_window=(trip_spec.daily_routine.dinner_window[0], trip_spec.daily_routine.dinner_window[1]),
                    max_radius_km=20.0,  # Using default from poi_providers
                    poi_fetch_limit=5,  # Using limit from _fetch_best_poi
                    min_rating=None,
                    providers_enabled=["database"],  # Fast draft only uses DB
                    category_match_weight=10.0,
                    tag_overlap_weight=2.0,
                    budget_alignment_bonus=5.0,
                )

        # 3. Try LLM generation with timeout
        try:
            skeletons = await asyncio.wait_for(
                self._generate_with_llm(trip_spec),
                timeout=LLM_TIMEOUT_SECONDS
            )
            source = "llm"
        except asyncio.TimeoutError:
            print(f"⏱️ LLM timeout after {LLM_TIMEOUT_SECONDS}s, using template fallback")
            skeletons = self._generate_from_template(trip_spec)
            source = "template"
        except Exception as e:
            print(f"❌ LLM error: {e}, using template fallback")
            skeletons = self._generate_from_template(trip_spec)
            source = "template"

        # No need to set skeleton_generation_method - it's set via generation_method in RouteTrace init

        # 4. Initialize POI provider
        if not self.poi_provider:
            self.poi_provider = get_poi_provider(db)

        # 5. Fetch REAL POIs for each block and convert to itinerary days
        days = await self._convert_to_itinerary_with_real_pois(
            skeletons, trip_spec, db, route_trace, enable_extended_trace
        )

        # 6. Store in database
        created_at = datetime.utcnow()
        await self._store_draft(trip_id, skeletons, days, db, created_at)

        print(f"✅ Draft generated via {source} with real POIs in < 20s")

        return ItineraryResponse(
            trip_id=trip_id,
            days=days,
            created_at=created_at.isoformat() + "Z",
            route_trace=route_trace,
            city_photo_reference=trip_spec.city_photo_reference,
        )

    async def _generate_with_llm(self, trip_spec) -> list[DaySkeleton]:
        """Generate skeleton using LLM with minimal prompt."""
        num_days = (trip_spec.end_date - trip_spec.start_date).days + 1

        prompt = f"""Trip: {trip_spec.city}, {num_days} days ({trip_spec.start_date} to {trip_spec.end_date})
Pace: {trip_spec.pace.value}
Budget: {trip_spec.budget.value}
Interests: {', '.join(trip_spec.interests or []) if trip_spec.interests else 'general sightseeing'}
Wake: {trip_spec.daily_routine.wake_time}, Sleep: {trip_spec.daily_routine.sleep_time}

Generate JSON skeleton with desired_categories for each block."""

        response = await self.llm_client.generate_structured(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=DRAFT_MAX_TOKENS,
        )

        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: dict) -> list[DaySkeleton]:
        """Parse LLM response into DaySkeleton objects."""
        days_data = response.get("days", [])
        skeletons = []

        for day_data in days_data:
            blocks = []
            for block_data in day_data.get("blocks", []):
                # Normalize time strings
                start_time = self._parse_time(block_data.get("start_time", "09:00:00"))
                end_time = self._parse_time(block_data.get("end_time", "10:00:00"))

                # Get desired categories from LLM response
                desired_categories = block_data.get("desired_categories", [])
                if not desired_categories:
                    # Infer from block type
                    block_type = block_data.get("block_type", "activity")
                    desired_categories = self._infer_categories(block_type, block_data.get("theme", ""))

                blocks.append(SkeletonBlock(
                    block_type=BlockType(block_data.get("block_type", "activity")),
                    start_time=start_time,
                    end_time=end_time,
                    theme=block_data.get("theme", ""),
                    desired_categories=desired_categories,
                ))

            skeletons.append(DaySkeleton(
                day_number=day_data["day_number"],
                date=day_data["date"],
                theme=day_data.get("theme", f"Day {day_data['day_number']}"),
                blocks=blocks,
            ))

        return skeletons

    def _infer_categories(self, block_type: str, theme: str) -> list[str]:
        """Infer POI categories from block type and theme."""
        theme_lower = theme.lower()

        if block_type == "meal":
            if "breakfast" in theme_lower:
                return ["cafe", "breakfast", "bakery"]
            elif "lunch" in theme_lower:
                return ["restaurant", "local cuisine", "cafe"]
            elif "dinner" in theme_lower:
                return ["restaurant", "local cuisine", "fine dining"]
            else:
                return ["restaurant", "cafe"]
        elif block_type == "nightlife":
            return ["bar", "club", "nightlife"]
        elif block_type == "activity":
            if "museum" in theme_lower:
                return ["museum", "art", "culture"]
            elif "park" in theme_lower or "garden" in theme_lower:
                return ["park", "nature", "garden"]
            elif "shopping" in theme_lower or "market" in theme_lower:
                return ["shopping", "market"]
            elif "historic" in theme_lower or "landmark" in theme_lower:
                return ["landmark", "attraction", "historic"]
            else:
                return ["attraction", "culture", "sightseeing"]
        else:
            return ["attraction"]

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        if not time_str:
            return time(9, 0)

        time_str = time_str.strip()
        if time_str.startswith(':'):
            time_str = '00' + time_str

        parts = time_str.split(':')
        try:
            hour = int(parts[0]) if len(parts) > 0 else 9
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0
            return time(hour % 24, minute % 60, second % 60)
        except (ValueError, IndexError):
            return time(9, 0)

    def _get_primary_activity_categories(self, interests: list[str]) -> dict:
        """
        Generate personalized activity categories based on trip interests.
        Returns dict with 'morning', 'afternoon', 'evening' category lists.
        """
        interests_lower = [i.lower() for i in (interests or [])]
        interests_text = ' '.join(interests_lower)

        # Default categories (used if no specific interests match)
        morning_cats = ["attraction", "museum", "landmark"]
        afternoon_cats = ["attraction", "culture", "shopping"]
        evening_cats = ["park", "viewpoint", "attraction"]

        # Personalize based on interests
        # Museums interest → prioritize museum
        if any(kw in interests_text for kw in ['museum', 'art', 'history']):
            morning_cats = ["museum", "art_gallery", "attraction"]
            afternoon_cats = ["museum", "attraction", "culture"]

        # Architecture/views → NEVER include museum, prioritize landmarks
        elif any(kw in interests_text for kw in ['architecture', 'view', 'landmark']):
            morning_cats = ["attraction", "landmark", "viewpoint"]
            afternoon_cats = ["attraction", "landmark", "park"]
            evening_cats = ["viewpoint", "park", "attraction"]

        # Gastronomy → focus on food experiences
        if 'gastronomy' in interests_text or 'food' in interests_text:
            # Don't override morning, but adjust afternoon
            if 'museum' not in interests_text and 'art' not in interests_text:
                afternoon_cats = ["restaurant", "cafe", "market"]

        # Shopping → include shopping in afternoon
        if 'shopping' in interests_text:
            afternoon_cats = ["shopping", "market", "boutique"]

        # Nature → prioritize parks
        if 'nature' in interests_text or 'park' in interests_text:
            morning_cats = ["park", "garden", "nature"]
            afternoon_cats = ["park", "nature", "attraction"]

        # Nightlife → handled separately in template

        return {
            'morning': morning_cats,
            'afternoon': afternoon_cats,
            'evening': evening_cats
        }

    def _generate_from_template(self, trip_spec) -> list[DaySkeleton]:
        """
        Generate skeleton from template (instant, no LLM).

        This is the fallback when LLM times out or fails.
        """
        num_days = (trip_spec.end_date - trip_spec.start_date).days + 1
        skeletons = []

        # Get time preferences
        wake = trip_spec.daily_routine.wake_time
        sleep = trip_spec.daily_routine.sleep_time
        breakfast_start, breakfast_end = trip_spec.daily_routine.breakfast_window
        lunch_start, lunch_end = trip_spec.daily_routine.lunch_window
        dinner_start, dinner_end = trip_spec.daily_routine.dinner_window

        # Determine activity count based on pace
        if trip_spec.pace == PaceLevel.SLOW:
            activities_per_day = 2
        elif trip_spec.pace == PaceLevel.FAST:
            activities_per_day = 4
        else:
            activities_per_day = 3

        # Day themes based on interests
        themes = self._generate_day_themes(trip_spec.interests, num_days)

        # Get personalized activity categories
        activity_cats = self._get_primary_activity_categories(trip_spec.interests)

        for day_num in range(1, num_days + 1):
            current_date = trip_spec.start_date + timedelta(days=day_num - 1)
            blocks = []

            # Breakfast
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=breakfast_start,
                end_time=breakfast_end,
                theme="Breakfast",
                desired_categories=["cafe", "breakfast", "bakery"],
            ))

            # Morning activity - PERSONALIZED
            blocks.append(SkeletonBlock(
                block_type=BlockType.ACTIVITY,
                start_time=time(10, 0),
                end_time=time(12, 30),
                theme="Morning exploration",
                desired_categories=activity_cats['morning'],
            ))

            # Lunch
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=lunch_start,
                end_time=lunch_end,
                theme="Lunch",
                desired_categories=["restaurant", "local cuisine", "cafe"],
            ))

            # Afternoon activities - PERSONALIZED
            if activities_per_day >= 2:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.ACTIVITY,
                    start_time=time(14, 30),
                    end_time=time(17, 0),
                    theme="Afternoon exploration",
                    desired_categories=activity_cats['afternoon'],
                ))

            if activities_per_day >= 3:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.ACTIVITY,
                    start_time=time(17, 30),
                    end_time=time(19, 0),
                    theme="Evening stroll",
                    desired_categories=activity_cats['evening'],
                ))

            # Dinner
            blocks.append(SkeletonBlock(
                block_type=BlockType.MEAL,
                start_time=dinner_start,
                end_time=dinner_end,
                theme="Dinner",
                desired_categories=["restaurant", "local cuisine", "fine dining"],
            ))

            # Nightlife (only if interested and not last day)
            if "nightlife" in [i.lower() for i in (trip_spec.interests or [])] and day_num < num_days:
                blocks.append(SkeletonBlock(
                    block_type=BlockType.NIGHTLIFE,
                    start_time=time(22, 0),
                    end_time=time(1, 0),
                    theme="Nightlife",
                    desired_categories=["bar", "club", "nightlife"],
                ))

            skeletons.append(DaySkeleton(
                day_number=day_num,
                date=current_date,
                theme=themes[day_num - 1] if day_num <= len(themes) else f"Day {day_num}",
                blocks=blocks,
            ))

        return skeletons

    def _generate_day_themes(self, interests: list[str], num_days: int) -> list[str]:
        """Generate day themes based on interests."""
        default_themes = [
            "City Center & Landmarks",
            "Local Culture & Food",
            "Hidden Gems & Parks",
            "Shopping & Entertainment",
            "Relaxation & Exploration",
        ]

        # Customize based on interests
        if interests:
            interest_themes = {
                "food": "Culinary Adventures",
                "culture": "Cultural Immersion",
                "nightlife": "Evening Entertainment",
                "history": "Historical Discoveries",
                "art": "Art & Museums",
                "nature": "Nature & Parks",
                "shopping": "Shopping & Markets",
                "architecture": "Architectural Highlights",
            }

            themed = []
            for i, interest in enumerate(interests[:num_days]):
                lower_interest = interest.lower()
                for key, theme in interest_themes.items():
                    if key in lower_interest:
                        themed.append(theme)
                        break
                else:
                    themed.append(default_themes[i % len(default_themes)])

            # Fill remaining days with defaults
            while len(themed) < num_days:
                themed.append(default_themes[len(themed) % len(default_themes)])

            return themed

        return default_themes[:num_days]

    async def _convert_to_itinerary_with_real_pois(
        self,
        skeletons: list[DaySkeleton],
        trip_spec,
        db: AsyncSession,
        route_trace=None,
        enable_extended_trace: bool = False,
    ) -> list[ItineraryDay]:
        """
        Convert skeletons to itinerary days with REAL POIs from database.

        NEW ALGORITHM:
        1. Analyze all blocks, count needed POIs per category
        2. Fetch large POI pool for each category (with 2x margin)
        3. For each block, randomly select 10 candidates from pool (rating >= 4.5)
        4. Route optimizer selects best POI with deduplication
        5. Never return empty blocks - always find alternative
        """
        # STEP 1: Analyze blocks and collect ALL unique categories
        all_categories_needed = set()

        for skeleton in skeletons:
            for skel_block in skeleton.blocks:
                if skel_block.block_type in BLOCK_TYPES_NEEDING_POIS:
                    # Add ALL desired categories, not just primary
                    for cat in skel_block.desired_categories:
                        all_categories_needed.add(cat)

        print(f"\n📊 POI Requirements Analysis:")
        print(f"  Total unique categories needed: {len(all_categories_needed)}")
        print(f"  Categories: {sorted(all_categories_needed)}")

        # STEP 2: Fetch large POI pools for each category
        poi_pools = await self._fetch_poi_pools(
            city=trip_spec.city,
            categories=all_categories_needed,
            budget=trip_spec.budget,
            db=db,
            trip_spec=trip_spec,
            city_center_lat=trip_spec.city_center_lat,
            city_center_lon=trip_spec.city_center_lon,
        )

        # STEP 3: Build itinerary with candidate selection + deduplication
        days = []
        used_poi_ids = set()  # Track used POIs across entire trip

        for skeleton in skeletons:
            blocks = []

            for block_index, skel_block in enumerate(skeleton.blocks):
                poi = None
                block_trace = None

                # Fetch candidates for blocks that need them
                if skel_block.block_type in BLOCK_TYPES_NEEDING_POIS:
                    poi, block_trace = await self._select_poi_from_pool(
                        skeleton_block=skel_block,
                        poi_pools=poi_pools,
                        used_poi_ids=used_poi_ids,
                        day_number=skeleton.day_number,
                        block_index=block_index,
                        trip_spec=trip_spec,
                        db=db,
                        city_center_lat=trip_spec.city_center_lat,
                        city_center_lon=trip_spec.city_center_lon,
                        enable_extended_trace=enable_extended_trace,
                    )

                    # Add to used set (deduplication happens here)
                    if poi:
                        used_poi_ids.add(poi.poi_id)

                    # Add block trace if tracing is enabled
                    if route_trace and block_trace:
                        route_trace.block_traces.append(block_trace)

                blocks.append(ItineraryBlock(
                    block_type=skel_block.block_type,
                    start_time=skel_block.start_time,
                    end_time=skel_block.end_time,
                    poi=poi,
                    travel_time_from_prev=0,  # Skip travel time for speed
                    travel_distance_meters=None,
                    travel_polyline=None,
                    notes=skel_block.theme if not poi else None,
                ))

            days.append(ItineraryDay(
                day_number=skeleton.day_number,
                date=skeleton.date,
                theme=skeleton.theme,
                blocks=blocks,
            ))

        return days

    def _normalize_category(self, category: str) -> str:
        """Normalize a single category to a canonical value."""
        alias_map = {
            "breakfast": "cafe",
            "bakery": "cafe",
            "fine dining": "restaurant",
            "local cuisine": "restaurant",
            "viewpoint": "attraction",
            "landmark": "attraction",
            "culture": "museum",
        }

        key = category.lower()
        mapped = alias_map.get(key, key)

        # Heuristic mapping for common free-form categories
        if any(token in key for token in ("restaurant", "cuisine", "dining", "food")):
            mapped = "restaurant"
        elif any(token in key for token in ("cafe", "coffee", "bakery")):
            mapped = "cafe"
        elif "bar" in key:
            mapped = "bar"
        elif any(token in key for token in ("museum", "gallery")):
            mapped = "museum"
        elif any(token in key for token in ("attraction", "landmark", "sight", "viewpoint")):
            mapped = "attraction"
        elif any(token in key for token in ("park", "garden")):
            mapped = "park"
        elif any(token in key for token in ("shopping", "market", "mall")):
            mapped = "shopping"
        elif any(token in key for token in ("nightlife", "club")):
            mapped = "nightlife"
        elif any(token in key for token in ("spa", "wellness", "gym")):
            mapped = "wellness"

        return mapped

    def _normalize_categories(self, categories: set) -> tuple[set, dict]:
        """Normalize desired categories to a smaller canonical set."""
        normalized = set()
        aliases = {}
        for category in categories:
            mapped = self._normalize_category(category)
            normalized.add(mapped)
            aliases[category] = mapped
        return normalized, aliases

    def _infer_block_type_for_category(self, category: str) -> BlockType:
        """Infer block type from a category string for provider filtering."""
        key = category.lower()
        if key in {"restaurant", "cafe", "bar", "bakery", "food"}:
            return BlockType.MEAL
        if key in {"nightlife"}:
            return BlockType.NIGHTLIFE
        return BlockType.ACTIVITY

    def _build_personalized_keywords(self, trip_spec, category: str) -> list[str]:
        """
        Build personalized search keywords based on user preferences.

        Uses:
        - trip_spec.interests: e.g., ["gastronomy", "nightlife", "modern art"]
        - trip_spec.additional_preferences: e.g., {"dietary": "vegetarian", "music": "techno"}
        - trip_spec.structured_preferences: e.g., [{"keyword": "georgian", "category": "restaurant"}]
        - trip_spec.budget: affects price-related keywords

        Returns list of keywords to enhance Google Places search queries.
        """
        keywords = []
        category_lower = category.lower()

        # Extract from interests
        interests = getattr(trip_spec, 'interests', []) or []
        for interest in interests:
            interest_lower = interest.lower()
            # Map interests to search keywords
            if category_lower in ("restaurant", "cafe", "bar"):
                if "gastronomy" in interest_lower or "food" in interest_lower:
                    keywords.append("local cuisine")
                if "кофейни" in interest_lower or "cafe" in interest_lower or "dessert" in interest_lower:
                    keywords.append("specialty coffee")
            elif category_lower == "nightlife":
                if "ночная" in interest_lower or "nightlife" in interest_lower:
                    keywords.append("popular nightclub")
            elif category_lower == "museum":
                if "современное искусство" in interest_lower or "modern art" in interest_lower:
                    keywords.append("contemporary art")
                if "истори" in interest_lower or "history" in interest_lower:
                    keywords.append("historical")

        # Extract from additional_preferences
        additional = getattr(trip_spec, 'additional_preferences', {}) or {}
        if isinstance(additional, dict):
            # Dietary preferences
            dietary = additional.get("dietary") or additional.get("diet")
            if dietary:
                if isinstance(dietary, list):
                    keywords.extend(dietary[:2])  # Max 2 dietary keywords
                else:
                    keywords.append(str(dietary))

            # Music preferences (for nightlife)
            if category_lower == "nightlife":
                music = additional.get("music") or additional.get("music_preference")
                if music:
                    keywords.append(str(music))

            # Avoid preferences (negate)
            avoid = additional.get("avoid", [])
            if isinstance(avoid, list) and category_lower not in avoid:
                pass  # Don't add negative keywords to search

        # Extract from structured_preferences
        structured = getattr(trip_spec, 'structured_preferences', []) or []
        for pref in structured:
            if hasattr(pref, 'category') and hasattr(pref, 'keyword'):
                pref_category = (pref.category or "").lower()
                if pref_category == category_lower or not pref_category:
                    keyword = pref.keyword
                    if keyword and keyword not in keywords:
                        keywords.append(keyword)

        # Budget-based keywords
        budget = getattr(trip_spec, 'budget', None)
        if budget:
            budget_str = str(budget.value if hasattr(budget, 'value') else budget).lower()
            if budget_str == "high" and category_lower in ("restaurant", "bar"):
                keywords.append("upscale")
            elif budget_str == "low" and category_lower in ("restaurant", "cafe"):
                keywords.append("budget-friendly")

        # Deduplicate and limit
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)

        return unique_keywords[:3]  # Max 3 keywords per category

    async def _fetch_category_pool(
        self,
        category: str,
        trip_spec,
        db: AsyncSession,
        city_center_lat: Optional[float],
        city_center_lon: Optional[float],
        max_radius_km: float,
        min_rating: float,
        limit: int,
        poi_provider: Optional["POIProvider"] = None,
        fetch_details: bool = False,
        search_keywords: Optional[list[str]] = None,
    ) -> list[POICandidate]:
        """
        Fetch a POI pool for a category using the composite provider.

        Args:
            fetch_details: If False, skip Google Place Details API calls (fast mode).
                          This significantly reduces latency for new cities.
            search_keywords: Personalized keywords to enhance Google search queries.
                            E.g., ["vegetarian", "local cuisine"] for restaurants.
        """
        provider = poi_provider
        if provider is None:
            if not self.poi_provider:
                self.poi_provider = get_poi_provider(db)
            provider = self.poi_provider

        normalized_category = self._normalize_category(category)
        block_type = self._infer_block_type_for_category(normalized_category)

        candidates = await provider.search_pois(
            city=trip_spec.city,
            desired_categories=[normalized_category],
            budget=trip_spec.budget,
            limit=limit,
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            max_radius_km=max_radius_km,
            block_type=block_type,
            fetch_details=fetch_details,
            search_keywords=search_keywords,
        )

        if not candidates:
            return []

        filtered = [c for c in candidates if (c.rating or 0) >= min_rating]
        if len(filtered) >= 3:
            return filtered

        return candidates

    async def _fetch_poi_pools(
        self,
        city: str,
        categories: set,
        budget: BudgetLevel,
        db: AsyncSession,
        trip_spec,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
    ) -> dict:
        """
        Hybrid POI fetching: DB baseline + Google for personalization and DB enrichment.

        Strategy:
        1. Geocode city to get center coordinates
        2. Fetch ALL categories from DB in one bulk query (fast baseline)
        3. ALWAYS fetch from Google for:
           - Categories in ALWAYS_FETCH_FROM_GOOGLE_CATEGORIES (high personalization value)
           - At least GOOGLE_FETCH_MIN_RATIO (50%) of remaining categories
           - All missing categories (no DB results)
        4. Use personalized search keywords based on user preferences
        5. Merge DB + Google results, boosting personalized matches

        This ensures:
        - Personalized results based on user interests
        - Continuous DB enrichment with new POIs
        - Fast response (DB provides baseline)
        """
        import random
        import time as time_module
        from src.infrastructure.poi_providers import DBPOIProvider, GooglePlacesPOIProvider
        from src.infrastructure.database import AsyncSessionLocal

        max_radius_km = 50.0
        normalized_categories, category_aliases = self._normalize_categories(categories)

        # Geocode city
        if city_center_lat is None or city_center_lon is None:
            geocoding_service = get_geocoding_service()
            geocoding_result = await geocoding_service.geocode_city(city)
            if geocoding_result:
                city_center_lat = geocoding_result.lat
                city_center_lon = geocoding_result.lon
        if city_center_lat is not None and city_center_lon is not None:
            print(f"  📍 City center: {city} ({city_center_lat:.4f}, {city_center_lon:.4f})")
        else:
            print(f"  ⚠️ Could not geocode '{city}', distance validation disabled")

        # =========================================================================
        # STEP 1: Fast DB bulk query (baseline)
        # =========================================================================
        print(f"  📚 DB fetch: {len(normalized_categories)} categories...")
        db_provider = DBPOIProvider(db)
        db_pools = await db_provider.search_pois_bulk(
            city=city,
            all_categories=normalized_categories,
            budget=budget,
            limit_per_category=15,  # Reduced since we're also fetching from Google
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            max_radius_km=max_radius_km,
            min_rating=4.5,
            include_tags=False,
        )

        db_total = sum(len(pois) for pois in db_pools.values())
        print(f"  📚 DB returned {db_total} POIs")

        # =========================================================================
        # STEP 2: Determine which categories to fetch from Google
        # =========================================================================
        categories_to_fetch_from_google = set()

        # 2a. Missing categories (no DB results) - always fetch
        missing_categories = {
            cat for cat in normalized_categories
            if not db_pools.get(cat)
        }
        categories_to_fetch_from_google.update(missing_categories)

        # 2b. High-personalization categories - always fetch from Google
        always_fetch = normalized_categories & ALWAYS_FETCH_FROM_GOOGLE_CATEGORIES
        categories_to_fetch_from_google.update(always_fetch)

        # 2c. Ensure at least GOOGLE_FETCH_MIN_RATIO of categories go to Google
        remaining = normalized_categories - categories_to_fetch_from_google
        min_google_count = int(len(normalized_categories) * GOOGLE_FETCH_MIN_RATIO)
        additional_needed = max(0, min_google_count - len(categories_to_fetch_from_google))
        if additional_needed > 0 and remaining:
            # Randomly select additional categories for diversity
            additional = random.sample(list(remaining), min(additional_needed, len(remaining)))
            categories_to_fetch_from_google.update(additional)

        print(f"  🌐 Google fetch: {len(categories_to_fetch_from_google)}/{len(normalized_categories)} categories")
        print(f"     - Missing from DB: {len(missing_categories)}")
        print(f"     - High-personalization: {len(always_fetch)}")
        print(f"     - Additional for {GOOGLE_FETCH_MIN_RATIO*100:.0f}% ratio: {additional_needed}")

        # =========================================================================
        # STEP 3: Fetch from Google with personalized keywords
        # =========================================================================
        google_pools: dict[str, list[POICandidate]] = {}

        if categories_to_fetch_from_google:
            fetch_start = time_module.time()
            semaphore = asyncio.Semaphore(POI_FETCH_CONCURRENCY)

            async def fetch_from_google(category: str) -> tuple[str, list[POICandidate]]:
                elapsed = time_module.time() - fetch_start
                if elapsed > POI_FETCH_DEADLINE_SECONDS:
                    print(f"  ⏱️ Deadline exceeded, skipping {category}")
                    return category, []

                # Build personalized keywords for this category
                keywords = self._build_personalized_keywords(trip_spec, category)

                async with semaphore:
                    try:
                        async with AsyncSessionLocal() as session:
                            provider = get_poi_provider(session)
                            candidates = await self._fetch_category_pool(
                                category=category,
                                trip_spec=trip_spec,
                                db=session,
                                city_center_lat=city_center_lat,
                                city_center_lon=city_center_lon,
                                max_radius_km=max_radius_km,
                                min_rating=4.0,  # Lower threshold for Google (more variety)
                                limit=EXTERNAL_POI_LIMIT_PER_CATEGORY,
                                poi_provider=provider,
                                fetch_details=False,
                                search_keywords=keywords if keywords else None,
                            )
                            if keywords and candidates:
                                print(f"     🔍 {category} + keywords {keywords}: {len(candidates)} POIs")
                            return category, candidates
                    except Exception as e:
                        print(f"  ⚠️ Failed to fetch {category}: {e}")
                        return category, []

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[fetch_from_google(cat) for cat in categories_to_fetch_from_google]),
                    timeout=POI_FETCH_DEADLINE_SECONDS
                )
                for category, candidates in results:
                    if candidates:
                        google_pools[category] = candidates
            except asyncio.TimeoutError:
                print(f"  ⏱️ Google fetch timeout after {POI_FETCH_DEADLINE_SECONDS}s, using partial results")

            fetch_elapsed = time_module.time() - fetch_start
            google_total = sum(len(pois) for pois in google_pools.values())
            print(f"  🌐 Google returned {google_total} POIs in {fetch_elapsed:.1f}s")

        # =========================================================================
        # STEP 4: Merge DB + Google with personalization boost
        # =========================================================================
        base_pools: dict[str, list[POICandidate]] = {}

        for category in normalized_categories:
            db_candidates = db_pools.get(category, [])
            google_candidates = google_pools.get(category, [])

            # Deduplicate by poi_id, preferring Google (newer/personalized)
            seen_ids = set()
            merged = []

            # First add Google results (with personalization boost)
            for poi in google_candidates:
                if poi.poi_id not in seen_ids:
                    seen_ids.add(poi.poi_id)
                    # Apply personalization boost to rank_score
                    boosted_poi = POICandidate(
                        poi_id=poi.poi_id,
                        name=poi.name,
                        category=poi.category,
                        tags=poi.tags,
                        rating=poi.rating,
                        user_ratings_total=poi.user_ratings_total,
                        price_level=poi.price_level,
                        business_status=poi.business_status,
                        open_now=poi.open_now,
                        location=poi.location,
                        lat=poi.lat,
                        lon=poi.lon,
                        description=poi.description,
                        reviews=poi.reviews,
                        rank_score=(poi.rank_score or 0) + PERSONALIZATION_BOOST,
                    )
                    merged.append(boosted_poi)

            # Then add DB results (no boost)
            for poi in db_candidates:
                if poi.poi_id not in seen_ids:
                    seen_ids.add(poi.poi_id)
                    merged.append(poi)

            # Sort by rank_score (boosted Google results will be higher)
            merged.sort(key=lambda p: p.rank_score or 0, reverse=True)
            base_pools[category] = merged

        # =========================================================================
        # STEP 5: Expand to original aliases and log
        # =========================================================================
        poi_pools = {}
        for original_category in categories:
            mapped = category_aliases.get(original_category, original_category)
            poi_pools[original_category] = base_pools.get(mapped, [])

        total_pois = sum(len(pois) for pois in poi_pools.values())
        db_only = sum(1 for cat in normalized_categories if cat not in categories_to_fetch_from_google and db_pools.get(cat))
        print(f"  ✓ Hybrid fetch complete: {total_pois} POIs across {len(categories)} categories")
        print(f"    - From DB only: {db_only} categories")
        print(f"    - From Google (with personalization): {len(google_pools)} categories")

        return poi_pools

    def _is_nightlife_category(self, category: str) -> bool:
        """Check if a category is nightlife-related (only suitable for evening/night)."""
        nightlife_keywords = {"nightlife", "night_club", "club", "nightclub"}
        return any(keyword in category.lower() for keyword in nightlife_keywords)

    def _is_evening_or_night_block(self, start_time) -> bool:
        """
        Check if a block is in evening/night time (suitable for nightlife).

        Args:
            start_time: Block start time (can be datetime.time object or "HH:MM:SS" string)

        Returns:
            True if block starts at or after 18:00 (6 PM), False otherwise
        """
        from datetime import time
        try:
            # Handle both datetime.time objects and strings
            if isinstance(start_time, time):
                hour = start_time.hour
            elif isinstance(start_time, str):
                hour = int(start_time.split(":")[0])
            else:
                return False

            # Nightlife suitable only after 18:00 (6 PM)
            return hour >= 18
        except (ValueError, IndexError, AttributeError):
            return False

    async def _select_poi_from_pool(
        self,
        skeleton_block,
        poi_pools: dict,
        used_poi_ids: set,
        day_number: int,
        block_index: int,
        trip_spec,
        db: AsyncSession,
        city_center_lat: Optional[float],
        city_center_lon: Optional[float],
        enable_extended_trace: bool = False,
    ):
        """
        Select best POI from pool with deduplication.

        Strategy:
        1. Get POI pool for this category
        2. Filter out already used POIs
        3. Filter nightlife categories by time-of-day (only evening/night)
        4. Randomly select up to 10 candidates
        5. Choose best candidate by rank_score
        6. If no unused POIs, expand search to related categories
        7. NEVER return None - always find alternative
        """
        import random
        from src.domain.route_trace import BlockSelectionTrace

        desired_categories = skeleton_block.desired_categories or []
        block_start_time = skeleton_block.start_time
        is_evening_block = self._is_evening_or_night_block(block_start_time)

        # CRITICAL: Filter out nightlife categories if block is during daytime
        if not is_evening_block:
            original_count = len(desired_categories)
            desired_categories = [
                cat for cat in desired_categories
                if not self._is_nightlife_category(cat)
            ]
            if original_count > len(desired_categories):
                print(f"🚫 Filtered out nightlife categories for daytime block (start={block_start_time})")

        fallback_categories: list[str]
        if skeleton_block.block_type == BlockType.MEAL:
            fallback_categories = ["restaurant", "cafe", "bar"]
        elif skeleton_block.block_type == BlockType.NIGHTLIFE:
            # For nightlife blocks, use bar as fallback if too early
            if not is_evening_block:
                fallback_categories = ["restaurant", "bar"]
                print(f"⚠️ Nightlife block at {block_start_time} (before 18:00), using restaurant/bar fallback")
            else:
                fallback_categories = ["nightlife", "bar"]
        else:
            fallback_categories = ["attraction", "museum", "park", "shopping"]

        candidate_categories = []
        for category in desired_categories + fallback_categories:
            # Double-check: never add nightlife categories for daytime blocks
            if not is_evening_block and self._is_nightlife_category(category):
                continue
            if category not in candidate_categories:
                candidate_categories.append(category)

        available_pois: list[POICandidate] = []
        for category in candidate_categories:
            pool = poi_pools.get(category, [])

            if not pool:
                pool = await self._fetch_category_pool(
                    category=category,
                    trip_spec=trip_spec,
                    db=db,
                    city_center_lat=city_center_lat,
                    city_center_lon=city_center_lon,
                    max_radius_km=50.0,
                    min_rating=4.0,
                    limit=EXTERNAL_POI_LIMIT_PER_CATEGORY,
                    fetch_details=False,  # Skip Place Details for speed
                )
                if pool:
                    poi_pools[category] = pool

            if pool:
                available_pois = [p for p in pool if p.poi_id not in used_poi_ids]
            if available_pois:
                break

        if not available_pois:
            print(
                f"❌ No available POIs in desired categories {desired_categories} "
                f"for day {day_number}, block {block_index}"
            )
            return None, None

        # Randomly select up to 10 candidates
        num_candidates = min(10, len(available_pois))
        candidates = random.sample(available_pois, num_candidates)

        # Sort by rank_score (descending)
        candidates.sort(key=lambda c: c.rank_score, reverse=True)

        # Select best candidate
        best_poi = candidates[0]

        print(f"  Day {day_number}, Block {block_index}: Selected '{best_poi.name}' (score: {best_poi.rank_score:.1f}, rating: {best_poi.rating})")

        # Create trace if needed
        block_trace = None
        if enable_extended_trace:
            block_trace = BlockSelectionTrace(
                day_number=day_number,
                block_index=block_index,
                block_type=skeleton_block.block_type.value,
                block_theme=skeleton_block.theme,
                desired_categories=skeleton_block.desired_categories,
                selected_poi_id=best_poi.poi_id,
                selected_poi_name=best_poi.name,
                provider_calls=[],
                filter_rules_applied=[],
                ranking_trace=None,
                selection_alternatives=[],
            )

        return best_poi, block_trace

    async def _fetch_best_poi_with_trace(
        self,
        city: str,
        categories: list[str],
        budget: BudgetLevel,
        used_poi_ids: set,
        enable_extended_trace: bool,
        block_type: str,
        theme: str,
        day_number: int,
        block_index: int,
    ):
        """Fetch the best available POI from database with optional trace."""
        from src.domain.route_trace import (
            BlockSelectionTrace, ProviderCallTrace, CandidatePOISample,
            FilterRuleTrace, POIFilteredOut, RankingTrace, POIScoringBreakdown,
            SelectionAlternative, FilterReason
        )
        import time as time_module

        poi = None
        block_trace = None

        if not self.poi_provider:
            return None, None

        try:
            # Measure provider call latency
            start_time = time_module.time()

            # Get candidates (increased limit for multi-day trips to avoid duplicates)
            candidates = await self.poi_provider.search_pois(
                city=city,
                desired_categories=categories,
                budget=budget,
                limit=30,  # Fetch more options to avoid duplicates across multiple days
            )

            latency_ms = (time_module.time() - start_time) * 1000

            # Create trace if extended trace is enabled
            if enable_extended_trace:
                # Provider call trace
                provider_calls = [ProviderCallTrace(
                    provider_name="database",
                    request_params={
                        "city": city,
                        "categories": categories,
                        "budget": budget.value,
                        "limit": 5,
                    },
                    candidates_returned=len(candidates),
                    latency_ms=round(latency_ms, 2),
                    status="success",
                    error_message=None,
                    sample_candidates=[
                        CandidatePOISample(
                            poi_id=c.poi_id,
                            poi_name=c.name,
                            category=c.category,
                            tags=c.tags or [],
                            rating=c.rating,
                            lat=c.lat,
                            lon=c.lon,
                        )
                        for c in candidates[:5]  # Limit to 5 samples
                    ],
                )]

                # Filter rules trace (candidates already used)
                filtered_out = []
                for candidate in candidates:
                    if candidate.poi_id in used_poi_ids:
                        filtered_out.append(POIFilteredOut(
                            poi_id=candidate.poi_id,
                            poi_name=candidate.name,
                            reason=FilterReason.ALREADY_USED,
                            details="POI already used in itinerary",
                        ))

                filter_rules = []
                if filtered_out:
                    filter_rules.append(FilterRuleTrace(
                        rule_name="already_used",
                        dropped_count=len(filtered_out),
                        examples_dropped=filtered_out[:5],  # Limit to 5 examples
                    ))

                # Ranking trace (simplified - we don't have actual scores in fast draft)
                available_candidates = [c for c in candidates if c.poi_id not in used_poi_ids]
                # Don't fall back to used candidates - keep available_candidates empty if all used

                ranking_trace = None
                if available_candidates:
                    from src.domain.route_trace import ScoringFactor

                    ranking_trace = RankingTrace(
                        total_candidates=len(available_candidates),
                        top_candidates=[
                            POIScoringBreakdown(
                                poi_id=c.poi_id,
                                poi_name=c.name,
                                total_score=c.rating or 0.0,  # Use rating as score
                                factors={
                                    ScoringFactor.CATEGORY_MATCH: 5.0 if categories and c.category in categories else 0.0,
                                    ScoringFactor.RATING: c.rating or 0.0,
                                },
                                explanation=f"Rating: {c.rating or 0.0}" + (f", matches category '{c.category}'" if c.category in categories else "")
                            )
                            for c in available_candidates[:5]  # Top 5
                        ],
                        avg_score=sum(c.rating or 0.0 for c in available_candidates) / len(available_candidates) if available_candidates else None,
                        max_score=max((c.rating or 0.0) for c in available_candidates) if available_candidates else None,
                        min_score=min((c.rating or 0.0) for c in available_candidates) if available_candidates else None,
                    )

                # Selection alternatives
                selection_alternatives = []
                if len(available_candidates) > 1:
                    for i, candidate in enumerate(available_candidates[1:4], start=2):  # Next 3
                        selection_alternatives.append(SelectionAlternative(
                            poi_id=candidate.poi_id,
                            poi_name=candidate.name,
                            rank=i,
                            score=candidate.rating or 0.0,
                            reason_not_selected=f"Selected higher-ranked POI" if i == 2 else None,
                        ))

            # Select first unused candidate
            for candidate in candidates:
                if candidate.poi_id not in used_poi_ids:
                    poi = candidate
                    break

            # If all candidates are already used, leave poi as None
            # This is correct behavior - better to have no POI than duplicate

            # Create block trace
            if enable_extended_trace:
                block_trace = BlockSelectionTrace(
                    day_number=day_number,
                    block_index=block_index,
                    block_type=block_type,
                    block_theme=theme,
                    desired_categories=categories,
                    selected_poi_id=poi.poi_id if poi else None,
                    selected_poi_name=poi.name if poi else None,
                    provider_calls=provider_calls,
                    filter_rules_applied=filter_rules,
                    ranking_trace=ranking_trace,
                    selection_alternatives=selection_alternatives,
                )

            return poi, block_trace

        except Exception as e:
            print(f"⚠️ POI fetch error: {e}")

            # Create error trace if extended trace is enabled
            if enable_extended_trace:
                block_trace = BlockSelectionTrace(
                    day_number=day_number,
                    block_index=block_index,
                    block_type=block_type,
                    block_theme=theme,
                    desired_categories=categories,
                    selected_poi_id=None,
                    selected_poi_name=None,
                    provider_calls=[ProviderCallTrace(
                        provider_name="database",
                        request_params={
                            "city": city,
                            "categories": categories,
                            "budget": budget.value,
                            "limit": 5,
                        },
                        candidates_returned=0,
                        latency_ms=None,
                        status="error",
                        error_message=str(e),
                        sample_candidates=[],
                    )],
                    filter_rules_applied=[],
                    ranking_trace=None,
                    selection_alternatives=[],
                )

            return None, block_trace

    async def _fetch_best_poi(
        self,
        city: str,
        categories: list[str],
        budget: BudgetLevel,
        used_poi_ids: set,
    ) -> Optional[POICandidate]:
        """Fetch the best available POI from database (legacy method)."""
        poi, _ = await self._fetch_best_poi_with_trace(
            city=city,
            categories=categories,
            budget=budget,
            used_poi_ids=used_poi_ids,
            enable_extended_trace=False,
            block_type="activity",
            theme="",
            day_number=1,
            block_index=0,
        )
        return poi

    async def _store_draft(
        self,
        trip_id: UUID,
        skeletons: list[DaySkeleton],
        days: list[ItineraryDay],
        db: AsyncSession,
        created_at: datetime,
    ):
        """Store draft in database."""
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        skeletons_json = [s.model_dump(mode='json') for s in skeletons]
        days_json = [d.model_dump(mode='json') for d in days]

        if itinerary_model:
            itinerary_model.macro_plan = skeletons_json
            itinerary_model.macro_plan_created_at = created_at
            itinerary_model.days = days_json
            itinerary_model.itinerary_created_at = created_at
            itinerary_model.updated_at = created_at
        else:
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                macro_plan=skeletons_json,
                macro_plan_created_at=created_at,
                days=days_json,
                itinerary_created_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        await db.commit()
