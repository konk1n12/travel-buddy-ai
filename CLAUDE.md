# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Never hallucinate or fabricate information. If you're unsure about anything, you MUST explicitly state your uncertainty. Say "I don't know" rather than guessing or making assumptions.

## Project Overview

AI-powered trip planning backend (FastAPI + PostgreSQL). Takes user inputs via chat or form, generates optimized multi-day itineraries with POI selection and route optimization.

Does NOT include: Live Guide, TTS/audio, Server-Driven UI, or frontend/mobile code (iOS app is in `ios/` but is a separate concern).

## Essential Commands

```bash
# Development
make install              # Install Python dependencies
make dev                  # Run API locally (uvicorn with reload)
make up                   # Start Docker containers (API + PostgreSQL)
make down                 # Stop Docker containers
make logs                 # View Docker logs

# Database
make db-upgrade           # Apply migrations
make db-downgrade         # Rollback last migration
make db-migrate msg="..."  # Generate new Alembic migration
make seed-pois            # Seed database with example POIs

# Testing
make test                 # Run all tests with coverage
pytest tests/test_foo.py  # Run single test file
pytest tests/test_foo.py::test_bar -v  # Run single test function

# External service checks (manual, not in pytest)
make check-externals      # Check all external APIs
make check-llm            # Check LLM (io.net or Anthropic)
make check-google-places  # Check Google Places API
make check-google-routes  # Check Google Routes API
```

## Tech Stack

- Python 3.11+, FastAPI, Pydantic v2
- SQLAlchemy 2.0 async + asyncpg + PostgreSQL
- Alembic for migrations
- LLM: io.net (default) or Anthropic Claude (configurable via `LLM_PROVIDER`)
- pytest-asyncio with auto mode

## Architecture

Four layers in `src/`:

1. **api/** - FastAPI routers (HTTP endpoints)
2. **application/** - Business logic orchestrators
3. **domain/** - Core models (Pydantic schemas in `schemas.py`, DB models in `models.py`)
4. **infrastructure/** - Database, LLM client, external APIs (Google Places/Routes)

### Planning Pipeline Flow

```
TripSpec → MacroPlanner → DaySkeleton → POIPlanner → RouteOptimizer → Itinerary → TripCritic
```

Key components in `src/application/`:
- **trip_spec.py** - Collects/validates user inputs
- **trip_chat.py** - Natural language → TripSpec updates via LLM
- **macro_planner.py** - LLM-based high-level day structure
- **poi_planner.py** - POI candidate selection (deterministic + optional LLM ranking)
- **poi_selection_llm.py** - LLM-based POI re-ranking (when `USE_LLM_FOR_POI_SELECTION=true`)
- **route_optimizer.py** - Travel time optimization, opening hours compliance
- **district_planner.py** - Geographic clustering for walking-efficient routes
- **trip_critic.py** - Validation (missing meals, closed POIs, long days)

### Infrastructure Layer

- **llm_client.py** - Provider-agnostic LLM (Anthropic/OpenAI-compatible)
- **poi_providers.py** - Google Places integration with caching
- **travel_time.py** - Simple heuristic or Google Routes API
- **geocoding.py** - Address → coordinates

## Key Environment Variables

Copy `.env.example` to `.env`. Critical settings:

```bash
LLM_PROVIDER=ionet                    # or "anthropic"
IONET_API_KEY=...                     # Required for io.net
GOOGLE_MAPS_API_KEY=...               # Required for POI search and routes
DATABASE_URL=postgresql+asyncpg://... # DB connection
TRAVEL_TIME_PROVIDER=google_maps      # or "simple" (heuristic)
USE_LLM_FOR_POI_SELECTION=true        # Enable LLM POI ranking
ENABLE_SMART_ROUTING=true             # Geographic clustering
FREEMIUM_ENABLED=false                # Auth gating (set true in prod)
```

## Key Domain Models

Defined in `src/domain/schemas.py`:
- `TripSpec` - User's trip configuration (city, dates, travelers, pace, interests)
- `DailyRoutine` - Wake/sleep times, meal windows
- `DaySkeleton` / `SkeletonBlock` - High-level day structure from macro planner
- `POICandidate` - Place candidates with ranking scores
- `ItineraryDay` / `ItineraryBlock` - Final detailed schedule
- `CritiqueIssue` - Validation problems per day/block
