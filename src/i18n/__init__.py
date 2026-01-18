"""
Internationalization (i18n) module for Travel Buddy API.

This module provides:
- Language detection and context management
- Translation loading and lookup
- Middleware for FastAPI
"""

from src.i18n.locale import (
    SupportedLanguage,
    LocaleContext,
    t,
    get_llm_language_instruction,
    load_translations,
)
from src.i18n.middleware import LocaleMiddleware

__all__ = [
    "SupportedLanguage",
    "LocaleContext",
    "t",
    "get_llm_language_instruction",
    "load_translations",
    "LocaleMiddleware",
]
