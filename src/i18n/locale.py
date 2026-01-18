"""
Language detection and localization utilities.

Provides:
- SupportedLanguage enum with all supported languages
- LocaleContext for request-scoped language storage
- t() function for translation lookup
- LLM language instruction generation
"""

from enum import Enum
from typing import Optional, Any
from functools import lru_cache
from pathlib import Path
from contextvars import ContextVar
import json
import logging

logger = logging.getLogger(__name__)

# Context variable for request-scoped language
_current_language: ContextVar[Optional["SupportedLanguage"]] = ContextVar(
    "current_language", default=None
)


class SupportedLanguage(str, Enum):
    """Supported languages for the application."""

    ENGLISH = "en"
    RUSSIAN = "ru"
    CHINESE = "zh"
    FRENCH = "fr"
    SPANISH = "es"
    ARABIC = "ar"
    GERMAN = "de"

    @classmethod
    def from_code(cls, code: str) -> "SupportedLanguage":
        """
        Parse language code from various formats.

        Handles:
        - Simple codes: en, ru, zh
        - Regional variants: en-US, zh-Hans, zh-CN
        - Accept-Language quality: en;q=0.9

        Args:
            code: Language code string

        Returns:
            Matching SupportedLanguage or ENGLISH as fallback
        """
        if not code:
            return cls.ENGLISH

        # Remove quality value if present (e.g., "en;q=0.9" -> "en")
        code = code.split(";")[0].strip()

        # Normalize
        normalized = code.lower()

        # Check exact match first
        for lang in cls:
            if lang.value == normalized:
                return lang

        # Handle Chinese variants
        if normalized.startswith("zh"):
            return cls.CHINESE

        # Extract base language code (e.g., "en-US" -> "en")
        base_code = normalized.split("-")[0]

        for lang in cls:
            if lang.value == base_code:
                return lang

        return cls.ENGLISH  # Default fallback

    @property
    def display_name(self) -> str:
        """Human-readable name in English (for LLM prompts)."""
        names = {
            self.ENGLISH: "English",
            self.RUSSIAN: "Russian",
            self.CHINESE: "Simplified Chinese",
            self.FRENCH: "French",
            self.SPANISH: "Spanish",
            self.ARABIC: "Arabic",
            self.GERMAN: "German",
        }
        return names.get(self, "English")

    @property
    def native_name(self) -> str:
        """Name in the language itself."""
        names = {
            self.ENGLISH: "English",
            self.RUSSIAN: "Русский",
            self.CHINESE: "简体中文",
            self.FRENCH: "Français",
            self.SPANISH: "Español",
            self.ARABIC: "العربية",
            self.GERMAN: "Deutsch",
        }
        return names.get(self, "English")

    @property
    def is_rtl(self) -> bool:
        """Whether this language uses right-to-left text direction."""
        return self == self.ARABIC


class LocaleContext:
    """
    Thread-safe context for the current request's language.

    Uses Python's contextvars to maintain request-scoped state
    in async environments.
    """

    @classmethod
    def get(cls) -> SupportedLanguage:
        """Get current language for this request/context."""
        lang = _current_language.get()
        return lang if lang is not None else SupportedLanguage.ENGLISH

    @classmethod
    def set(cls, language: SupportedLanguage) -> None:
        """Set language for this request/context."""
        _current_language.set(language)

    @classmethod
    def reset(cls) -> None:
        """Reset to default (English)."""
        _current_language.set(None)


@lru_cache(maxsize=10)
def load_translations(language: SupportedLanguage) -> dict:
    """
    Load translation file for a language.

    Uses LRU cache to avoid repeated file reads.

    Args:
        language: The language to load translations for

    Returns:
        Dictionary of translation keys to values
    """
    translations_dir = Path(__file__).parent / "translations"
    file_path = translations_dir / f"{language.value}.json"

    if not file_path.exists():
        logger.warning(f"Translation file not found: {file_path}, falling back to English")
        file_path = translations_dir / "en.json"

    if not file_path.exists():
        logger.error("English translation file not found!")
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in translation file {file_path}: {e}")
        return {}


def t(key: str, **kwargs: Any) -> str:
    """
    Get translated string for current locale.

    Supports:
    - Nested keys with dot notation: "errors.trip_not_found"
    - String interpolation: t("errors.trip_not_found", trip_id=123)
    - Fallback to English if key not found in current language
    - Fallback to key itself if not found anywhere

    Args:
        key: Translation key (dot-separated for nested access)
        **kwargs: Values to interpolate into the string

    Returns:
        Translated and interpolated string

    Example:
        >>> t("errors.trip_not_found", trip_id="abc-123")
        "Trip with ID abc-123 not found"
    """
    language = LocaleContext.get()
    translations = load_translations(language)

    # Navigate nested keys
    value = _get_nested(translations, key)

    # Fallback to English if not found
    if value is None and language != SupportedLanguage.ENGLISH:
        english_translations = load_translations(SupportedLanguage.ENGLISH)
        value = _get_nested(english_translations, key)

    # Fallback to key itself
    if value is None:
        logger.warning(f"Translation not found for key: {key}")
        return key

    # Interpolate values
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing interpolation key {e} for translation: {key}")
            return value

    return value


def _get_nested(data: dict, key: str) -> Optional[str]:
    """
    Get value from nested dictionary using dot notation.

    Args:
        data: Dictionary to search
        key: Dot-separated key path (e.g., "errors.trip_not_found")

    Returns:
        String value if found, None otherwise
    """
    parts = key.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current if isinstance(current, str) else None


def get_llm_language_instruction(language: Optional[SupportedLanguage] = None) -> str:
    """
    Generate instruction for LLM to respond in specific language.

    This instruction should be appended to LLM system prompts to ensure
    the model responds in the user's preferred language.

    Args:
        language: Target language (defaults to current context)

    Returns:
        Instruction string to append to LLM prompt
    """
    lang = language or LocaleContext.get()

    return f"\n\nIMPORTANT: You MUST respond in {lang.display_name}. All user-facing text in your response must be in {lang.display_name}."


def get_google_places_language(language: Optional[SupportedLanguage] = None) -> str:
    """
    Get language code for Google Places API.

    Args:
        language: Target language (defaults to current context)

    Returns:
        Language code compatible with Google Places API
    """
    lang = language or LocaleContext.get()

    # Google Places uses slightly different codes for some languages
    google_codes = {
        SupportedLanguage.CHINESE: "zh-CN",  # Simplified Chinese
        SupportedLanguage.ARABIC: "ar",
    }

    return google_codes.get(lang, lang.value)
