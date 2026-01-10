"""
Trip Chat Assistant service.
Handles natural language chat messages and updates TripSpec via LLM.
"""
from uuid import UUID
from typing import Optional
import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.schemas import TripChatLLMResponse, TripChatResponse, TripUpdateRequest, TripUpdates
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_trip_chat_llm_client
from src.infrastructure.cache import ChatCache, get_chat_cache

class TripChatAssistant:
    """
    Service for handling trip-related chat messages.
    Uses LLM to interpret user messages and update TripSpec.
    """

    # System prompt for Trip Chat Mode (Russian language)
    SYSTEM_PROMPT = """Ты — дружелюбный и очень внимательный помощник по планированию путешествий. Твоя задача:
1. Понять предпочтения, ограничения и, что самое важное, КОНКРЕТНЫЕ запросы пользователя о поездке.
2. Ответить коротким, дружелюбным сообщением на русском языке (1-2 предложения), подтверждая, что ты понял запрос.
3. Извлечь структурированные обновления для спецификации поездки, включая ОБЩИЕ предпочтения и КОНКРЕТНЫЕ запросы.

Пользователь может сказать что-то вроде:
- Общие предпочтения: "Мы любим техно музыку", "Предпочитаем вегетарианскую еду"
- Конкретные запросы: "Найди 2-3 самых дорогих грузинских ресторана", "Я хочу в музей современного искусства", "добавь в план одну кофейню с хорошим рейтингом"

Ты ДОЛЖЕН отвечать валидным JSON в точно таком формате:
{
  "assistant_message": "Твой дружелюбный ответ на русском языке",
  "trip_updates": {
    "interests": ["список", "общих", "интересов"],
    "additional_preferences": {
      "любой_ключ": "любое_значение"
    },
    "structured_preferences": [
      {
        "keyword": "например, 'грузинский'",
        "category": "restaurant",
        "price_level": "expensive",
        "quantity": 2
      }
    ]
  }
}

Правила для trip_updates:
- interests: список ОБЩИХ интересов/предпочтений (еда, культура, ночная жизнь).
- additional_preferences: произвольный словарь для ДРУГИХ общих предпочтений.
- structured_preferences: список для КОНКРЕТНЫХ, структурированных запросов.
  - "keyword": Ключевое слово для поиска (например, "грузинский", "кофе", "современное искусство").
  - "category": Категория POI (например, "restaurant", "cafe", "museum", "park").
  - "price_level": Уровень цен ("cheap", "moderate", "expensive"). Определяй из контекста.
  - "quantity": Количество таких мест, если указано.
- Если сообщение не требует обновлений, оставь trip_updates пустым ({}).
- Если запрос не содержит конкретики, `structured_preferences` должен быть пустым списком `[]`.

ВАЖНО: Поле assistant_message ВСЕГДА должно быть на русском языке!
Будь дружелюбным, кратким и подтверждай понимание пожеланий пользователя."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        cache: Optional[ChatCache] = None,
    ):
        """
        Initialize Trip Chat Assistant.

        Args:
            llm_client: LLM client (defaults to factory function)
            cache: Chat cache (defaults to global instance)
        """
        self.llm_client = llm_client or get_trip_chat_llm_client()
        self.cache = cache or get_chat_cache()
        self.trip_spec_collector = TripSpecCollector()

    def _build_user_prompt(self, trip_context: str, user_message: str) -> str:
        """Build the user prompt with trip context."""
        return f"""Текущая поездка:
{trip_context}

Сообщение пользователя: {user_message}

Ответь только JSON."""

    def _safe_apply_trip_updates(self, trip_updates: TripUpdates) -> TripUpdateRequest:
        """
        Safely convert LLM trip_updates model to TripUpdateRequest.
        Only allows updating specific allowed fields.
        """
        allowed_updates = {}

        if trip_updates.interests is not None:
            allowed_updates["interests"] = trip_updates.interests

        if trip_updates.pace is not None:
            allowed_updates["pace"] = trip_updates.pace

        if trip_updates.budget is not None:
            allowed_updates["budget"] = trip_updates.budget

        if trip_updates.additional_preferences is not None:
            allowed_updates["additional_preferences"] = trip_updates.additional_preferences
        
        if trip_updates.structured_preferences is not None:
            allowed_updates["structured_preferences"] = trip_updates.structured_preferences

        return TripUpdateRequest(**allowed_updates)

    async def handle_chat_message(
        self,
        trip_id: UUID,
        user_message: str,
        db: AsyncSession,
        use_cache: bool = True,
    ) -> TripChatResponse:
        """
        Handle a chat message for a trip.

        Args:
            trip_id: Trip UUID
            user_message: User's natural language message
            db: Database session
            use_cache: Whether to use cache (default True)

        Returns:
            TripChatResponse with assistant message and updated trip

        Raises:
            ValueError: If trip not found or LLM response invalid
        """
        # 1. Load current trip
        current_trip = await self.trip_spec_collector.get_trip(trip_id, db)
        if not current_trip:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Check cache
        cache_key = None
        if use_cache:
            cache_key = self.cache.generate_cache_key(str(trip_id), user_message)
            cached_response = self.cache.get(cache_key)
            if cached_response:
                # Return cached response with fresh trip data
                return TripChatResponse(
                    assistant_message=cached_response["assistant_message"],
                    trip=current_trip,
                )

        # 3. Build trip context for LLM (Russian)
        trip_context = f"""- Город: {current_trip.city}
- Даты: {current_trip.start_date} — {current_trip.end_date}
- Путешественников: {current_trip.num_travelers}
- Темп: {current_trip.pace}
- Бюджет: {current_trip.budget}
- Интересы: {', '.join(current_trip.interests) if current_trip.interests else 'не указаны'}
- Дополнительные предпочтения: {json.dumps(current_trip.additional_preferences, ensure_ascii=False)}"""

        # 4. Call LLM in Trip Chat Mode (use cheaper model)
        user_prompt = self._build_user_prompt(trip_context, user_message)

        try:
            # Use the dedicated trip_chat_model for cost optimization
            llm_response_raw = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=512,  # Keep it short for cost savings
            )

            # Parse into TripChatLLMResponse
            llm_response = TripChatLLMResponse(**llm_response_raw)

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {e}")

        # 5. Apply trip updates if any
        updated_trip = current_trip
        if llm_response.trip_updates:
            # Get the update object from the LLM response
            updates = llm_response.trip_updates

            # Merge interests instead of replacing
            if updates.interests:
                existing_interests = set(current_trip.interests or [])
                new_interests = set(updates.interests)
                merged_interests = list(existing_interests | new_interests)
                updates.interests = merged_interests
                print(f"  🔀 Merged interests: {existing_interests} + {new_interests} → {merged_interests}")

            # Merge additional_preferences instead of replacing
            if updates.additional_preferences:
                merged_prefs = {
                    **current_trip.additional_preferences,
                    **updates.additional_preferences,
                }
                updates.additional_preferences = merged_prefs
                print(f"  🔀 Merged additional_preferences: {len(merged_prefs)} items")

            # Merge structured_preferences instead of replacing
            if updates.structured_preferences:
                # Assuming current_trip has a structured_preferences attribute
                # which we will add to the model
                existing_structured_prefs = getattr(current_trip, 'structured_preferences', []) or []
                merged_structured_prefs = existing_structured_prefs + updates.structured_preferences
                updates.structured_preferences = merged_structured_prefs
                print(f"  🔀 Merged structured_preferences: {len(existing_structured_prefs)} + {len(updates.structured_preferences)} → {len(merged_structured_prefs)}")

            update_request = self._safe_apply_trip_updates(updates)
            
            if update_request.model_dump(exclude_unset=True):
                updated_trip = await self.trip_spec_collector.update_trip(
                    trip_id, update_request, db
                )
                if not updated_trip:
                    raise ValueError(f"Failed to update trip {trip_id}")

        # 6. Cache the response
        if use_cache and cache_key:
            self.cache.set(
                cache_key,
                {"assistant_message": llm_response.assistant_message},
                ttl_seconds=3600,  # 1 hour TTL
            )

        # 7. Return response
        return TripChatResponse(
            assistant_message=llm_response.assistant_message,
            trip=updated_trip,
        )
