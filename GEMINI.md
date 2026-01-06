# Gemini Code Assistant Context

This document provides context for the Gemini Code Assistant to understand the "Travel Buddy Ai" project.

## Project Overview

This is a travel planning application composed of two main parts:

1.  **Backend API**: A Python-based API server that provides AI-powered trip planning functionalities.
2.  **iOS Application**: A native iOS client that consumes the backend API to provide a user interface for trip planning.

### Backend

The backend is a modern Python web application with a layered architecture:

-   **Framework**: FastAPI
-   **Database**: PostgreSQL
-   **ORM**: SQLAlchemy 2.0 (async)
-   **Migrations**: Alembic
-   **Data Validation**: Pydantic v2
-   **AI**: Anthropic Claude is used as the default LLM.
-   **Deployment**: Docker and Docker Compose are used for containerization and local development setup.

The backend code is organized into four layers:
-   `src/api`: FastAPI routers and endpoints.
-   `src/application`: Business logic and service layer.
-   `src/domain`: Core business models (Pydantic schemas).
-   `src/infrastructure`: Database access, LLM clients, and other external service integrations.

### iOS Application

The iOS application is a native Swift application using SwiftUI. It communicates with the backend API to create trips, generate plans, and interact with the AI assistant. The Xcode project is located in the `ios/` directory.

Key components of the iOS app include:
-   **Networking**: A set of API clients for communicating with the backend (`ios/Travell Buddy/Networking/`).
-   **Models**: Data models for representing application data (`ios/Travell Buddy/Models/`).
-   **Views**: SwiftUI views for the user interface (`ios/Travell Buddy/Views/` and `ios/Travell Buddy/TripPlanning/`).

## Building and Running

### Backend

The backend can be run using Docker (recommended) or locally for development. The primary commands are managed via the `Makefile`.

**Docker (Recommended):**

-   **Start services (API + DB):**
    ```bash
    make up
    ```
-   **Stop services:**
    ```bash
    make down
    ```
-   **View logs:**
    ```bash
    make logs
    ```

**Local Development:**

1.  **Install dependencies:**
    ```bash
    make install
    ```
2.  **Start the database in Docker:**
    ```bash
    docker-compose up -d db
    ```
3.  **Run database migrations:**
    ```bash
    make db-upgrade
    ```
4.  **Start the API server:**
    ```bash
    make dev
    ```

The API will be available at `http://localhost:8000` and the documentation can be found at `http://localhost:8000/docs`.

### iOS Application

To run the iOS application:

1.  Open the Xcode project: `ios/Travell Buddy.xcodeproj`.
2.  Select a simulator or a connected device.
3.  Click the "Run" button in Xcode.

## Development Conventions

### Backend

-   **Testing**: The project uses `pytest` for testing. Run tests with:
    ```bash
    make test
    ```
-   **Database Migrations**: Alembic is used for database schema migrations.
    -   Create a new migration: `make db-migrate msg="Your migration message"`
    -   Apply migrations: `make db-upgrade`
-   **Dependencies**: Python dependencies are managed in `requirements.txt`.
-   **External Services Checks**: Manual checks for external services (LLM, Google Places, Google Routes) are available:
    ```bash
    make check-externals
    ```

### iOS

The iOS project follows standard Swift and SwiftUI conventions. Dependencies are managed by Xcode.