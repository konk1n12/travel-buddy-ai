# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Travel Buddy AI** is an AI-powered trip planning system:
- **Backend:** FastAPI + PostgreSQL with LLM integration (io.net or Anthropic)
- **iOS App:** SwiftUI native client (iOS 16+)
- **Features:** Multi-day itineraries, POI selection, route optimization, freemium gating

Core flow: `User Input → Backend API → LLM Processing → POI Selection → Route Optimization → iOS Display`

## Essential Commands

### Backend

```bash
make up                   # Start Docker containers (API + PostgreSQL)
make down                 # Stop containers
make logs                 # View Docker logs
make dev                  # Run API locally with hot reload

make db-upgrade           # Apply database migrations
make db-migrate msg="..." # Generate new migration
make test                 # Run all tests
pytest tests/test_foo.py  # Run single test file
pytest tests/test_foo.py::test_bar -v  # Run specific test

make check-externals      # Check all external API connections
docker compose down -v    # Fresh database (removes volumes)
```

### iOS

```bash
open "ios/Travell Buddy.xcodeproj"  # Open in Xcode, then ⌘R to run
```

## Architecture

### Backend Layers (Clean Architecture)

```
src/
├── api/           # HTTP endpoints (FastAPI routers)
├── application/   # Business logic orchestration
├── domain/        # Core models (Pydantic schemas)
├── infrastructure/# External integrations (LLM, Google APIs, DB)
├── auth/          # JWT, providers, auth service
└── i18n/          # Localization middleware
```

**Trip Planning Pipeline** (`src/application/trip_planner.py`):
1. **MacroPlanner** - LLM generates day structure (time blocks, themes)
2. **POIPlanner** - Selects actual places from Google Places
3. **RouteOptimizer** - Orders POIs for efficient walking routes
4. **TripCritic** - Validates and reports issues

**Key Application Components:**
- `trip_planner.py` - Main orchestrator
- `route_optimizer.py` / `smart_route_optimizer.py` - Travel optimization
- `district_planner.py` - Geographic clustering by neighborhoods
- `day_editor.py` - AI Studio day editing
- `place_replacement_service.py` - Replace POI alternatives

### iOS Architecture (MVVM)

```
ios/Travell Buddy/
├── TripPlanning/      # Trip views and view models
├── Chat/              # Chat interface
├── Services/          # AuthManager, AuthGatingManager, SavedTripsManager
├── Networking/        # API clients and DTOs
├── Features/          # PlaceDetails, RouteBuilding, TripSummary
└── Views/             # Reusable UI components
```

**Key View Models:**
- `TripPlanViewModel` - Trip display and interaction state
- `ChatViewModel` - Trip planning chat
- `EditDayViewModel` - Day editing (AI Studio)

**Singletons:**
- `AuthManager.shared` - Authentication state
- `AuthGatingManager.shared` - Freemium gating (`isDayLocked`, `isMapLocked`)

**API Clients:**
- `TripPlanningAPIClient` - Unauthenticated calls
- `AuthenticatedAPIClient` - Requires JWT token

## Configuration

Copy `.env.example` to `.env` and set:

```bash
# Required
IONET_API_KEY=...           # or ANTHROPIC_API_KEY
GOOGLE_MAPS_API_KEY=...

# Key settings
LLM_PROVIDER=ionet          # "ionet" or "anthropic"
FREEMIUM_ENABLED=false      # true in production
ENABLE_SMART_ROUTING=true   # Geographic clustering
ENABLE_AGENTIC_PLANNING=true # LLM personalization
```

Database runs on port **5433** (mapped from container's 5432).

## API Documentation

When running: http://localhost:8000/docs (Swagger) or http://localhost:8000/redoc

Key endpoints:
- `POST /api/trips` - Create trip
- `POST /api/trips/{id}/plan` - Generate itinerary
- `GET /api/trips/{id}/itinerary` - Get full itinerary
- `POST /api/trips/{id}/chat` - Natural language planning
- `POST /api/day-studio/{trip_id}/days/{day_index}/...` - AI Studio editing

## Testing

pytest-asyncio is configured in **auto mode** - async tests are detected automatically.

```bash
make test                              # All tests
pytest tests/test_trips.py -v          # Specific file
pytest -k "test_macro" -v              # Pattern match
pytest --tb=short                      # Shorter tracebacks
```

## Key Files Reference

**Backend:**
- `src/application/trip_planner.py` - Main planning orchestrator
- `src/api/trips.py` - Trip CRUD endpoints
- `src/api/day_studio.py` - AI Studio endpoints
- `src/infrastructure/llm_client.py` - LLM provider abstraction
- `src/config.py` - All configuration settings

**iOS:**
- `TripPlanning/TripPlanView.swift` - Main trip view
- `TripPlanning/TripPlanViewModel.swift` - Trip state management
- `Services/AuthManager.swift` - Auth state
- `Services/AuthGatingManager.swift` - Freemium logic
- `Networking/TripPlanningAPIClient.swift` - API calls
- `Config/AppConfig.swift` - Base URL and app config
