"""
Trip Chat API endpoints for natural language trip updates.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.database import get_db
from src.infrastructure.models import TripModel
from src.application.trip_chat import TripChatAssistant
from src.domain.schemas import TripChatRequest, TripChatResponse
from src.auth.dependencies import (
    get_auth_context,
    AuthContext,
    check_trip_ownership,
)


router = APIRouter(prefix="/trips", tags=["chat"])


@router.post(
    "/{trip_id}/chat",
    response_model=TripChatResponse,
    summary="Send chat message for trip",
    description="Send a natural language message to update trip preferences via AI assistant."
)
async def chat_with_trip(
    trip_id: UUID,
    request: TripChatRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TripChatResponse:
    """
    Send a chat message to update a trip.

    The AI assistant interprets the natural language message, extracts preferences,
    and updates the TripSpec accordingly. Perfect for conversational trip refinement.

    Examples:
    - "We hate museums, we love techno nightlife"
    - "We prefer vegetarian food"
    - "We want to sleep in until 10am"

    Args:
        trip_id: UUID of the trip to update
        request: Chat request with user message

    Returns:
        TripChatResponse with assistant reply and updated trip data

    Raises:
        HTTPException 404 if trip not found
        HTTPException 500 if LLM processing fails
    """
    result = await db.execute(
        select(TripModel).where(TripModel.id == trip_id)
    )
    trip = result.scalar_one_or_none()

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

    assistant = TripChatAssistant()

    try:
        response = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message=request.message,
            db=db,
            use_cache=True,
        )
        return response

    except ValueError as e:
        # Trip not found or invalid LLM response
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process chat message: {error_msg}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
