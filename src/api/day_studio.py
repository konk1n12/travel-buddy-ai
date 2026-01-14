"""
Day Studio API endpoints for AI-powered day editing.
"""
import logging
from uuid import UUID
from typing import Optional, List
from datetime import datetime, time
import hashlib
import json

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel, ItineraryModel
from src.auth.dependencies import get_auth_context, AuthContext, check_trip_ownership
from src.domain.models import ItineraryDay, ItineraryBlock, POICandidate
from src.application.day_editor import DayEditor, DayChange, ChangeType


router = APIRouter(prefix="/trips", tags=["day-studio"])


# MARK: - Request/Response Schemas

class StudioPlaceDTO(BaseModel):
    """Place data for studio view."""
    id: str
    name: str
    latitude: float
    longitude: float
    time_start: str
    time_end: str
    category: str
    rating: Optional[float] = None
    price_level: Optional[int] = None
    photo_url: Optional[str] = None
    address: Optional[str] = None


class WishMessageDTO(BaseModel):
    """Wish message in the chat."""
    id: str
    role: str  # "user" or "assistant"
    text: str
    created_at: str


class DayStudioDataDTO(BaseModel):
    """Day data for studio."""
    places: List[StudioPlaceDTO]
    wishes: List[WishMessageDTO] = Field(default_factory=list)


class DaySettingsDTO(BaseModel):
    """Day settings."""
    tempo: str = "medium"  # low, medium, high
    start_time: str = "08:00"
    end_time: str = "18:00"
    budget: str = "medium"  # low, medium, high


class DayMetricsDTO(BaseModel):
    """Calculated day metrics."""
    distance_km: float = 0.0
    steps_estimate: int = 0
    places_count: int = 0
    walking_time_minutes: int = 0


class DaySuggestionDTO(BaseModel):
    """AI suggestion for the day."""
    type: str
    title: str
    description: Optional[str] = None


class DayStudioResponse(BaseModel):
    """Response for GET /trip/{trip_id}/day/{day_id}/studio."""
    day: DayStudioDataDTO
    settings: DaySettingsDTO
    preset: Optional[str] = None
    ai_summary: str
    metrics: DayMetricsDTO
    suggestions: Optional[List[DaySuggestionDTO]] = None
    revision: int


# MARK: - Change Types

class PlacementDTO(BaseModel):
    """Placement specification for adding a place."""
    type: str = "auto"  # auto, in_slot, at_time
    slot_index: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None


class DayChangeDataDTO(BaseModel):
    """Data for a single change."""
    # UpdateSettings
    tempo: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    budget: Optional[str] = None

    # SetPreset
    preset: Optional[str] = None

    # AddPlace / RemovePlace
    place_id: Optional[str] = None
    placement: Optional[PlacementDTO] = None

    # ReplacePlace
    from_place_id: Optional[str] = None
    to_place_id: Optional[str] = None

    # AddWishMessage
    text: Optional[str] = None


class DayChangeDTO(BaseModel):
    """A single change to apply."""
    type: str  # update_settings, set_preset, add_place, replace_place, remove_place, add_wish_message
    data: DayChangeDataDTO


class ApplyChangesRequest(BaseModel):
    """Request for POST /trip/{trip_id}/day/{day_id}/apply_changes."""
    base_revision: int
    changes: List[DayChangeDTO]


# MARK: - Place Search

class PlaceSearchRequest(BaseModel):
    """Request for POST /places/search."""
    query: str
    city: str
    limit: Optional[int] = 10


class PlaceSearchResultDTO(BaseModel):
    """A single search result."""
    place_id: str
    name: str
    category: str
    rating: Optional[float] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PlaceSearchResponse(BaseModel):
    """Response for POST /places/search."""
    results: List[PlaceSearchResultDTO]


# MARK: - Endpoints

@router.get(
    "/{trip_id}/day/{day_id}/studio",
    response_model=DayStudioResponse,
    summary="Get day studio data",
    description="Get all data needed for the AI Studio day editing screen."
)
async def get_day_studio(
    trip_id: UUID,
    day_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> DayStudioResponse:
    """
    Get day studio data including places, settings, AI summary, and metrics.

    Args:
        trip_id: UUID of the trip
        day_id: Day number (1-indexed)

    Returns:
        DayStudioResponse with all studio data
    """
    # Verify trip exists and user has access
    trip_result = await db.execute(
        select(TripModel).where(TripModel.id == trip_id)
    )
    trip = trip_result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    if not check_trip_ownership(trip, auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    # Get itinerary
    itinerary_result = await db.execute(
        select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
    )
    itinerary_model = itinerary_result.scalar_one_or_none()

    if not itinerary_model or not itinerary_model.days:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found. Please generate a plan first."
        )

    # Find the requested day
    # Note: itinerary_model.days is a list of ItineraryDay dicts, not {"days": [...]}
    days_data = itinerary_model.days if isinstance(itinerary_model.days, list) else itinerary_model.days.get("days", [])
    day_data = None
    for d in days_data:
        if d.get("day_number") == day_id:
            day_data = d
            break

    if not day_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Day {day_id} not found in itinerary"
        )

    # Extract places from blocks
    places = []
    total_distance_m = 0
    total_walking_minutes = 0

    for block in day_data.get("blocks", []):
        poi = block.get("poi")
        if poi:
            start_time = block.get("start_time", "")
            end_time = block.get("end_time", "")

            # Format time strings
            if isinstance(start_time, str) and ":" in start_time:
                start_str = start_time[:5]  # HH:MM
            else:
                start_str = "00:00"

            if isinstance(end_time, str) and ":" in end_time:
                end_str = end_time[:5]
            else:
                end_str = "00:00"

            places.append(StudioPlaceDTO(
                id=str(poi.get("poi_id", "")),
                name=poi.get("name", ""),
                latitude=poi.get("lat", 0.0) or 0.0,
                longitude=poi.get("lon", 0.0) or 0.0,
                time_start=start_str,
                time_end=end_str,
                category=poi.get("category", "other"),
                rating=poi.get("rating"),
                price_level=poi.get("price_level"),
                photo_url=None,  # TODO: Add photo URL support
                address=poi.get("location")
            ))

        # Accumulate metrics
        travel_dist = block.get("travel_distance_meters")
        if travel_dist:
            total_distance_m += travel_dist

        travel_time = block.get("travel_time_from_prev", 0)
        if travel_time:
            total_walking_minutes += travel_time

    # Calculate metrics
    distance_km = total_distance_m / 1000.0
    steps_estimate = int(distance_km * 1300)  # ~1300 steps per km

    metrics = DayMetricsDTO(
        distance_km=round(distance_km, 1),
        steps_estimate=steps_estimate,
        places_count=len(places),
        walking_time_minutes=total_walking_minutes
    )

    # Generate AI summary
    ai_summary = await _generate_day_summary(
        city=trip.city,
        day_number=day_id,
        places=places,
        theme=day_data.get("theme", ""),
        db=db
    )

    # Default settings (from trip or defaults)
    settings = DaySettingsDTO(
        tempo=trip.pace.value if trip.pace else "medium",
        start_time="08:00",
        end_time="18:00",
        budget=trip.budget.value if trip.budget else "medium"
    )

    # TODO: Load wishes from database
    wishes: List[WishMessageDTO] = []

    # TODO: Implement proper revision tracking
    revision = 1

    return DayStudioResponse(
        day=DayStudioDataDTO(places=places, wishes=wishes),
        settings=settings,
        preset=None,
        ai_summary=ai_summary,
        metrics=metrics,
        suggestions=None,
        revision=revision
    )


@router.post(
    "/{trip_id}/day/{day_id}/apply_changes",
    response_model=DayStudioResponse,
    summary="Apply day changes",
    description="Apply a batch of changes to a day and regenerate the plan."
)
async def apply_day_changes(
    trip_id: UUID,
    day_id: int,
    request: ApplyChangesRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> DayStudioResponse:
    """
    Apply changes to a day and regenerate affected portions.

    Args:
        trip_id: UUID of the trip
        day_id: Day number (1-indexed)
        request: Changes to apply with base revision for conflict detection

    Returns:
        Updated DayStudioResponse
    """
    print(f"\n🎯 apply_day_changes CALLED: trip={trip_id}, day={day_id}, changes={len(request.changes)}")

    # Verify trip exists and user has access
    trip_result = await db.execute(
        select(TripModel).where(TripModel.id == trip_id)
    )
    trip = trip_result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    if not check_trip_ownership(trip, auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this trip"
        )

    # Get itinerary
    itinerary_result = await db.execute(
        select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
    )
    itinerary_model = itinerary_result.scalar_one_or_none()

    if not itinerary_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    # TODO: Check revision for conflict (future enhancement)

    # Convert API changes to DayEditor changes
    day_changes = []
    for change in request.changes:
        change_type_map = {
            "update_settings": ChangeType.UPDATE_SETTINGS,
            "set_preset": ChangeType.SET_PRESET,
            "add_place": ChangeType.ADD_PLACE,
            "replace_place": ChangeType.REPLACE_PLACE,
            "remove_place": ChangeType.REMOVE_PLACE,
            "add_wish_message": ChangeType.ADD_WISH_MESSAGE,
        }

        change_type = change_type_map.get(change.type)
        if not change_type:
            logger.warning(f"Unknown change type: {change.type}")
            continue

        # Build change data dict
        data = {}
        if change.data.tempo:
            data["tempo"] = change.data.tempo
        if change.data.start_time:
            data["start_time"] = change.data.start_time
        if change.data.end_time:
            data["end_time"] = change.data.end_time
        if change.data.budget:
            data["budget"] = change.data.budget
        if change.data.preset is not None:
            data["preset"] = change.data.preset
        if change.data.place_id:
            data["place_id"] = change.data.place_id
        if change.data.placement:
            data["placement"] = {
                "type": change.data.placement.type,
                "slot_index": change.data.placement.slot_index,
                "hour": change.data.placement.hour,
                "minute": change.data.placement.minute,
            }
        if change.data.from_place_id:
            data["from_place_id"] = change.data.from_place_id
        if change.data.to_place_id:
            data["to_place_id"] = change.data.to_place_id
        if change.data.text:
            data["text"] = change.data.text

        day_changes.append(DayChange(type=change_type, data=data))

    print(f"📝 Converted {len(day_changes)} changes for DayEditor")
    for i, dc in enumerate(day_changes):
        print(f"   Change {i+1}: {dc.type.value} - data: {dc.data}")

    logger.info(f"🔄 Applying {len(day_changes)} changes to day {day_id} of trip {trip_id}")
    for i, dc in enumerate(day_changes):
        logger.info(f"   Change {i+1}: {dc.type.value} - data: {dc.data}")

    # Apply changes using DayEditor
    print(f"🔧 Creating DayEditor instance...")
    editor = DayEditor()

    try:
        print(f"🚀 Calling editor.apply_changes_to_day()...")
        updated_day = await editor.apply_changes_to_day(
            trip_id=trip_id,
            day_number=day_id,
            changes=day_changes,
            db=db
        )
        print(f"✅ DayEditor returned: {len(updated_day.blocks)} blocks")

        # Convert updated day back to response format
        places = []
        for block in updated_day.blocks:
            if block.poi:
                places.append(StudioPlaceDTO(
                    id=str(block.poi.poi_id),
                    name=block.poi.name,
                    latitude=block.poi.lat or 0.0,
                    longitude=block.poi.lon or 0.0,
                    time_start=block.start_time[:5] if isinstance(block.start_time, str) else block.start_time.strftime("%H:%M"),
                    time_end=block.end_time[:5] if isinstance(block.end_time, str) else block.end_time.strftime("%H:%M"),
                    category=block.poi.category,
                    rating=block.poi.rating,
                    price_level=None,  # TODO: Add price level support
                    photo_url=None,
                    address=block.poi.location
                ))

        # Calculate metrics
        total_distance_m = sum(b.travel_distance_meters or 0 for b in updated_day.blocks)
        total_walking_minutes = sum(b.travel_time_from_prev or 0 for b in updated_day.blocks)
        distance_km = total_distance_m / 1000.0
        steps_estimate = int(distance_km * 1300)

        metrics = DayMetricsDTO(
            distance_km=round(distance_km, 1),
            steps_estimate=steps_estimate,
            places_count=len(places),
            walking_time_minutes=total_walking_minutes
        )

        # Extract settings from changes or use defaults
        new_settings = DaySettingsDTO(
            tempo=trip.pace.value if trip.pace else "medium",
            start_time="08:00",
            end_time="18:00",
            budget=trip.budget.value if trip.budget else "medium"
        )
        new_preset = None

        for change in day_changes:
            if change.type == ChangeType.UPDATE_SETTINGS:
                if "tempo" in change.data:
                    new_settings.tempo = change.data["tempo"]
                if "start_time" in change.data:
                    new_settings.start_time = change.data["start_time"]
                if "end_time" in change.data:
                    new_settings.end_time = change.data["end_time"]
                if "budget" in change.data:
                    new_settings.budget = change.data["budget"]
            elif change.type == ChangeType.SET_PRESET:
                new_preset = change.data.get("preset")

        # Regenerate AI summary
        ai_summary = await _generate_day_summary(
            city=trip.city,
            day_number=day_id,
            places=places,
            theme=updated_day.theme,
            preset=new_preset,
            tempo=new_settings.tempo,
            budget=new_settings.budget,
            db=db
        )

        # TODO: Load wishes from database
        wishes: List[WishMessageDTO] = []

        response = DayStudioResponse(
            day=DayStudioDataDTO(places=places, wishes=wishes),
            settings=new_settings,
            preset=new_preset,
            ai_summary=ai_summary,
            metrics=metrics,
            suggestions=None,
            revision=request.base_revision + 1
        )

        print(f"📤 Returning response with {len(places)} places, revision={response.revision}")
        print(f"   Settings: start={new_settings.start_time}, end={new_settings.end_time}")
        print(f"   Preset: {new_preset}")

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to apply changes to day {day_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply changes: {str(e)}"
        )


# MARK: - Place Search Router

places_router = APIRouter(prefix="/places", tags=["places"])


@places_router.post(
    "/search",
    response_model=PlaceSearchResponse,
    summary="Search for places",
    description="Search for places by query string."
)
async def search_places(
    request: PlaceSearchRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PlaceSearchResponse:
    """
    Search for places using Google Places API.

    Args:
        request: Search query and parameters

    Returns:
        List of matching places
    """
    from src.infrastructure.poi_providers import get_poi_provider

    try:
        provider = get_poi_provider()

        # Search using the provider
        candidates = await provider.search_pois(
            city=request.city,
            query=request.query,
            limit=request.limit or 10
        )

        results = [
            PlaceSearchResultDTO(
                place_id=str(c.poi_id),
                name=c.name,
                category=c.category,
                rating=c.rating,
                address=c.location,
                photo_url=None,
                latitude=c.lat,
                longitude=c.lon
            )
            for c in candidates
        ]

        return PlaceSearchResponse(results=results)

    except Exception as e:
        print(f"❌ Place search error: {e}")
        # Return empty results on error
        return PlaceSearchResponse(results=[])


# MARK: - Helper Functions

async def _generate_day_summary(
    city: str,
    day_number: int,
    places: List[StudioPlaceDTO],
    theme: str,
    preset: Optional[str] = None,
    tempo: str = "medium",
    budget: str = "medium",
    wishes: Optional[List[str]] = None,
    db: Optional[AsyncSession] = None,
) -> str:
    """
    Generate an AI summary for a day using LLM.

    Args:
        city: City name
        day_number: Day number
        places: List of places in the day
        theme: Day theme
        preset: Selected preset (if any)
        tempo: Day tempo setting
        budget: Day budget setting
        wishes: User wishes (if any)
        db: Database session for caching

    Returns:
        AI-generated summary string
    """
    # Create input hash for caching
    input_data = {
        "city": city,
        "day": day_number,
        "places": [p.name for p in places],
        "preset": preset,
        "tempo": tempo,
        "budget": budget,
        "wishes": wishes or []
    }
    input_hash = hashlib.md5(json.dumps(input_data, sort_keys=True).encode()).hexdigest()

    # TODO: Check cache in database

    # Build place descriptions
    place_names = [p.name for p in places]

    if not place_names:
        return f"День {day_number} в {city} ждёт вашего планирования."

    # Determine meal count
    meal_categories = {"cafe", "restaurant", "food", "breakfast", "lunch", "dinner"}
    meal_count = sum(1 for p in places if p.category.lower() in meal_categories)

    # Build summary based on context
    try:
        from src.infrastructure.llm_client import get_trip_chat_llm_client

        llm = get_trip_chat_llm_client()

        prompt = f"""Сгенерируй краткую (3-4 предложения) консьерж-стиль сводку дня путешествия.

Город: {city}
День: {day_number}
Места: {', '.join(place_names)}
Тема дня: {theme or 'обзорный'}
Пресет: {preset or 'не выбран'}
Темп: {tempo}
Бюджет: {budget}
Приёмов пищи: {meal_count}
{f'Пожелания: {", ".join(wishes)}' if wishes else ''}

Требования к стилю:
- Тон консьержа премиум-отеля
- Упомяни 1-2 ключевых места
- Если есть пресет или ограничения, отрази их мягко
- Без воды и общих фраз
- 3-4 строки максимум

Ответь только текстом сводки, без кавычек и преамбул."""

        summary = await llm.generate_text(
            prompt=prompt,
            system_prompt="Ты — личный консьерж путешественника. Пиши кратко, по делу, с теплотой.",
            max_tokens=256
        )

        # TODO: Cache result in database

        return summary.strip()

    except Exception as e:
        print(f"⚠️ LLM summary generation failed: {e}")
        # Fallback to simple summary
        return _generate_fallback_summary(city, day_number, place_names, theme, preset, tempo)


def _generate_fallback_summary(
    city: str,
    day_number: int,
    place_names: List[str],
    theme: str,
    preset: Optional[str],
    tempo: str
) -> str:
    """Generate a simple fallback summary without LLM."""

    tempo_adj = {
        "low": "неспешный",
        "medium": "сбалансированный",
        "high": "насыщенный"
    }.get(tempo, "сбалансированный")

    preset_text = ""
    if preset:
        preset_map = {
            "overview": "обзорный",
            "food": "гастрономический",
            "walks": "прогулочный",
            "avoid_crowds": "без толп",
            "art": "артистический",
            "architecture": "архитектурный",
            "cozy": "уютный",
            "nightlife": "вечерний"
        }
        preset_text = f" {preset_map.get(preset, preset)}"

    if len(place_names) == 0:
        return f"День {day_number} в городе {city}."
    elif len(place_names) == 1:
        return f"{tempo_adj.capitalize()}{preset_text} день в {city}. Главное место — {place_names[0]}."
    elif len(place_names) <= 3:
        return f"{tempo_adj.capitalize()}{preset_text} день в {city}: {', '.join(place_names)}."
    else:
        return f"{tempo_adj.capitalize()}{preset_text} день в {city}. Начало в {place_names[0]}, далее {place_names[1]}, и ещё {len(place_names) - 2} мест."
