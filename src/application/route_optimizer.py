"""
Route & Time Optimizer service.
Generates final itinerary by selecting POIs and assigning concrete times.

Supports two modes:
1. Classic mode (default fallback): Deterministic POI selection + local optimization
2. Smart mode (new): District-based clustering + LLM planning for optimal walking routes

Features:
- Selects best POI for each block
- Optimizes block order within reorderable clusters (minimizes travel)
- Enforces max travel time per hop constraints
- Calculates accurate travel times and distances
- [Smart mode] Groups POIs by districts for logical walking routes
"""
import logging
import json
import itertools
from uuid import UUID
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, Settings
from src.domain.models import ItineraryDay, ItineraryBlock, POICandidate, BlockType, DaySkeleton
from src.domain.schemas import POIPlanBlock, ItineraryResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_agent import (
    POIPreferenceAgent,
    POIPreferenceProfile,
    score_candidate,
    filter_candidates_for_block,
)
from src.infrastructure.travel_time import TravelTimeProvider, TravelLocation, get_travel_time_provider
from src.infrastructure.llm_client import LLMClient, get_poi_selection_llm_client
from src.infrastructure.poi_providers import haversine_distance_km
from src.infrastructure.models import ItineraryModel

logger = logging.getLogger(__name__)


@dataclass
class BlockWithPOI:
    """A block paired with its selected POI for optimization."""
    original_index: int  # Original position in the day
    block_type: BlockType
    start_time: any  # datetime.time
    end_time: any  # datetime.time
    theme: Optional[str]
    poi: Optional[POICandidate]
    is_reorderable: bool = False


class RouteTimeOptimizer:
    """
    Service for generating final itinerary with selected POIs and concrete times.
    Deterministic POI selection and travel time calculation.

    Features:
    - Daily route optimization: reorders blocks to minimize travel
    - Max hop constraint: flags or replaces POIs with excessive travel time
    """

    # Block types that need POIs
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    # Block types that are reorderable (can be swapped to minimize travel)
    # MEAL blocks are NOT reorderable as they have fixed time windows
    REORDERABLE_BLOCK_TYPES = {
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    ROUTE_ORDER_SYSTEM_PROMPT = """You are a route ordering assistant.
Reorder the given blocks to minimize walking distance between consecutive POIs.
You must include every block exactly once and return only JSON."""

    def __init__(
        self,
        travel_time_provider: Optional[TravelTimeProvider] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize Route & Time Optimizer.

        Args:
            travel_time_provider: Travel time provider (defaults to heuristic)
            app_settings: Settings override (for testing)
        """
        self.travel_time_provider = travel_time_provider or get_travel_time_provider()
        self._settings = app_settings or settings
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()
        self._route_order_llm_client: Optional[LLMClient] = None

    def _block_needs_poi(self, block_type: BlockType) -> bool:
        """Check if a block type needs a POI."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

    def _select_poi_for_block(
        self,
        day_number: int,
        block_index: int,
        poi_plan_blocks: list[POIPlanBlock],
        used_poi_ids: set[UUID],
        block_type: BlockType,
        desired_categories: list[str],
        preference_profile: POIPreferenceProfile,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
        day_center_lat: Optional[float] = None,
        day_center_lon: Optional[float] = None,
        candidates_by_block: Optional[dict[tuple[int, int], list[POICandidate]]] = None,
    ) -> Optional[POICandidate]:
        """
        Select the best POI candidate for a block, avoiding duplicates.

        Args:
            day_number: Day number
            block_index: Block index within the day
            poi_plan_blocks: List of all POI plan blocks
            used_poi_ids: Set of POI IDs already selected (for deduplication)

        Returns:
            Selected POICandidate or None if not found
        """
        # Find matching POI plan block
        matching_block = None
        if candidates_by_block is not None:
            matching_candidates = candidates_by_block.get((day_number, block_index), [])
            if not matching_candidates:
                return None
            matching_block = POIPlanBlock(
                day_number=day_number,
                block_index=block_index,
                block_theme="",
                block_type=block_type,
                candidates=matching_candidates,
            )
        else:
            for poi_block in poi_plan_blocks:
                if poi_block.day_number == day_number and poi_block.block_index == block_index:
                    matching_block = poi_block
                    break

            if not matching_block or not matching_block.candidates:
                return None

        # Debug logging
        candidate_info = [(c.name, str(c.poi_id)[:8]) for c in matching_block.candidates[:5]]
        logger.info(
            f"Day {day_number}, Block {block_index}: "
            f"Selecting from {len(matching_block.candidates)} candidates: {candidate_info}"
        )
        logger.info(f"Already used POIs: {len(used_poi_ids)} unique IDs")

        available = [c for c in matching_block.candidates if c.poi_id not in used_poi_ids]
        if not available:
            logger.warning(
                f"❌ All {len(matching_block.candidates)} POI candidates for day {day_number}, "
                f"block {block_index} are already used. Leaving block without POI."
            )
            return None

        available = filter_candidates_for_block(
            candidates=available,
            profile=preference_profile,
            block_type=block_type,
        )

        scored = []
        for candidate in available:
            scored.append((
                score_candidate(
                    candidate=candidate,
                    block_type=block_type,
                    desired_categories=desired_categories,
                    profile=preference_profile,
                    anchor_lat=anchor_lat,
                    anchor_lon=anchor_lon,
                    day_center_lat=day_center_lat,
                    day_center_lon=day_center_lon,
                    distance_weight=self._settings.hotel_anchor_distance_weight,
                ),
                candidate,
            ))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        used_poi_ids.add(selected.poi_id)
        logger.info(
            f"✓ Selected: {selected.name} (ID: {str(selected.poi_id)[:8]}...)"
        )
        return selected

    def _is_block_reorderable(self, block_type: BlockType) -> bool:
        """Check if a block type can be reordered for route optimization."""
        return block_type in self.REORDERABLE_BLOCK_TYPES

    def _calculate_travel_cost_km(
        self,
        poi1: Optional[POICandidate],
        poi2: Optional[POICandidate],
    ) -> float:
        """
        Calculate travel cost between two POIs using haversine distance.
        Uses straight-line distance as a cheap proxy for actual travel cost.

        Returns:
            Distance in km, or 0 if coordinates are missing.
        """
        if poi1 is None or poi2 is None:
            return 0.0
        if poi1.lat is None or poi1.lon is None or poi2.lat is None or poi2.lon is None:
            return 0.0
        return haversine_distance_km(poi1.lat, poi1.lon, poi2.lat, poi2.lon)

    def _calculate_cluster_travel_cost(
        self,
        blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> float:
        """
        Calculate total travel cost for a sequence of blocks.

        Includes:
        - Travel from prev_poi to first block (if prev_poi exists)
        - Travel between all blocks in sequence
        - Travel from last block to next_poi (if next_poi exists)

        Args:
            blocks: Ordered list of blocks in the cluster
            prev_poi: POI from the block before the cluster (or None)
            next_poi: POI from the block after the cluster (or None)

        Returns:
            Total travel cost in km
        """
        if not blocks:
            return 0.0

        total_cost = 0.0

        # Travel from prev_poi to first block
        if prev_poi is not None and blocks[0].poi is not None:
            total_cost += self._calculate_travel_cost_km(prev_poi, blocks[0].poi)

        # Travel between blocks in cluster
        for i in range(len(blocks) - 1):
            total_cost += self._calculate_travel_cost_km(blocks[i].poi, blocks[i + 1].poi)

        # Travel from last block to next_poi
        if next_poi is not None and blocks[-1].poi is not None:
            total_cost += self._calculate_travel_cost_km(blocks[-1].poi, next_poi)

        return total_cost

    def _distance_from_anchor_km(
        self,
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
        poi: Optional[POICandidate],
    ) -> float:
        """Calculate distance between an anchor point and a POI."""
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
        """Find a candidate that improves hop distances while preserving preferences."""
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
            dist_next = self._calculate_travel_cost_km(candidate, next_poi)
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
        current_next = self._calculate_travel_cost_km(current_poi, next_poi)
        current_max = max(current_prev, current_next)

        if best_max_dist is None:
            return None

        if best_max_dist <= max_hop_distance_km or best_max_dist < current_max:
            return best_candidate

        return None

    def _repair_long_hops(
        self,
        blocks: list[BlockWithPOI],
        day_number: int,
        day_skeleton: DaySkeleton,
        candidates_by_block: dict[tuple[int, int], list[POICandidate]],
        used_poi_ids: set[UUID],
        preference_profile: POIPreferenceProfile,
        day_anchor_lat: Optional[float],
        day_anchor_lon: Optional[float],
        day_center_lat: Optional[float],
        day_center_lon: Optional[float],
    ) -> list[BlockWithPOI]:
        """Attempt to replace POIs that create long travel hops."""
        if not self._settings.enable_travel_hop_limit:
            return blocks

        max_hop_distance_km = self._settings.max_hop_distance_km
        if max_hop_distance_km <= 0:
            return blocks

        for _ in range(2):
            prev_poi = None
            prev_anchor_lat = day_anchor_lat
            prev_anchor_lon = day_anchor_lon

            for i, block in enumerate(blocks):
                if block.poi is None or block.poi.lat is None or block.poi.lon is None:
                    if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                        prev_poi = block.poi
                        prev_anchor_lat = block.poi.lat
                        prev_anchor_lon = block.poi.lon
                    continue

                # Find next POI with coordinates
                next_poi = None
                for j in range(i + 1, len(blocks)):
                    candidate_poi = blocks[j].poi
                    if candidate_poi and candidate_poi.lat is not None and candidate_poi.lon is not None:
                        next_poi = candidate_poi
                        break

                dist_prev = self._distance_from_anchor_km(
                    prev_anchor_lat, prev_anchor_lon, block.poi
                )
                dist_next = self._calculate_travel_cost_km(block.poi, next_poi)
                max_dist = max(dist_prev, dist_next)

                if max_dist > max_hop_distance_km:
                    block_candidates = candidates_by_block.get(
                        (day_number, block.original_index), []
                    )
                    skeleton_block = day_skeleton.blocks[block.original_index]
                    replacement = self._find_alternative_poi(
                        candidates=block_candidates,
                        used_poi_ids=used_poi_ids,
                        current_poi=block.poi,
                        block_type=block.block_type,
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

                prev_poi = block.poi
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    prev_anchor_lat = block.poi.lat
                    prev_anchor_lon = block.poi.lon

        return blocks

    def _find_reorderable_clusters(
        self,
        blocks: list[BlockWithPOI],
    ) -> list[tuple[int, int]]:
        """
        Find contiguous sequences of reorderable blocks.

        Returns:
            List of (start_index, end_index) tuples for each cluster.
            Indices are inclusive.
        """
        clusters = []
        i = 0
        while i < len(blocks):
            if blocks[i].is_reorderable and blocks[i].poi is not None:
                # Start of a potential cluster
                start = i
                while i < len(blocks) and blocks[i].is_reorderable and blocks[i].poi is not None:
                    i += 1
                end = i - 1
                # Only consider clusters with 2+ blocks
                if end > start:
                    clusters.append((start, end))
            else:
                i += 1
        return clusters

    def _get_route_order_llm_client(self) -> Optional[LLMClient]:
        """Lazy initialization of LLM client for route ordering."""
        if not self._settings.use_llm_for_route_optimization:
            return None
        if self._route_order_llm_client is not None:
            return self._route_order_llm_client
        try:
            self._route_order_llm_client = get_poi_selection_llm_client(self._settings)
        except Exception as exc:
            logger.warning(f"Route ordering LLM unavailable, using deterministic: {exc}")
            self._route_order_llm_client = None
        return self._route_order_llm_client

    def _build_route_order_prompt(
        self,
        cluster_blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> str:
        """Build prompt for LLM-based cluster ordering."""
        blocks_payload = []
        for block in cluster_blocks:
            if not block.poi or block.poi.lat is None or block.poi.lon is None:
                continue
            blocks_payload.append({
                "block_index": block.original_index,
                "type": block.block_type.value,
                "time": f"{block.start_time} - {block.end_time}",
                "poi_id": str(block.poi.poi_id),
                "name": block.poi.name,
                "lat": round(block.poi.lat, 5),
                "lon": round(block.poi.lon, 5),
                "rating": block.poi.rating,
                "category": block.poi.category,
            })

        anchor_payload = {
            "prev": {
                "lat": round(prev_poi.lat, 5),
                "lon": round(prev_poi.lon, 5),
            } if prev_poi and prev_poi.lat is not None and prev_poi.lon is not None else None,
            "next": {
                "lat": round(next_poi.lat, 5),
                "lon": round(next_poi.lon, 5),
            } if next_poi and next_poi.lat is not None and next_poi.lon is not None else None,
        }

        prompt = f"""Order these blocks to minimize walking distance.

Anchors (optional):
{json.dumps(anchor_payload, indent=2)}

Max hop distance (km): {self._settings.max_hop_distance_km}

Blocks:
```json
{json.dumps(blocks_payload, indent=2)}
```

Return JSON only:
```json
{{"ordered_block_indices": [0, 1, 2]}}
```
"""

        return prompt

    def _parse_route_order_response(
        self,
        response: dict,
        cluster_blocks: list[BlockWithPOI],
    ) -> Optional[list[BlockWithPOI]]:
        """Validate LLM response for ordering."""
        ordered_indices = response.get("ordered_block_indices")
        if not isinstance(ordered_indices, list):
            return None

        cluster_index_set = {block.original_index for block in cluster_blocks}
        if set(ordered_indices) != cluster_index_set:
            return None

        block_map = {block.original_index: block for block in cluster_blocks}
        ordered_blocks = [block_map[idx] for idx in ordered_indices if idx in block_map]
        if len(ordered_blocks) != len(cluster_blocks):
            return None

        return ordered_blocks

    async def _llm_optimize_cluster_order(
        self,
        cluster_blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> Optional[list[BlockWithPOI]]:
        """Use LLM to order a cluster of blocks, with validation."""
        if any(
            block.poi is None or block.poi.lat is None or block.poi.lon is None
            for block in cluster_blocks
        ):
            return None

        llm_client = self._get_route_order_llm_client()
        if llm_client is None:
            return None

        prompt = self._build_route_order_prompt(
            cluster_blocks=cluster_blocks,
            prev_poi=prev_poi,
            next_poi=next_poi,
        )

        try:
            response = await llm_client.generate_structured(
                prompt=prompt,
                system_prompt=self.ROUTE_ORDER_SYSTEM_PROMPT,
                max_tokens=256,
            )
            return self._parse_route_order_response(response, cluster_blocks)
        except Exception as exc:
            logger.warning(f"Route ordering LLM failed, using deterministic: {exc}")
            return None

    def _optimize_cluster_order(
        self,
        blocks: list[BlockWithPOI],
        cluster_start: int,
        cluster_end: int,
        max_cluster_size: int,
    ) -> list[BlockWithPOI]:
        """
        Find the optimal ordering of blocks within a cluster to minimize travel.

        Uses brute-force permutation search for small clusters.
        For clusters larger than max_cluster_size, returns original order.

        Args:
            blocks: Full list of blocks for the day
            cluster_start: Start index of cluster (inclusive)
            cluster_end: End index of cluster (inclusive)
            max_cluster_size: Maximum cluster size to optimize

        Returns:
            New list of blocks with optimized cluster order
        """
        cluster_size = cluster_end - cluster_start + 1

        if cluster_size > max_cluster_size:
            logger.debug(
                f"Cluster size {cluster_size} exceeds max {max_cluster_size}, skipping optimization"
            )
            return blocks

        # Get cluster blocks
        cluster_blocks = blocks[cluster_start:cluster_end + 1]

        # Get surrounding context
        prev_poi = blocks[cluster_start - 1].poi if cluster_start > 0 else None
        next_poi = blocks[cluster_end + 1].poi if cluster_end < len(blocks) - 1 else None

        # Find best permutation
        best_order = cluster_blocks
        best_cost = self._calculate_cluster_travel_cost(cluster_blocks, prev_poi, next_poi)

        for perm in itertools.permutations(cluster_blocks):
            perm_list = list(perm)
            cost = self._calculate_cluster_travel_cost(perm_list, prev_poi, next_poi)
            if cost < best_cost:
                best_cost = cost
                best_order = perm_list

        # Log optimization result
        if best_order != cluster_blocks:
            original_names = [b.poi.name if b.poi else "?" for b in cluster_blocks]
            optimized_names = [b.poi.name if b.poi else "?" for b in best_order]
            logger.info(
                f"Optimized cluster order: {original_names} -> {optimized_names} "
                f"(cost reduced by {self._calculate_cluster_travel_cost(cluster_blocks, prev_poi, next_poi) - best_cost:.1f}km)"
            )

        # Rebuild blocks list with optimized cluster
        result = list(blocks[:cluster_start]) + list(best_order) + list(blocks[cluster_end + 1:])
        return result

    def _optimize_day_route(
        self,
        blocks: list[BlockWithPOI],
    ) -> list[BlockWithPOI]:
        """
        Optimize the order of blocks within a day to minimize travel.

        Identifies reorderable clusters and optimizes each one.

        Args:
            blocks: List of blocks for the day

        Returns:
            List of blocks with optimized order
        """
        if not self._settings.enable_daily_route_optimization:
            return blocks

        max_cluster_size = self._settings.max_optimization_blocks_per_cluster
        result = list(blocks)

        # Find clusters and optimize each one
        # Note: we process from end to start to avoid index shifting issues
        clusters = self._find_reorderable_clusters(result)

        for cluster_start, cluster_end in reversed(clusters):
            result = self._optimize_cluster_order(
                result, cluster_start, cluster_end, max_cluster_size
            )

        return result

    async def _optimize_day_route_llm(
        self,
        blocks: list[BlockWithPOI],
    ) -> list[BlockWithPOI]:
        """Optimize daily route with optional LLM ordering per cluster."""
        if not self._settings.enable_daily_route_optimization:
            return blocks

        max_cluster_size = self._settings.max_optimization_blocks_per_cluster
        result = list(blocks)

        clusters = self._find_reorderable_clusters(result)
        for cluster_start, cluster_end in reversed(clusters):
            cluster_size = cluster_end - cluster_start + 1
            if cluster_size < 2:
                continue

            cluster_blocks = result[cluster_start:cluster_end + 1]
            prev_poi = result[cluster_start - 1].poi if cluster_start > 0 else None
            next_poi = result[cluster_end + 1].poi if cluster_end < len(result) - 1 else None

            llm_order = None
            if (
                self._settings.use_llm_for_route_optimization
                and cluster_size >= 3
                and cluster_size <= max_cluster_size
            ):
                llm_order = await self._llm_optimize_cluster_order(
                    cluster_blocks,
                    prev_poi,
                    next_poi,
                )

            if llm_order:
                llm_cost = self._calculate_cluster_travel_cost(
                    llm_order, prev_poi, next_poi
                )
                deterministic = self._optimize_cluster_order(
                    result, cluster_start, cluster_end, max_cluster_size
                )
                deterministic_cluster = deterministic[cluster_start:cluster_end + 1]
                deterministic_cost = self._calculate_cluster_travel_cost(
                    deterministic_cluster, prev_poi, next_poi
                )

                if llm_cost <= deterministic_cost * 1.25:
                    result = (
                        list(result[:cluster_start])
                        + list(llm_order)
                        + list(result[cluster_end + 1:])
                    )
                else:
                    result = deterministic
            else:
                result = self._optimize_cluster_order(
                    result, cluster_start, cluster_end, max_cluster_size
                )

        return result

    async def generate_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional[POIPreferenceProfile] = None,
    ) -> ItineraryResponse:
        """
        Generate final itinerary for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with final itinerary

        Raises:
            ValueError: If trip not found or required plans missing
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load macro plan
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            raise ValueError(f"No macro plan found for trip {trip_id}. Generate macro plan first.")

        # 2b. Build preference profile if not provided
        if preference_profile is None:
            preference_agent = POIPreferenceAgent(app_settings=self._settings)
            preference_profile = await preference_agent.build_profile(trip_spec)

        # 3. Load POI plan
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.poi_plan:
            raise ValueError(f"No POI plan found for trip {trip_id}. Generate POI plan first.")

        # Parse POI plan blocks
        poi_plan_blocks = [POIPlanBlock(**block_data) for block_data in itinerary_model.poi_plan]
        candidates_by_block = {
            (block.day_number, block.block_index): block.candidates
            for block in poi_plan_blocks
        }

        # Log optimization settings
        if self._settings.enable_daily_route_optimization:
            logger.info(
                f"Route optimization enabled: max_cluster_size={self._settings.max_optimization_blocks_per_cluster}"
            )

        # 4. Generate itinerary days
        itinerary_days = []

        # CRITICAL: Track POIs used across entire trip to prevent duplicates
        trip_used_poi_ids: set[UUID] = set()

        previous_day_last_poi: Optional[POICandidate] = None

        for day_skeleton in macro_plan.days:
            # Phase 1: Build BlockWithPOI objects for all blocks
            blocks_with_poi: list[BlockWithPOI] = []
            selection_anchor = None

            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                selected_poi = None
                if self._block_needs_poi(skeleton_block.block_type):
                    if selection_anchor is None:
                        selection_anchor = (
                            trip_spec.hotel_lat or trip_spec.city_center_lat,
                            trip_spec.hotel_lon or trip_spec.city_center_lon,
                        )
                    anchor_lat = selection_anchor[0] if selection_anchor else None
                    anchor_lon = selection_anchor[1] if selection_anchor else None
                    selected_poi = self._select_poi_for_block(
                        day_skeleton.day_number,
                        block_index,
                        poi_plan_blocks,
                        trip_used_poi_ids,  # Pass trip-level deduplication tracking
                        block_type=skeleton_block.block_type,
                        desired_categories=skeleton_block.desired_categories,
                        preference_profile=preference_profile,
                        anchor_lat=anchor_lat,
                        anchor_lon=anchor_lon,
                        day_center_lat=trip_spec.city_center_lat,
                        day_center_lon=trip_spec.city_center_lon,
                        candidates_by_block=candidates_by_block,
                    )
                    if selected_poi:
                        selection_anchor = (selected_poi.lat, selected_poi.lon)

                is_reorderable = self._is_block_reorderable(skeleton_block.block_type)

                block_with_poi = BlockWithPOI(
                    original_index=block_index,
                    block_type=skeleton_block.block_type,
                    start_time=skeleton_block.start_time,
                    end_time=skeleton_block.end_time,
                    theme=skeleton_block.theme,
                    poi=selected_poi,
                    is_reorderable=is_reorderable,
                )
                blocks_with_poi.append(block_with_poi)

            # Phase 2: Optimize block order within reorderable clusters
            if self._settings.use_llm_for_route_optimization:
                optimized_blocks = await self._optimize_day_route_llm(blocks_with_poi)
            else:
                optimized_blocks = self._optimize_day_route(blocks_with_poi)

            # Phase 2b: Repair long hops by swapping POIs within candidate pools
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

            optimized_blocks = self._repair_long_hops(
                blocks=optimized_blocks,
                day_number=day_skeleton.day_number,
                day_skeleton=day_skeleton,
                candidates_by_block=candidates_by_block,
                used_poi_ids=trip_used_poi_ids,
                preference_profile=preference_profile,
                day_anchor_lat=day_anchor_lat,
                day_anchor_lon=day_anchor_lon,
                day_center_lat=trip_spec.city_center_lat,
                day_center_lon=trip_spec.city_center_lon,
            )

            # Phase 3: Build final itinerary blocks with travel info
            itinerary_blocks = []
            prev_poi = None

            for block_with_poi in optimized_blocks:
                travel_time = 0
                travel_distance = None
                travel_polyline = None

                if block_with_poi.poi is not None:
                    # Calculate travel from previous POI
                    if prev_poi is not None or block_with_poi.poi is not None:
                        origin = TravelLocation.from_poi(prev_poi)
                        destination = TravelLocation.from_poi(block_with_poi.poi)
                        travel_result = await self.travel_time_provider.estimate_travel(
                            origin,
                            destination,
                        )
                        travel_time = travel_result.duration_minutes
                        travel_distance = travel_result.distance_meters
                        travel_polyline = travel_result.polyline

                    prev_poi = block_with_poi.poi

                # Build notes for REST/TRAVEL blocks
                notes = None
                if block_with_poi.block_type == BlockType.REST:
                    notes = block_with_poi.theme or "Rest at hotel"
                elif block_with_poi.block_type == BlockType.TRAVEL:
                    notes = block_with_poi.theme or "Travel time"

                # Check for geo_suboptimal (travel time exceeds threshold)
                geo_suboptimal = False
                if (
                    self._settings.enable_travel_hop_limit
                    and travel_time > self._settings.max_travel_minutes_per_hop
                    and block_with_poi.poi is not None
                ):
                    geo_suboptimal = True
                    logger.warning(
                        f"Geo-suboptimal hop detected: {travel_time} min > "
                        f"{self._settings.max_travel_minutes_per_hop} min threshold "
                        f"(to {block_with_poi.poi.name})"
                    )

                # Create itinerary block
                itinerary_block = ItineraryBlock(
                    block_type=block_with_poi.block_type,
                    start_time=block_with_poi.start_time,
                    end_time=block_with_poi.end_time,
                    poi=block_with_poi.poi,
                    travel_time_from_prev=travel_time,
                    travel_distance_meters=travel_distance,
                    travel_polyline=travel_polyline,
                    notes=notes,
                    geo_suboptimal=geo_suboptimal,
                )
                itinerary_blocks.append(itinerary_block)

            # Create itinerary day
            itinerary_day = ItineraryDay(
                day_number=day_skeleton.day_number,
                date=day_skeleton.date,
                theme=day_skeleton.theme,
                blocks=itinerary_blocks,
            )
            itinerary_days.append(itinerary_day)

            # Track last POI for cross-day anchoring
            for block in reversed(itinerary_blocks):
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    previous_day_last_poi = block.poi
                    break

        # 5. Store in database
        created_at = datetime.utcnow()

        # Convert ItineraryDay list to JSON
        itinerary_json = [day.model_dump(mode='json') for day in itinerary_days]

        # Update existing itinerary record
        itinerary_model.days = itinerary_json
        itinerary_model.itinerary_created_at = created_at
        itinerary_model.updated_at = created_at

        await db.commit()
        await db.refresh(itinerary_model)

        # 6. Return response
        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=created_at.isoformat() + "Z",
        )

    async def get_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[ItineraryResponse]:
        """
        Get stored itinerary for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse if itinerary exists, None otherwise
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.days:
            return None

        # Parse stored JSON back into ItineraryDay objects
        itinerary_days = [ItineraryDay(**day_data) for day_data in itinerary_model.days]

        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=itinerary_model.itinerary_created_at.isoformat() + "Z"
            if itinerary_model.itinerary_created_at else datetime.utcnow().isoformat() + "Z",
        )

    async def generate_smart_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional["POIPreferenceProfile"] = None,
    ) -> ItineraryResponse:
        """
        Generate itinerary using smart district-based routing.

        This method uses geographic clustering and LLM-based district planning
        to create optimal walking routes that stay within neighborhoods.

        Falls back to classic generate_itinerary() on any failure.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with optimized itinerary
        """
        if not self._settings.enable_smart_routing:
            logger.info("Smart routing disabled, using classic method")
            return await self.generate_itinerary(trip_id, db)

        try:
            # Import here to avoid circular imports
            from src.application.smart_route_optimizer import SmartRouteOptimizer

            smart_optimizer = SmartRouteOptimizer(
                travel_time_provider=self.travel_time_provider,
                app_settings=self._settings,
            )

            logger.info(f"Using smart district-based routing for trip {trip_id}")
            return await smart_optimizer.generate_smart_itinerary(
                trip_id,
                db,
                preference_profile=preference_profile,
            )

        except Exception as e:
            logger.warning(
                f"Smart routing failed for trip {trip_id}, falling back to classic: {e}"
            )
            return await self.generate_itinerary(trip_id, db)
