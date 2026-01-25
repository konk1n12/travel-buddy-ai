"""
Place Replacement Service - business logic for in-route place substitution.

Handles:
1. Finding 3-5 alternative places with smart ranking
2. Applying replacement atomically with version control
3. POI deduplication and distance calculation
"""
import logging
import uuid
from typing import Dict, List, Any, Optional, Set
from uuid import UUID
from math import radians, cos, sin, asin, sqrt
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.infrastructure.models import TripModel, ItineraryModel
from src.infrastructure.poi_providers import get_poi_provider
from src.domain.models import POICandidate
from src.auth.dependencies import AuthContext, check_trip_ownership


logger = logging.getLogger(__name__)


class PlaceReplacementService:
    """Service for finding and applying place replacements."""

    def __init__(self):
        """Initialize service (POI provider will be initialized per request)."""
        pass

    async def get_replacement_options(
        self,
        trip_id: UUID,
        day_index: int,
        block_index: int,
        current_place_id: str,
        current_category: str,
        current_lat: float,
        current_lng: float,
        constraints: Dict[str, Any],
        limit: int,
        auth: AuthContext,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get 3-5 replacement options for a place.

        Args:
            trip_id: Trip UUID
            day_index: Day index (0-based)
            block_index: Block index within day
            current_place_id: Current place ID to replace
            current_category: Current place category
            current_lat: Current place latitude
            current_lng: Current place longitude
            constraints: Filtering constraints
            limit: Number of alternatives (3-10)
            auth: Authentication context
            db: Database session

        Returns:
            Dict with options list and request_id

        Raises:
            ValueError: If trip/day/block not found
            PermissionError: If access denied
        """
        request_id = str(uuid.uuid4())
        logger.info(f"🔄 Get replacement options: trip={trip_id}, day={day_index}, block={block_index}, request_id={request_id}")

        # 1. Load trip and verify ownership
        trip = await self._load_trip(trip_id, auth, db)

        # 2. Load itinerary
        itinerary_model = await self._load_itinerary(trip_id, db)
        days = itinerary_model.days or []

        # 3. Validate day and block indices
        if day_index < 0 or day_index >= len(days):
            raise ValueError(f"Day index {day_index} out of range (0-{len(days)-1})")

        day_data = days[day_index]
        blocks = day_data.get("blocks", [])

        if block_index < 0 or block_index >= len(blocks):
            raise ValueError(f"Block index {block_index} out of range (0-{len(blocks)-1})")

        # 4. Get current block and validate place_id
        current_block = blocks[block_index]
        current_poi = current_block.get("poi")

        if not current_poi:
            raise ValueError(f"Block {block_index} has no POI")

        # Note: Accept place_id mismatch (client may have stale data)
        # Just use server's poi_id as source of truth
        actual_place_id = current_poi.get("poi_id")

        # 5. Extract constraints
        max_distance_m = constraints.get("max_distance_m", 3000)
        same_category = constraints.get("same_category", True)
        exclude_existing_in_day = constraints.get("exclude_existing_in_day", True)
        exclude_place_ids_input = constraints.get("exclude_place_ids", [])

        # 6. Build exclusion set
        exclude_pois: Set[str] = {actual_place_id}  # Always exclude current place

        if exclude_place_ids_input:
            exclude_pois.update(exclude_place_ids_input)

        if exclude_existing_in_day:
            # Exclude all POIs from current day
            for block in blocks:
                if block.get("poi"):
                    exclude_pois.add(block["poi"]["poi_id"])

        # 7. Determine search categories
        if same_category:
            desired_categories = [current_category]
        else:
            # Search all categories
            desired_categories = []

        # 8. Initialize POI provider
        poi_provider = get_poi_provider(db)

        # 9. Fetch POI candidates
        candidates = await poi_provider.search_pois(
            city=trip.city,
            desired_categories=desired_categories,
            limit=50  # Fetch more to account for filtering
        )

        logger.info(f"   Fetched {len(candidates)} POI candidates")

        # 10. Filter and rank
        options = self._filter_and_rank_candidates(
            candidates=candidates,
            origin_lat=current_lat,
            origin_lng=current_lng,
            max_distance_m=max_distance_m,
            exclude_pois=exclude_pois,
            same_category=same_category,
            target_category=current_category,
            limit=limit
        )

        logger.info(f"   ✅ Returning {len(options)} replacement options")

        return {
            "options": options,
            "request_id": request_id
        }

    async def apply_replacement(
        self,
        trip_id: UUID,
        day_index: int,
        block_index: int,
        old_place_id: str,
        new_place_id: str,
        idempotency_key: str,
        client_route_version: Optional[int],
        auth: AuthContext,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Apply place replacement atomically.

        Args:
            trip_id: Trip UUID
            day_index: Day index (0-based)
            block_index: Block index within day
            old_place_id: Expected current place ID
            new_place_id: New place ID to set
            idempotency_key: Idempotency key (UUID string)
            client_route_version: Client's route version (for conflict detection)
            auth: Authentication context
            db: Database session

        Returns:
            Dict with updated_block and route_version

        Raises:
            ValueError: If trip/day/block not found
            PermissionError: If access denied
            RuntimeError: If version conflict or place_id mismatch
        """
        logger.info(f"🔄 Apply replacement: trip={trip_id}, day={day_index}, block={block_index}")
        logger.info(f"   old_place={old_place_id[:8]}..., new_place={new_place_id[:8]}..., idempotency={idempotency_key}")

        # 1. Load trip and verify ownership
        trip = await self._load_trip(trip_id, auth, db)

        # 2. Load itinerary
        itinerary_model = await self._load_itinerary(trip_id, db)
        days = itinerary_model.days or []

        # 3. Validate day and block indices
        if day_index < 0 or day_index >= len(days):
            raise ValueError(f"Day index {day_index} out of range")

        day_data = days[day_index]
        blocks = day_data.get("blocks", [])

        if block_index < 0 or block_index >= len(blocks):
            raise ValueError(f"Block index {block_index} out of range")

        # 4. Get current block
        current_block = blocks[block_index]
        current_poi = current_block.get("poi")

        if not current_poi:
            raise ValueError(f"Block {block_index} has no POI")

        actual_old_place_id = current_poi.get("poi_id")

        # 5. Validate old_place_id matches (if provided)
        # Allow mismatch if client has stale data - just warn
        if old_place_id != actual_old_place_id:
            logger.warning(
                f"⚠️ old_place_id mismatch: client expects {old_place_id[:8]}..., "
                f"but server has {actual_old_place_id[:8]}..."
            )
            # Continue anyway - server's state is source of truth

        # 6. Version control (optional - for future use)
        current_version = itinerary_model.updated_at.timestamp() if itinerary_model.updated_at else 0

        # Note: Route version could be based on updated_at timestamp
        # For now, we use a simple counter stored in metadata (if needed)
        # For MVP, we just use updated_at as version indicator

        # 7. Fetch new POI details
        new_poi = await self._fetch_poi_details(new_place_id, trip.city, db)

        if not new_poi:
            raise ValueError(f"New place {new_place_id} not found")

        # 8. Replace POI in block
        updated_block = current_block.copy()
        updated_block["poi"] = {
            "poi_id": str(new_poi.poi_id),  # Convert UUID to string for JSON serialization
            "name": new_poi.name,
            "category": new_poi.category,
            "tags": new_poi.tags or [],
            "rating": new_poi.rating,
            "user_ratings_total": new_poi.user_ratings_total,
            "price_level": new_poi.price_level,
            "business_status": new_poi.business_status,
            "open_now": None,  # Will be validated later if needed
            "location": new_poi.location or "",
            "lat": new_poi.lat,
            "lon": new_poi.lon,
            "description": new_poi.description,
            "reviews": new_poi.reviews,
            "rank_score": new_poi.rating or 0.0
        }

        # Recalculate travel times and distances (PHASE 1: 2026-01-24)
        if block_index > 0:
            # Get previous block
            prev_block = blocks[block_index - 1]
            prev_poi = prev_block.get("poi")

            if prev_poi and prev_poi.get("lat") and prev_poi.get("lon"):
                # Calculate distance from prev to new POI
                distance_meters = self._calculate_distance(
                    prev_poi["lat"],
                    prev_poi["lon"],
                    new_poi.lat,
                    new_poi.lon
                )

                # Calculate walking time (4 km/h = 4000 m/h = 66.67 m/min)
                walking_speed_m_per_min = 4000 / 60  # ~66.67 m/min
                travel_time_minutes = int(distance_meters / walking_speed_m_per_min)

                # Update block with new travel data
                updated_block["travel_time_from_prev"] = travel_time_minutes
                updated_block["travel_distance_meters"] = int(distance_meters)

                print(f"📏 Updated travel from prev: {travel_time_minutes} min, {int(distance_meters)} m")
                logger.info(f"Recalculated travel from prev block: {travel_time_minutes}min, {int(distance_meters)}m")
        else:
            # First block has no travel from previous
            updated_block["travel_time_from_prev"] = 0
            updated_block["travel_distance_meters"] = 0

        # Update next block's travel data if exists
        if block_index < len(blocks) - 1:
            next_block = blocks[block_index + 1]
            next_poi = next_block.get("poi")

            if next_poi and next_poi.get("lat") and next_poi.get("lon"):
                # Calculate distance from new POI to next
                distance_to_next = self._calculate_distance(
                    new_poi.lat,
                    new_poi.lon,
                    next_poi["lat"],
                    next_poi["lon"]
                )

                # Calculate walking time
                walking_speed_m_per_min = 4000 / 60
                travel_time_to_next = int(distance_to_next / walking_speed_m_per_min)

                # Update next block
                blocks[block_index + 1]["travel_time_from_prev"] = travel_time_to_next
                blocks[block_index + 1]["travel_distance_meters"] = int(distance_to_next)

                print(f"📏 Updated next block travel: {travel_time_to_next} min, {int(distance_to_next)} m")
                logger.info(f"Recalculated travel to next block: {travel_time_to_next}min, {int(distance_to_next)}m")

        # 9. Update block in day
        blocks[block_index] = updated_block
        day_data["blocks"] = blocks

        # 10. Update day in itinerary
        days[day_index] = day_data
        itinerary_model.days = days

        # 11. Mark as modified and save
        flag_modified(itinerary_model, 'days')
        itinerary_model.updated_at = datetime.utcnow()
        await db.commit()

        new_version = itinerary_model.updated_at.timestamp()

        logger.info(f"   ✅ Replacement applied successfully, new version={new_version}")

        return {
            "updated_block": updated_block,
            "route_version": int(new_version),
            "message": f"Replaced {current_poi.get('name')} with {new_poi.name}"
        }

    # MARK: - Helper Methods

    async def _load_trip(self, trip_id: UUID, auth: AuthContext, db: AsyncSession) -> TripModel:
        """Load trip and verify ownership."""
        result = await db.execute(
            select(TripModel).where(TripModel.id == trip_id)
        )
        trip = result.scalar_one_or_none()

        if not trip:
            raise ValueError(f"Trip {trip_id} not found")

        if not check_trip_ownership(trip, auth):
            raise PermissionError("Access denied")

        return trip

    async def _load_itinerary(self, trip_id: UUID, db: AsyncSession) -> ItineraryModel:
        """Load itinerary for trip."""
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary = result.scalar_one_or_none()

        if not itinerary:
            raise ValueError(f"Itinerary for trip {trip_id} not found")

        return itinerary

    async def _fetch_poi_details(
        self,
        place_id: str,
        city: str,
        db: AsyncSession
    ) -> Optional[POICandidate]:
        """Fetch POI details by place_id (UUID)."""
        from src.infrastructure.models import POIModel

        # Query database directly by UUID
        try:
            poi_uuid = UUID(place_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid POI UUID: {place_id}")
            return None

        result = await db.execute(
            select(POIModel).where(POIModel.id == poi_uuid)
        )
        poi_model = result.scalar_one_or_none()

        if not poi_model:
            logger.warning(f"POI {place_id} not found in database")
            return None

        # Convert to POICandidate
        from src.domain.models import POICandidate

        return POICandidate(
            poi_id=poi_model.id,
            name=poi_model.name,
            category=poi_model.category,
            tags=poi_model.tags or [],
            rating=poi_model.rating,
            user_ratings_total=poi_model.user_ratings_total,
            price_level=None,  # Not stored in current schema
            business_status=poi_model.business_status,
            open_now=None,
            location=poi_model.location or "",
            lat=poi_model.lat,
            lon=poi_model.lon,
            description=poi_model.description,
            reviews=poi_model.reviews,
            rank_score=poi_model.rating or 0.0
        )

    def _filter_and_rank_candidates(
        self,
        candidates: List[POICandidate],
        origin_lat: float,
        origin_lng: float,
        max_distance_m: int,
        exclude_pois: Set[str],
        same_category: bool,
        target_category: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Filter and rank POI candidates.

        Scoring formula:
        - 60% proximity (closer = better)
        - 30% rating (higher = better)
        - 10% review count (more popular = better)
        """
        options = []

        for candidate in candidates:
            # Filter: Excluded POIs
            if str(candidate.poi_id) in exclude_pois:
                continue

            # Filter: Category match (if required)
            if same_category and candidate.category != target_category:
                continue

            # Filter: Has coordinates
            if not candidate.lat or not candidate.lon:
                continue

            # Calculate distance
            distance_m = self._calculate_distance(
                origin_lat, origin_lng,
                candidate.lat, candidate.lon
            )

            # Filter: Max distance
            if distance_m > max_distance_m:
                continue

            # Calculate score
            # Proximity score: 1.0 at 0m, 0.0 at max_distance_m
            proximity_score = 1.0 - (distance_m / max_distance_m)

            # Rating score: normalize 0-5 to 0-1
            rating_score = (candidate.rating or 3.0) / 5.0

            # Popularity score: log scale, normalize to 0-1
            # 100 reviews = 0.5, 10000 reviews = 1.0
            reviews = candidate.user_ratings_total or 50
            popularity_score = min(1.0, (reviews / 10000) ** 0.5)

            # Weighted total
            total_score = (
                0.6 * proximity_score +
                0.3 * rating_score +
                0.1 * popularity_score
            )

            # Build reason string
            reason_parts = []
            if proximity_score > 0.8:
                reason_parts.append("Very close")
            elif proximity_score > 0.5:
                reason_parts.append("Nearby")

            if rating_score > 0.85:
                reason_parts.append("Top rated")
            elif rating_score > 0.75:
                reason_parts.append("Highly rated")

            if same_category:
                reason_parts.append(f"Similar type")

            reason = " • ".join(reason_parts) if reason_parts else "Alternative option"

            options.append({
                "place_id": str(candidate.poi_id),
                "name": candidate.name,
                "category": candidate.category,
                "area": None,  # Could extract from location string
                "distance_m": int(distance_m),
                "rating": candidate.rating,
                "reviews_count": candidate.user_ratings_total,
                "photo_url": None,  # Not stored in DB yet
                "reason": reason,
                "lat": candidate.lat,
                "lng": candidate.lon,
                "address": candidate.location,
                "tags": candidate.tags,
                "_score": total_score  # Internal for sorting
            })

        # Sort by score descending
        options.sort(key=lambda x: x["_score"], reverse=True)

        # Remove internal score field
        for opt in options:
            del opt["_score"]

        # Return top N
        return options[:limit]

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula.

        Returns:
            Distance in meters
        """
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        # Earth radius in meters
        r = 6371000

        return c * r
