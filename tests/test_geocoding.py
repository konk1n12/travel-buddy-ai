"""
Tests for city geocoding service.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.infrastructure.geocoding import (
    GeocodingService,
    GeocodingResult,
    get_geocoding_service,
)


class TestGeocodingService:
    """Tests for GeocodingService."""

    @pytest.fixture
    def geocoding_service(self):
        """Create a geocoding service with test API key."""
        return GeocodingService(api_key="test_api_key")

    @pytest.mark.asyncio
    async def test_geocode_city_success(self, geocoding_service):
        """Test successful geocoding of a city."""
        mock_response = {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {
                            "lat": 48.8566,
                            "lng": 2.3522
                        }
                    },
                    "formatted_address": "Paris, France"
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response_obj

            result = await geocoding_service.geocode_city("Paris")

        assert result is not None
        assert result.city == "Paris"
        assert result.lat == 48.8566
        assert result.lon == 2.3522
        assert result.formatted_address == "Paris, France"

    @pytest.mark.asyncio
    async def test_geocode_city_zero_results(self, geocoding_service):
        """Test geocoding returns None for unknown city."""
        mock_response = {
            "status": "ZERO_RESULTS",
            "results": []
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response_obj

            result = await geocoding_service.geocode_city("UnknownCity12345")

        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_city_no_api_key(self):
        """Test geocoding without API key returns None."""
        service = GeocodingService(api_key=None)
        result = await service.geocode_city("Paris")
        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_city_timeout(self, geocoding_service):
        """Test geocoding handles timeout gracefully."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")

            result = await geocoding_service.geocode_city("Paris")

        assert result is None


class TestGeocodingResult:
    """Tests for GeocodingResult dataclass."""

    def test_geocoding_result_creation(self):
        """Test creating a GeocodingResult."""
        result = GeocodingResult(
            city="Tokyo",
            lat=35.6762,
            lon=139.6503,
            formatted_address="Tokyo, Japan"
        )

        assert result.city == "Tokyo"
        assert result.lat == 35.6762
        assert result.lon == 139.6503
        assert result.formatted_address == "Tokyo, Japan"


def test_get_geocoding_service_singleton():
    """Test that get_geocoding_service returns the same instance."""
    # Reset the global instance
    import src.infrastructure.geocoding as geocoding_module
    geocoding_module._geocoding_service = None

    service1 = get_geocoding_service()
    service2 = get_geocoding_service()

    assert service1 is service2
