"""
FastAPI middleware for language detection and context setup.

Reads language from request headers and sets LocaleContext for the duration
of the request.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.i18n.locale import SupportedLanguage, LocaleContext


class LocaleMiddleware(BaseHTTPMiddleware):
    """
    Middleware to detect and set request language.

    Language detection priority:
    1. X-Language header (explicit app setting from iOS/Android)
    2. Accept-Language header (browser/system preference)
    3. Default to English

    The detected language is stored in:
    - LocaleContext (thread-local/async-safe context variable)
    - request.state.language (for direct access in endpoints)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Detect language from headers
        language = self._detect_language(request)

        # Set context for this request
        LocaleContext.set(language)

        # Also store in request state for direct access
        request.state.language = language

        try:
            response = await call_next(request)
            # Add Content-Language header to response
            response.headers["Content-Language"] = language.value
            return response
        finally:
            # Reset context after request
            LocaleContext.reset()

    def _detect_language(self, request: Request) -> SupportedLanguage:
        """
        Detect language from request headers.

        Args:
            request: FastAPI/Starlette request object

        Returns:
            Detected SupportedLanguage
        """
        # Priority 1: Explicit X-Language header from app
        explicit_lang = request.headers.get("X-Language")
        if explicit_lang:
            return SupportedLanguage.from_code(explicit_lang)

        # Priority 2: Accept-Language header
        accept_lang = request.headers.get("Accept-Language", "")
        if accept_lang:
            # Parse Accept-Language (e.g., "ru-RU,ru;q=0.9,en;q=0.8")
            # Take the first (highest priority) language
            first_lang = accept_lang.split(",")[0].strip()
            return SupportedLanguage.from_code(first_lang)

        # Default fallback
        return SupportedLanguage.ENGLISH
