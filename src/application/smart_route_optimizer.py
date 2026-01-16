"""
Smart Route Optimizer - District-based route planning.

This module integrates geographic clustering, LLM district planning,
and intra-cluster routing for optimal walking routes.

Key improvements over linear pipeline:
- POIs are selected WITHIN assigned districts (no city-wide random selection)
- Routes stay in one area for consecutive blocks
- Minimizes travel between districts
- Better user experience (logical walking route)
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, Settings
from src.domain.models import (
    ItineraryDay, ItineraryBlock, POICandidate, BlockType, DaySkeleton
)
from src.domain.schemas import POIPlanBlock, ItineraryResponse, MacroPlanResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.geo_clustering import GeoClusterer, ClusteringResult, District, haversine_distance_km
from src.application.district_planner import DistrictPlanner, DayDistrictPlan
from src.application.poi_agent import (
    POIPreferenceAgent,
    POIPreferenceProfile,
    score_candidate,
    filter_candidates_for_block,
)
from src.infrastructure.travel_time import TravelTimeProvider, TravelLocation, get_travel_time_provider
from src.infrastructure.poi_providers import POIProvider, get_poi_provider
from src.infrastructure.models import ItineraryModel

logger = logging.getLogger(__name__)


class SmartRouteOptimizer:
    """
    Smart route optimizer using district-based planning.

    Pipeline:
    1. Fetch ALL POI candidates for the trip
    2. Cluster POIs into geographic districts
    3. Use LLM to assign districts to time blocks
    4. Select POIs from assigned districts
    5. Optimize intra-district routing
    6. Calculate travel times
    """

    # Block types that need POIs
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    def __init__(
        self,
        travel_time_provider: Optional[TravelTimeProvider] = None,
        poi_provider: Optional[POIProvider] = None,
        app_settings: Optional[Settings] = None,
    ):
        """Initialize smart route optimizer."""
        self.travel_time_provider = travel_time_provider or get_travel_time_provider()
        self.poi_provider = poi_provider
        self._settings = app_settings or settings

        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()

        # Initialize clustering and planning components
        self.geo_clusterer = GeoClusterer(
            cell_size_km=self._settings.cluster_cell_size_km,
            min_pois_per_district=self._settings.min_pois_per_district,
            max_districts=self._settings.max_districts_per_city,
        )
        self.district_planner = DistrictPlanner(
            use_llm=self._settings.use_llm_for_district_planning,
            app_settings=self._settings,
        )

    def _block_needs_poi(self, block_type: BlockType) -> bool:
        """Check if a block type needs a POI."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

    def _build_district_summaries(
        self,
        clustering_result: ClusteringResult,
        macro_plan: MacroPlanResponse,
        preference_profile: POIPreferenceProfile,
    ) -> list[dict]:
        """Build compact district summaries with preference-aware scores."""
        needed_categories = set()
        for day in macro_plan.days:
            for block in day.blocks:
                if self._block_needs_poi(block.block_type):
                    for category in block.desired_categories or []:
                        needed_categories.add(category)

        summaries = []
        keyword_signals = set(preference_profile.must_include_keywords) | set(preference_profile.tag_boosts.keys())

        for district in clustering_result.districts.values():
            if needed_categories and not district.has_category(list(needed_categories)):
                continue

            candidates = list(district.pois)

            scored = []
            for candidate in candidates:
                scored.append(score_candidate(
                    candidate=candidate,
                    block_type=BlockType.ACTIVITY,
                    desired_categories=list(needed_categories),
                    profile=preference_profile,
                    anchor_lat=district.center_lat,
                    anchor_lon=district.center_lon,
                    distance_weight=0.2,
                ))

            scored.sort(reverse=True)
            top_scores = scored[:5]
            preference_score = round(sum(top_scores) / len(top_scores), 2) if top_scores else 0.0

            summary = district.to_llm_summary()
            summary["preference_score"] = preference_score
            summary["category_coverage"] = [
                category for category in sorted(needed_categories)
                if district.has_category([category])
            ]

            if keyword_signals:
                hits = []
                for keyword in keyword_signals:
                    for poi in district.pois:
                        # Defensive check for correct type
                        if not hasattr(poi, 'name'):
                            logger.error(f"❌ BUG in district.pois: poi is {type(poi)}, not POICandidate!")
                            continue
                        haystack = f"{poi.name} {' '.join(poi.tags or [])}".lower()
                        if keyword in haystack:
                            hits.append(keyword)
                            break
                summary["preference_signals"] = hits[:5]

            summaries.append(summary)

        return summaries

    async def _fetch_all_pois_for_trip(
        self,
        macro_plan: MacroPlanResponse,
        trip_spec,
        db: AsyncSession,
        preference_profile: Optional[POIPreferenceProfile] = None,
    ) -> list[POICandidate]:
        """
        Fetch ALL POI candidates needed for the entire trip.

        Collects unique categories from all blocks and fetches
        a large pool of POIs for clustering.
        """
        # Collect all unique categories needed
        all_categories = set()
        for day in macro_plan.days:
            for block in day.blocks:
                if self._block_needs_poi(block.block_type):
                    for cat in (block.desired_categories or []):
                        all_categories.add(cat)

        logger.info(f"Fetching POIs for {len(all_categories)} categories: {sorted(all_categories)}")

        # Initialize POI provider if needed
        if not self.poi_provider:
            self.poi_provider = get_poi_provider(db)

        # Fetch POIs for each category
        all_pois: dict[UUID, POICandidate] = {}  # Deduplicate by ID
        min_rating = self._settings.smart_routing_min_rating
        if preference_profile:
            min_rating = max(min_rating, preference_profile.min_rating)

        meal_categories = {"restaurant", "cafe", "bar", "bakery", "food"}
        search_keywords = preference_profile.search_keywords if preference_profile else []

        for category in all_categories:
            try:
                candidates = await self.poi_provider.search_pois(
                    city=trip_spec.city,
                    desired_categories=[category],
                    budget=trip_spec.budget,
                    limit=100,  # Large pool for clustering (increased for better variety)
                    city_center_lat=trip_spec.city_center_lat,
                    city_center_lon=trip_spec.city_center_lon,
                    max_radius_km=50.0,
                    search_keywords=search_keywords if category in meal_categories else None,
                )

                # Filter by minimum rating
                filtered = [c for c in candidates if (c.rating or 0) >= min_rating]

                # If too few high-rated, include lower-rated as fallback
                if len(filtered) < 10:
                    filtered = candidates[:30]  # Take top 30 by rank_score

                for poi in filtered:
                    if poi.poi_id not in all_pois:
                        all_pois[poi.poi_id] = poi

                logger.debug(f"Category '{category}': {len(filtered)} POIs")

            except Exception as e:
                logger.warning(f"Failed to fetch POIs for category '{category}': {e}")

        logger.info(f"Total unique POIs fetched: {len(all_pois)}")
        return list(all_pois.values())

    def _select_poi_from_district(
        self,
        district: District,
        skeleton_block,
        used_poi_ids: set[UUID],
        clustering_result: ClusteringResult,
        preference_profile: POIPreferenceProfile,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
    ) -> tuple[Optional[POICandidate], list[POICandidate]]:
        """
        Select best POI from a district for a block.

        Strategy:
        1. Get POIs matching categories from assigned district
        2. If insufficient, expand to adjacent districts
        3. Select best by rating (maintaining quality >= 4.5)
        """
        required_categories = skeleton_block.desired_categories or []
        min_rating = max(self._settings.smart_routing_min_rating, preference_profile.min_rating)
        min_candidates = self._settings.district_poi_min_candidates

        # Try assigned district first
        candidates = district.get_pois_by_category(
            categories=required_categories,
            min_rating=min_rating,
            exclude_ids=used_poi_ids,
        )

        candidates = filter_candidates_for_block(
            candidates=candidates,
            profile=preference_profile,
            block_type=skeleton_block.block_type,
        )

        logger.debug(
            f"District {district.district_id}: {len(candidates)} candidates "
            f"for categories {required_categories}"
        )

        # If insufficient candidates, expand search
        if len(candidates) < min_candidates:
            logger.info(
                f"District {district.district_id} has only {len(candidates)} candidates, "
                "expanding to nearby districts"
            )

            # Get nearby districts sorted by distance
            nearby = clustering_result.get_districts_sorted_by_distance(
                district.center_lat, district.center_lon
            )

            for nearby_district, distance in nearby[1:4]:  # Skip self, check next 3
                additional = nearby_district.get_pois_by_category(
                    categories=required_categories,
                    min_rating=min_rating,
                    exclude_ids=used_poi_ids,
                )
                candidates.extend(filter_candidates_for_block(
                    candidates=additional,
                    profile=preference_profile,
                    block_type=skeleton_block.block_type,
                ))

                if len(candidates) >= min_candidates:
                    break

        # If still no candidates with min_rating, lower threshold
        if not candidates:
            logger.warning(
                f"No candidates with rating >= {min_rating}, "
                "trying with lower threshold"
            )
            candidates = district.get_pois_by_category(
                categories=required_categories,
                min_rating=4.0,
                exclude_ids=used_poi_ids,
            )
            candidates = filter_candidates_for_block(
                candidates=candidates,
                profile=preference_profile,
                block_type=skeleton_block.block_type,
            )

        if not candidates:
            logger.warning(
                f"No suitable POI found in district {district.district_id} "
                f"for categories {required_categories}"
            )
            return None, []

        # Select best candidate using preference-aware scoring
        scored_candidates = []
        for candidate in candidates:
            scored_candidates.append((
                score_candidate(
                    candidate=candidate,
                    block_type=skeleton_block.block_type,
                    desired_categories=required_categories,
                    profile=preference_profile,
                    anchor_lat=anchor_lat,
                    anchor_lon=anchor_lon,
                    day_center_lat=district.center_lat,
                    day_center_lon=district.center_lon,
                    distance_weight=self._settings.hotel_anchor_distance_weight,
                ),
                candidate,
            ))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        ordered_candidates = [candidate for _, candidate in scored_candidates]
        selected = ordered_candidates[0]

        # Defensive check for correct type
        if not hasattr(selected, 'name'):
            logger.error(
                f"❌ BUG: selected object is {type(selected)}, not POICandidate! "
                f"Has attributes: {dir(selected)}"
            )
            # Try to find the first valid POICandidate
            for cand in ordered_candidates:
                if hasattr(cand, 'name'):
                    selected = cand
                    break
            else:
                # If no valid candidate found, return None
                logger.error("No valid POICandidate found in ordered_candidates!")
                return None, []

        logger.info(
            f"Selected '{selected.name}' (rating: {selected.rating}) "
            f"from district {district.district_id}"
        )
        return selected, ordered_candidates

    def _optimize_intra_district_route(
        self,
        blocks: list[tuple[int, ItineraryBlock]],
        start_lat: Optional[float] = None,
        start_lon: Optional[float] = None,
    ) -> list[tuple[int, ItineraryBlock]]:
        """
        Optimize route within a district using nearest-neighbor.

        Args:
            blocks: List of (original_index, ItineraryBlock) tuples
            start_lat: Starting point latitude (e.g., previous POI or hotel)
            start_lon: Starting point longitude

        Returns:
            Reordered blocks for minimal walking
        """
        if len(blocks) <= 2:
            return blocks

        reorderable_types = {BlockType.ACTIVITY, BlockType.NIGHTLIFE}
        result: list[tuple[int, ItineraryBlock]] = []
        i = 0
        anchor_lat = start_lat
        anchor_lon = start_lon

        while i < len(blocks):
            idx, block = blocks[i]

            is_reorderable = block.block_type in reorderable_types
            has_coords = block.poi and block.poi.lat is not None and block.poi.lon is not None

            if not is_reorderable or not has_coords:
                result.append((idx, block))
                if has_coords:
                    anchor_lat = block.poi.lat
                    anchor_lon = block.poi.lon
                i += 1
                continue

            # Collect contiguous reorderable segment with coordinates
            segment: list[tuple[int, ItineraryBlock]] = []
            while i < len(blocks):
                seg_idx, seg_block = blocks[i]
                seg_reorderable = seg_block.block_type in reorderable_types
                seg_coords = seg_block.poi and seg_block.poi.lat is not None and seg_block.poi.lon is not None
                if not seg_reorderable or not seg_coords:
                    break
                segment.append((seg_idx, seg_block))
                i += 1

            if len(segment) <= 1:
                result.extend(segment)
                if segment and segment[0][1].poi:
                    anchor_lat = segment[0][1].poi.lat
                    anchor_lon = segment[0][1].poi.lon
                continue

            remaining = list(segment)
            if anchor_lat is not None and anchor_lon is not None:
                remaining.sort(
                    key=lambda x: haversine_distance_km(
                        anchor_lat, anchor_lon, x[1].poi.lat, x[1].poi.lon
                    )
                )

            current = remaining.pop(0)
            optimized = [current]

            while remaining:
                current_poi = current[1].poi
                remaining.sort(
                    key=lambda x: haversine_distance_km(
                        current_poi.lat, current_poi.lon,
                        x[1].poi.lat, x[1].poi.lon
                    )
                )
                current = remaining.pop(0)
                optimized.append(current)

            result.extend(optimized)
            last_poi = optimized[-1][1].poi
            if last_poi:
                anchor_lat = last_poi.lat
                anchor_lon = last_poi.lon

        return result

    def _distance_from_anchor_km(
        self,
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
        poi: Optional[POICandidate],
    ) -> float:
        if poi is None or poi.lat is None or poi.lon is None:
            return 0.0
        if anchor_lat is None or anchor_lon is None:
            return 0.0
        return haversine_distance_km(anchor_lat, anchor_lon, poi.lat, poi.lon)

    def _find_alternative_poi(
        self,
        candidates: list[POICandidate],
        used_poi_ids: set[UUID],
        current_poi: POICandidate,
        block_type: BlockType,
        desired_categories: list[str],
        preference_profile: POIPreferenceProfile,
        prev_anchor_lat: Optional[float],
        prev_anchor_lon: Optional[float],
        next_poi: Optional[POICandidate],
        day_center_lat: Optional[float],
        day_center_lon: Optional[float],
        max_hop_distance_km: float,
    ) -> Optional[POICandidate]:
        best_candidate = None
        best_score = float("-inf")
        best_max_dist = None

        for candidate in candidates:
            if candidate.poi_id in used_poi_ids and candidate.poi_id != current_poi.poi_id:
                continue
            if candidate.lat is None or candidate.lon is None:
                continue

            dist_prev = self._distance_from_anchor_km(
                prev_anchor_lat, prev_anchor_lon, candidate
            )
            dist_next = haversine_distance_km(
                candidate.lat, candidate.lon,
                next_poi.lat, next_poi.lon
            ) if next_poi and next_poi.lat is not None and next_poi.lon is not None else 0.0

            max_dist = max(dist_prev, dist_next)

            base_score = score_candidate(
                candidate=candidate,
                block_type=block_type,
                desired_categories=desired_categories,
                profile=preference_profile,
                anchor_lat=prev_anchor_lat,
                anchor_lon=prev_anchor_lon,
                day_center_lat=day_center_lat,
                day_center_lon=day_center_lon,
                distance_weight=self._settings.hotel_anchor_distance_weight,
            )

            score = base_score - (dist_next * self._settings.hotel_anchor_distance_weight)
            if max_dist > max_hop_distance_km:
                score -= (max_dist - max_hop_distance_km) * 2.0

            if score > best_score:
                best_candidate = candidate
                best_score = score
                best_max_dist = max_dist

        if best_candidate is None:
            return None

        current_prev = self._distance_from_anchor_km(
            prev_anchor_lat, prev_anchor_lon, current_poi
        )
        current_next = haversine_distance_km(
            current_poi.lat, current_poi.lon,
            next_poi.lat, next_poi.lon
        ) if next_poi and next_poi.lat is not None and next_poi.lon is not None else 0.0
        current_max = max(current_prev, current_next)

        if best_max_dist is None:
            return None

        if best_max_dist <= max_hop_distance_km or best_max_dist < current_max:
            return best_candidate

        return None

    def _repair_long_hops(
        self,
        blocks_with_index: list[tuple[int, ItineraryBlock]],
        day_skeleton: DaySkeleton,
        candidates_by_block: dict[int, list[POICandidate]],
        used_poi_ids: set[UUID],
        preference_profile: POIPreferenceProfile,
        day_anchor_lat: Optional[float],
        day_anchor_lon: Optional[float],
        day_center_lat: Optional[float],
        day_center_lon: Optional[float],
    ) -> list[tuple[int, ItineraryBlock]]:
        if not self._settings.enable_travel_hop_limit:
            return blocks_with_index

        max_hop_distance_km = self._settings.max_hop_distance_km
        if max_hop_distance_km <= 0:
            return blocks_with_index

        for _ in range(2):
            prev_anchor_lat = day_anchor_lat
            prev_anchor_lon = day_anchor_lon

            for i, (block_index, block) in enumerate(blocks_with_index):
                if block.poi is None or block.poi.lat is None or block.poi.lon is None:
                    if block.poi:
                        prev_anchor_lat = block.poi.lat
                        prev_anchor_lon = block.poi.lon
                    continue

                next_poi = None
                for j in range(i + 1, len(blocks_with_index)):
                    candidate_poi = blocks_with_index[j][1].poi
                    if candidate_poi and candidate_poi.lat is not None and candidate_poi.lon is not None:
                        next_poi = candidate_poi
                        break

                dist_prev = self._distance_from_anchor_km(
                    prev_anchor_lat, prev_anchor_lon, block.poi
                )
                dist_next = haversine_distance_km(
                    block.poi.lat, block.poi.lon,
                    next_poi.lat, next_poi.lon
                ) if next_poi and next_poi.lat is not None and next_poi.lon is not None else 0.0
                max_dist = max(dist_prev, dist_next)

                if max_dist > max_hop_distance_km:
                    candidates = candidates_by_block.get(block_index, [])
                    if not candidates:
                        continue

                    skeleton_block = day_skeleton.blocks[block_index]
                    candidates = filter_candidates_for_block(
                        candidates=candidates,
                        profile=preference_profile,
                        block_type=skeleton_block.block_type,
                    )

                    replacement = self._find_alternative_poi(
                        candidates=candidates,
                        used_poi_ids=used_poi_ids,
                        current_poi=block.poi,
                        block_type=skeleton_block.block_type,
                        desired_categories=skeleton_block.desired_categories,
                        preference_profile=preference_profile,
                        prev_anchor_lat=prev_anchor_lat,
                        prev_anchor_lon=prev_anchor_lon,
                        next_poi=next_poi,
                        day_center_lat=day_center_lat,
                        day_center_lon=day_center_lon,
                        max_hop_distance_km=max_hop_distance_km,
                    )

                    if replacement and replacement.poi_id != block.poi.poi_id:
                        logger.info(
                            f"Replacing POI to reduce hop distance: "
                            f"{block.poi.name} -> {replacement.name}"
                        )
                        used_poi_ids.discard(block.poi.poi_id)
                        used_poi_ids.add(replacement.poi_id)
                        block.poi = replacement

                prev_anchor_lat = block.poi.lat
                prev_anchor_lon = block.poi.lon

        return blocks_with_index

    async def generate_smart_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional[POIPreferenceProfile] = None,
    ) -> ItineraryResponse:
        """
        Generate itinerary using smart district-based routing.

        Steps:
        1. Load trip spec and macro plan
        2. Fetch all POIs and cluster into districts
        3. Plan district assignments for each day
        4. Select POIs from assigned districts
        5. Optimize intra-district routes
        6. Calculate travel times
        7. Store and return itinerary
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(
            trip_id,
            db,
            refresh_city_photo=True,
        )
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load macro plan
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            raise ValueError(f"No macro plan found for trip {trip_id}")

        # 2b. Build preference profile (POI agent)
        poi_agent = POIPreferenceAgent(app_settings=self._settings)
        if preference_profile is None:
            preference_profile = await poi_agent.build_profile(trip_spec)

        preference_summary = {
            "must_include_keywords": preference_profile.must_include_keywords,
            "avoid_keywords": preference_profile.avoid_keywords,
            "search_keywords": preference_profile.search_keywords,
            "category_boosts": preference_profile.category_boosts,
            "tag_boosts": preference_profile.tag_boosts,
            "min_rating": preference_profile.min_rating,
            "preferred_price_levels": preference_profile.preferred_price_levels,
        }

        logger.info(f"Starting smart route optimization for trip {trip_id}")

        # 3. Fetch all POIs for the trip
        all_pois = await self._fetch_all_pois_for_trip(
            macro_plan,
            trip_spec,
            db,
            preference_profile=preference_profile,
        )

        if not all_pois:
            raise ValueError("No POIs found for clustering")

        # 4. Cluster POIs into districts
        clustering_result = self.geo_clusterer.cluster_pois(
            pois=all_pois,
            hotel_lat=trip_spec.hotel_lat,
            hotel_lon=trip_spec.hotel_lon,
            city_center_lat=trip_spec.city_center_lat,
            city_center_lon=trip_spec.city_center_lon,
        )

        district_summaries = self._build_district_summaries(
            clustering_result=clustering_result,
            macro_plan=macro_plan,
            preference_profile=preference_profile,
        )

        logger.info(
            f"Clustered {len(all_pois)} POIs into {len(clustering_result.districts)} districts: "
            f"{[d.name for d in clustering_result.districts.values()]}"
        )

        # 5. Generate itinerary days
        itinerary_days = []
        trip_used_poi_ids: set[UUID] = set()
        previous_day_last_poi: Optional[POICandidate] = None

        for day_skeleton in macro_plan.days:
            # 5a. Plan district assignments for the day
            previous_day_anchor = None
            previous_day_district_id = None
            if previous_day_last_poi and previous_day_last_poi.lat is not None and previous_day_last_poi.lon is not None:
                previous_day_anchor = {
                    "lat": round(previous_day_last_poi.lat, 5),
                    "lon": round(previous_day_last_poi.lon, 5),
                }
                nearest = clustering_result.get_nearest_district(
                    previous_day_last_poi.lat,
                    previous_day_last_poi.lon,
                )
                if nearest:
                    previous_day_district_id = nearest.district_id

            district_plan = await self.district_planner.plan_districts(
                day_skeleton=day_skeleton,
                clustering_result=clustering_result,
                city=trip_spec.city,
                district_summaries=district_summaries,
                preference_summary=preference_summary,
                previous_day_anchor=previous_day_anchor,
                previous_day_district_id=previous_day_district_id,
            )

            logger.info(
                f"Day {day_skeleton.day_number} district plan: "
                f"{[a.district_id for a in district_plan.assignments]}"
            )

            # 5b. Select POIs from assigned districts
            itinerary_blocks_with_index: list[tuple[int, ItineraryBlock]] = []
            prev_poi = None
            selection_anchor = None
            block_candidate_pool: dict[int, list[POICandidate]] = {}

            # Group blocks by consecutive district for intra-cluster optimization
            current_district_blocks: list[tuple[int, ItineraryBlock]] = []
            current_district_id = None

            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                assigned_district_id = district_plan.get_district_for_block(block_index)
                assigned_district = clustering_result.get_district(assigned_district_id)

                # Select POI if needed
                selected_poi = None
                candidate_pool: list[POICandidate] = []
                if self._block_needs_poi(skeleton_block.block_type):
                    if assigned_district:
                        if selection_anchor is None:
                            selection_anchor = (
                                trip_spec.hotel_lat or trip_spec.city_center_lat,
                                trip_spec.hotel_lon or trip_spec.city_center_lon,
                            )
                        anchor_lat = selection_anchor[0] if selection_anchor else None
                        anchor_lon = selection_anchor[1] if selection_anchor else None
                        selected_poi, candidate_pool = self._select_poi_from_district(
                            district=assigned_district,
                            skeleton_block=skeleton_block,
                            used_poi_ids=trip_used_poi_ids,
                            clustering_result=clustering_result,
                            preference_profile=preference_profile,
                            anchor_lat=anchor_lat,
                            anchor_lon=anchor_lon,
                        )
                        block_candidate_pool[block_index] = candidate_pool
                        if selected_poi:
                            trip_used_poi_ids.add(selected_poi.poi_id)
                            selection_anchor = (selected_poi.lat, selected_poi.lon)
                    else:
                        block_candidate_pool[block_index] = []
                else:
                    block_candidate_pool[block_index] = []

                # Build notes for non-POI blocks
                notes = None
                if skeleton_block.block_type == BlockType.REST:
                    notes = skeleton_block.theme or "Rest at hotel"
                elif skeleton_block.block_type == BlockType.TRAVEL:
                    notes = skeleton_block.theme or "Travel time"

                # Create block (travel time calculated later)
                itinerary_block = ItineraryBlock(
                    block_type=skeleton_block.block_type,
                    start_time=skeleton_block.start_time,
                    end_time=skeleton_block.end_time,
                    poi=selected_poi,
                    travel_time_from_prev=0,
                    travel_distance_meters=None,
                    travel_polyline=None,
                    notes=notes,
                    geo_suboptimal=False,
                )

                # Track for intra-district optimization
                if assigned_district_id != current_district_id:
                    # New district - optimize previous cluster and add to result
                    if current_district_blocks:
                        # Get start point for optimization
                        start_lat = prev_poi.lat if prev_poi else trip_spec.hotel_lat
                        start_lon = prev_poi.lon if prev_poi else trip_spec.hotel_lon

                        optimized = self._optimize_intra_district_route(
                            current_district_blocks,
                            start_lat, start_lon
                        )

                        for block_idx, block in optimized:
                            itinerary_blocks_with_index.append((block_idx, block))
                            if block.poi:
                                prev_poi = block.poi

                    current_district_blocks = [(block_index, itinerary_block)]
                    current_district_id = assigned_district_id
                else:
                    current_district_blocks.append((block_index, itinerary_block))

            # Don't forget last cluster
            if current_district_blocks:
                start_lat = prev_poi.lat if prev_poi else trip_spec.hotel_lat
                start_lon = prev_poi.lon if prev_poi else trip_spec.hotel_lon

                optimized = self._optimize_intra_district_route(
                    current_district_blocks,
                    start_lat, start_lon
                )

                for block_idx, block in optimized:
                    itinerary_blocks_with_index.append((block_idx, block))

            day_anchor_lat = None
            day_anchor_lon = None
            if previous_day_last_poi and previous_day_last_poi.lat is not None and previous_day_last_poi.lon is not None:
                day_anchor_lat = previous_day_last_poi.lat
                day_anchor_lon = previous_day_last_poi.lon
            elif trip_spec.hotel_lat is not None and trip_spec.hotel_lon is not None:
                day_anchor_lat = trip_spec.hotel_lat
                day_anchor_lon = trip_spec.hotel_lon
            elif trip_spec.city_center_lat is not None and trip_spec.city_center_lon is not None:
                day_anchor_lat = trip_spec.city_center_lat
                day_anchor_lon = trip_spec.city_center_lon

            itinerary_blocks_with_index = self._repair_long_hops(
                blocks_with_index=itinerary_blocks_with_index,
                day_skeleton=day_skeleton,
                candidates_by_block=block_candidate_pool,
                used_poi_ids=trip_used_poi_ids,
                preference_profile=preference_profile,
                day_anchor_lat=day_anchor_lat,
                day_anchor_lon=day_anchor_lon,
                day_center_lat=trip_spec.city_center_lat,
                day_center_lon=trip_spec.city_center_lon,
            )

            itinerary_blocks = [block for _, block in itinerary_blocks_with_index]

            # 5c. Calculate travel times
            prev_poi = None
            for block in itinerary_blocks:
                if block.poi:
                    if prev_poi:
                        origin = TravelLocation.from_poi(prev_poi)
                        destination = TravelLocation.from_poi(block.poi)
                        travel_result = await self.travel_time_provider.estimate_travel(
                            origin, destination
                        )
                        block.travel_time_from_prev = travel_result.duration_minutes
                        block.travel_distance_meters = travel_result.distance_meters
                        block.travel_polyline = travel_result.polyline

                        # Check for geo_suboptimal
                        if (
                            self._settings.enable_travel_hop_limit
                            and block.travel_time_from_prev > self._settings.max_travel_minutes_per_hop
                        ):
                            block.geo_suboptimal = True
                            logger.warning(
                                f"Geo-suboptimal hop: {block.travel_time_from_prev} min > "
                                f"{self._settings.max_travel_minutes_per_hop} min"
                            )

                    prev_poi = block.poi

            for block in reversed(itinerary_blocks):
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    previous_day_last_poi = block.poi
                    break

            # Create itinerary day
            itinerary_day = ItineraryDay(
                day_number=day_skeleton.day_number,
                date=day_skeleton.date,
                theme=day_skeleton.theme,
                blocks=itinerary_blocks,
            )
            itinerary_days.append(itinerary_day)

        # 6. Store in database
        created_at = datetime.utcnow()
        itinerary_json = [day.model_dump(mode='json') for day in itinerary_days]

        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if itinerary_model:
            itinerary_model.days = itinerary_json
            itinerary_model.itinerary_created_at = created_at
            itinerary_model.updated_at = created_at
        else:
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                days=itinerary_json,
                itinerary_created_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        await db.commit()
        await db.refresh(itinerary_model)

        # 7. Log summary
        total_distance = sum(
            block.travel_distance_meters or 0
            for day in itinerary_days
            for block in day.blocks
        )
        total_travel_time = sum(
            block.travel_time_from_prev or 0
            for day in itinerary_days
            for block in day.blocks
        )
        geo_suboptimal_count = sum(
            1 for day in itinerary_days
            for block in day.blocks
            if block.geo_suboptimal
        )

        logger.info(
            f"Smart itinerary generated: "
            f"{len(itinerary_days)} days, "
            f"{total_distance / 1000:.1f}km total distance, "
            f"{total_travel_time} min total travel, "
            f"{geo_suboptimal_count} geo-suboptimal hops"
        )

        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=created_at.isoformat() + "Z",
            city_photo_reference=trip_spec.city_photo_reference,
        )
