"""
City geocoding service using Google Geocoding API.
Converts city names to latitude/longitude coordinates.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GeocodingResult:
    """Result from geocoding a city name."""
    city: str
    lat: float
    lon: float
    formatted_address: str


class GeocodingService:
    """
    Service for geocoding city names to coordinates.
    Uses Google Geocoding API.
    """

    GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: int = 10,
    ):
        """
        Initialize geocoding service.

        Args:
            api_key: Google Maps API key (defaults to settings)
            timeout_seconds: HTTP timeout in seconds
        """
        self.api_key = api_key or settings.google_maps_api_key
        self.timeout_seconds = timeout_seconds

    async def geocode_city(self, city: str) -> Optional[GeocodingResult]:
        """
        Geocode a city name to coordinates.

        Args:
            city: City name (e.g., "Paris", "New York", "Tokyo")

        Returns:
            GeocodingResult with lat/lon if successful, None otherwise
        """
        if not self.api_key:
            logger.warning("Google Maps API key not configured, cannot geocode city")
            return None

        params = {
            "address": city,
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.GEOCODING_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

            status = data.get("status", "UNKNOWN")
            if status != "OK":
                if status == "ZERO_RESULTS":
                    logger.warning(f"No geocoding results for city: {city}")
                else:
                    logger.warning(f"Geocoding API returned status: {status}")
                return None

            results = data.get("results", [])
            if not results:
                logger.warning(f"Empty results for city: {city}")
                return None

            # Use the first result
            result = results[0]
            geometry = result.get("geometry", {})
            location = geometry.get("location", {})

            lat = location.get("lat")
            lon = location.get("lng")

            if lat is None or lon is None:
                logger.warning(f"Missing coordinates in geocoding result for: {city}")
                return None

            formatted_address = result.get("formatted_address", city)

            logger.info(f"Geocoded '{city}' to ({lat}, {lon})")

            return GeocodingResult(
                city=city,
                lat=lat,
                lon=lon,
                formatted_address=formatted_address,
            )

        except httpx.TimeoutException:
            logger.warning(f"Geocoding API timeout for city: {city}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Geocoding API HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during geocoding: {e}")
            return None


# Global service instance
_geocoding_service: Optional[GeocodingService] = None


def get_geocoding_service() -> GeocodingService:
    """Get or create the geocoding service singleton."""
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service
