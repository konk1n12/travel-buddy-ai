//
//  TripPlanViewModel.swift
//  Travell Buddy
//
//  Manages trip plan state and communicates with backend API.
//

import Foundation

final class TripPlanViewModel: ObservableObject {
    enum TripPlanTab {
        case overview
        case route
        case map
    }

    /// Result of last plan update attempt (for chat rebuild)
    enum UpdateResult {
        case none
        case success
        case failure(String)
    }

    @Published var plan: TripPlan?
    @Published var selectedTab: TripPlanTab = .route
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    @Published var lastUpdateResult: UpdateResult = .none
    @Published var isShowingPaywall: Bool = false
    @Published var pendingIntent: PendingIntent?

    /// Indicates if this trip was loaded from saved trips
    @Published var isLoadedFromSavedTrip: Bool = false

    /// Indicates if the trip has been modified since loading
    @Published var hasUnsavedChanges: Bool = false

    /// Track revision number for each day (for optimistic locking)
    @Published var dayRevisions: [Int: Int] = [:]

    private let apiClient: TripPlanningAPIClient

    // Store last generation parameters for retry
    private var lastGenerationParams: TripGenerationParams?

    init(apiClient: TripPlanningAPIClient = .shared) {
        self.apiClient = apiClient
    }

    /// Whether an error is currently displayed
    var hasError: Bool {
        errorMessage != nil
    }

    /// Clear current error
    func clearError() {
        errorMessage = nil
    }

    /// Retry last failed generation
    @MainActor
    func retryLastGeneration() async {
        guard let params = lastGenerationParams else { return }
        await generatePlan(
            destinationCity: params.destinationCity,
            startDate: params.startDate,
            endDate: params.endDate,
            selectedInterests: params.selectedInterests,
            budgetLevel: params.budgetLevel,
            travellersCount: params.travellersCount,
            pace: params.pace
        )
    }

    /// Refresh itinerary after authentication to unlock full content.
    @MainActor
    func refreshPlanAfterAuth() async -> Bool {
        return await refreshItinerary()
    }

    /// Refresh itinerary from backend (e.g., after day editing in AI Studio).
    @MainActor
    func refreshItinerary() async -> Bool {
        guard let existingPlan = plan else { return false }

        print("🔄 Refreshing itinerary for trip \(existingPlan.tripId)")

        isLoading = true
        defer { isLoading = false }

        do {
            let itinerary = try await apiClient.getItinerary(tripId: existingPlan.tripId.uuidString.lowercased())
            self.plan = itinerary.toTripPlan(using: existingPlan)

            // Initialize revisions for all days
            initializeRevisions()

            // Mark as having unsaved changes if loaded from saved trip
            if isLoadedFromSavedTrip {
                self.hasUnsavedChanges = true
            }

            print("✅ Itinerary refreshed successfully")
            return true
        } catch {
            print("❌ Failed to refresh itinerary: \(error)")
            self.errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "Не удалось обновить маршрут. Попробуйте ещё раз."
            return false
        }
    }

    // MARK: - Computed Properties

    /// Currently selected day from the plan
    var currentDay: TripDay? {
        guard let plan = plan,
              selectedDayIndex >= 0,
              selectedDayIndex < plan.days.count else { return nil }
        return plan.days[selectedDayIndex]
    }

    /// Activities for the currently selected day
    var currentDayActivities: [TripActivity] {
        currentDay?.activities ?? []
    }

    /// Activities with valid coordinates for the currently selected day
    var currentDayActivitiesWithCoordinates: [TripActivity] {
        currentDayActivities.filter { $0.hasCoordinates }
    }

    // MARK: - Backend Integration

    /// Generate trip plan using backend API
    @MainActor
    func generatePlan(
        destinationCity: String,
        startDate: Date,
        endDate: Date,
        selectedInterests: [String],
        budgetLevel: String,
        travellersCount: Int,
        pace: String = "medium"
    ) async {
        // Store parameters for potential retry
        lastGenerationParams = TripGenerationParams(
            destinationCity: destinationCity,
            startDate: startDate,
            endDate: endDate,
            selectedInterests: selectedInterests,
            budgetLevel: budgetLevel,
            travellersCount: travellersCount,
            pace: pace
        )

        isLoading = true
        errorMessage = nil

        defer { isLoading = false }

        print("🚀 Starting trip plan generation for \(destinationCity)")
        print("🔧 API Client: \(type(of: apiClient))")
        print("🔧 Base URL: \(AppConfig.baseURL)")

        do {
            // 1. Create trip request DTO
            let tripRequest = buildTripRequest(
                city: destinationCity,
                startDate: startDate,
                endDate: endDate,
                travelers: travellersCount,
                interests: selectedInterests,
                budget: budgetLevel,
                pace: pace
            )

            // 2. Create trip
            print("📝 Creating trip...")
            let tripResponse = try await apiClient.createTrip(tripRequest)
            print("✅ Trip created with ID: \(tripResponse.id)")

            // 3. Generate plan
            print("🗺️ Generating itinerary...")
            let itinerary = try await apiClient.planTrip(tripId: tripResponse.id)
            print("✅ Plan generated with \(itinerary.days.count) days")

            // 4. Fetch complete itinerary
            print("📋 Fetching complete itinerary...")
            let fullItinerary = try await apiClient.getItinerary(tripId: tripResponse.id)
            print("✅ Full itinerary fetched")

            // 5. Convert to TripPlan
            self.plan = fullItinerary.toTripPlan(
                destinationCity: destinationCity,
                budget: budgetLevel,
                interests: selectedInterests,
                travelersCount: travellersCount,
                expectedStartDate: startDate,
                expectedEndDate: endDate
            )

            // Initialize revisions for all days
            initializeRevisions()

            print("🎉 Trip plan successfully generated!")

        } catch {
            print("❌ Raw error: \(error)")
            print("❌ Error type: \(type(of: error))")
            if let apiError = error as? APIError {
                print("❌ APIError details: \(apiError)")
            }
            if let apiError = error as? APIError, case .paywallRequired = apiError {
                if let params = lastGenerationParams ?? buildParamsFromPlan() {
                    pendingIntent = .generateTrip(params)
                }
                isShowingPaywall = true
            } else {
                self.errorMessage = (error as? LocalizedError)?.errorDescription
                    ?? "Что-то пошло не так. Попробуйте ещё раз."
                print("❌ Error generating plan: \(self.errorMessage ?? "Unknown error")")
            }
        }
    }

    private func buildTripRequest(
        city: String,
        startDate: Date,
        endDate: Date,
        travelers: Int,
        interests: [String],
        budget: String,
        pace: String
    ) -> TripCreateRequestDTO {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        // Map budget level from Russian to backend format
        let backendBudget = mapBudgetToBackend(budget)

        return TripCreateRequestDTO(
            city: city,
            startDate: dateFormatter.string(from: startDate),
            endDate: dateFormatter.string(from: endDate),
            numTravelers: max(travelers, 1),
            pace: pace,
            budget: backendBudget,
            interests: interests,
            dailyRoutine: nil,  // Use backend defaults
            hotelLocation: nil,
            additionalPreferences: nil
        )
    }

    private func mapBudgetToBackend(_ budget: String) -> String {
        switch budget {
        case "Эконом":
            return "low"
        case "Премиум":
            return "high"
        default:
            return "medium"
        }
    }

    /// Update plan from chat (re-run planning pipeline for existing trip)
    /// Returns true if update succeeded, false otherwise
    @MainActor
    func updatePlanFromChat() async -> Bool {
        guard let currentPlan = plan else {
            errorMessage = "Нет активного маршрута для обновления"
            lastUpdateResult = .failure("Нет активного маршрута для обновления")
            return false
        }

        isLoading = true
        errorMessage = nil
        lastUpdateResult = .none

        defer { isLoading = false }

        print("🔄 Updating trip plan for trip: \(currentPlan.tripId)")

        do {
            // 1. Re-run planning pipeline for the same trip
            print("🗺️ Re-generating itinerary...")
            let tripIdString = currentPlan.tripId.uuidString
            let itinerary = try await apiClient.planTrip(tripId: tripIdString)
            print("✅ Plan regenerated with \(itinerary.days.count) days")

            // 2. Fetch complete updated itinerary
            print("📋 Fetching updated itinerary...")
            let fullItinerary = try await apiClient.getItinerary(tripId: tripIdString)
            print("✅ Full itinerary fetched")

            // 3. Convert to TripPlan (preserve existing metadata)
            self.plan = fullItinerary.toTripPlan(using: currentPlan)

            // Reinitialize revisions after rebuild
            initializeRevisions()

            lastUpdateResult = .success
            print("🎉 Trip plan successfully updated!")
            return true

        } catch {
            let errorMsg = (error as? LocalizedError)?.errorDescription
                ?? "Что-то пошло не так. Попробуйте ещё раз."
            if let apiError = error as? APIError, case .paywallRequired = apiError {
                if let params = lastGenerationParams ?? buildParamsFromPlan() {
                    pendingIntent = .generateTrip(params)
                }
                isShowingPaywall = true
                lastUpdateResult = .failure(errorMsg)
                return false
            } else {
                self.errorMessage = errorMsg
                lastUpdateResult = .failure(errorMsg)
                print("❌ Error updating plan: \(errorMsg)")
                return false
            }
        }
    }

    private func buildParamsFromPlan() -> TripGenerationParams? {
        guard let plan = plan else { return nil }
        let interests = plan.interestsSummary
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
        return TripGenerationParams(
            destinationCity: plan.destinationCity,
            startDate: plan.startDate,
            endDate: plan.endDate,
            selectedInterests: interests,
            budgetLevel: mapComfortToBudget(plan.comfortLevel),
            travellersCount: plan.travellersCount,
            pace: "medium"
        )
    }

    private func mapComfortToBudget(_ comfort: String) -> String {
        switch comfort.lowercased() {
        case "эконом":
            return "low"
        case "премиум":
            return "high"
        default:
            return "medium"
        }
    }

    // MARK: - Local Activity Replacement (UX-only, no backend)

    /// Replace an activity at a specific position with a new one.
    /// This is a local-only operation for the "Replace place" UX flow.
    @MainActor
    func replaceActivity(at dayIndex: Int, activityIndex: Int, with newActivity: TripActivity) {
        guard var currentPlan = plan,
              dayIndex >= 0,
              dayIndex < currentPlan.days.count,
              activityIndex >= 0,
              activityIndex < currentPlan.days[dayIndex].activities.count else {
            return
        }

        // Create a mutable copy of the day's activities
        var updatedActivities = currentPlan.days[dayIndex].activities
        updatedActivities[activityIndex] = newActivity

        // Create a new TripDay with the updated activities
        let updatedDay = TripDay(
            index: currentPlan.days[dayIndex].index,
            date: currentPlan.days[dayIndex].date,
            title: currentPlan.days[dayIndex].title,
            summary: currentPlan.days[dayIndex].summary,
            activities: updatedActivities
        )

        // Create a mutable copy of the days array
        var updatedDays = currentPlan.days
        updatedDays[dayIndex] = updatedDay

        // Create a new TripPlan with the updated days
        let updatedPlan = TripPlan(
            tripId: currentPlan.tripId,
            destinationCity: currentPlan.destinationCity,
            startDate: currentPlan.startDate,
            endDate: currentPlan.endDate,
            days: updatedDays,
            travellersCount: currentPlan.travellersCount,
            comfortLevel: currentPlan.comfortLevel,
            interestsSummary: currentPlan.interestsSummary,
            tripSummary: currentPlan.tripSummary,
            isLocked: currentPlan.isLocked,
            cityPhotoReference: currentPlan.cityPhotoReference
        )

        // Update the plan
        self.plan = updatedPlan

        // Mark as having unsaved changes
        self.hasUnsavedChanges = true

        print("🔄 Activity replaced at day \(dayIndex), position \(activityIndex): \(newActivity.title)")
    }

    // MARK: - Backend Place Replacement

    /// Apply place replacement to backend and update local plan with travel data
    @MainActor
    func applyReplacementToBackend(
        tripId: String,
        dayIndex: Int,
        blockIndex: Int,
        oldPlaceId: String,
        newPlaceId: String,
        currentRevision: Int
    ) async throws -> ReplacementAppliedResponseDTO {
        print("🔄 Applying replacement to backend: trip=\(tripId), day=\(dayIndex), block=\(blockIndex)")

        // Create request
        let request = ApplyReplacementRequestDTO(
            dayIndex: dayIndex,
            blockIndex: blockIndex,
            oldPlaceId: oldPlaceId,
            newPlaceId: newPlaceId,
            idempotencyKey: UUID().uuidString,
            clientRouteVersion: currentRevision
        )

        // Call API
        let apiClient = TripPlanningAPIClient.shared
        let response = try await apiClient.applyReplacement(
            tripId: tripId,
            request: request
        )

        if response.success {
            print("✅ Replacement applied on backend, updating local plan with travel data")

            // Update local plan with backend data (including new travel times/distances)
            updateLocalPlanWithBackendData(
                dayIndex: dayIndex,
                blockIndex: blockIndex,
                updatedBlock: response.updatedBlock
            )

            // Update revision number for this day
            updateRevision(forDay: dayIndex, newRevision: response.routeVersion)

            // Mark as saved (changes persisted to backend)
            hasUnsavedChanges = false

            print("✅ Local plan updated with new travel data")
        } else {
            print("⚠️ Replacement response indicated failure")
        }

        return response
    }

    /// Update local plan with data from backend apply response
    private func updateLocalPlanWithBackendData(
        dayIndex: Int,
        blockIndex: Int,
        updatedBlock: [String: AnyCodable]
    ) {
        guard var currentPlan = plan,
              dayIndex >= 0,
              dayIndex < currentPlan.days.count,
              blockIndex >= 0,
              blockIndex < currentPlan.days[dayIndex].activities.count else {
            print("⚠️ Invalid indices for updating local plan")
            return
        }

        // Extract POI data from updatedBlock
        guard let poiDict = updatedBlock["poi"]?.value as? [String: Any] else {
            print("⚠️ No POI data in updated block")
            return
        }

        // Extract travel data
        let travelTimeMinutes = updatedBlock["travel_time_from_prev"]?.value as? Int
        let travelDistanceMeters = updatedBlock["travel_distance_meters"]?.value as? Int

        // Get current activity to preserve some fields
        let currentActivity = currentPlan.days[dayIndex].activities[blockIndex]

        // Create updated activity with new POI and travel data
        let updatedActivity = TripActivity(
            id: currentActivity.id,
            time: currentActivity.time,
            endTime: currentActivity.endTime,
            title: poiDict["name"] as? String ?? currentActivity.title,
            description: currentActivity.description,
            category: mapCategoryFromBackend(poiDict["category"] as? String ?? "other"),
            address: poiDict["location"] as? String ?? currentActivity.address,
            note: currentActivity.note,
            latitude: poiDict["lat"] as? Double ?? currentActivity.latitude,
            longitude: poiDict["lon"] as? Double ?? currentActivity.longitude,
            travelPolyline: currentActivity.travelPolyline,  // Keep existing polyline for now
            rating: poiDict["rating"] as? Double,
            tags: poiDict["tags"] as? [String],
            poiId: poiDict["poi_id"] as? String,
            travelTimeMinutes: travelTimeMinutes,
            travelDistanceMeters: travelDistanceMeters
        )

        // Update the plan
        var updatedActivities = currentPlan.days[dayIndex].activities
        updatedActivities[blockIndex] = updatedActivity

        let updatedDay = TripDay(
            index: currentPlan.days[dayIndex].index,
            date: currentPlan.days[dayIndex].date,
            title: currentPlan.days[dayIndex].title,
            summary: currentPlan.days[dayIndex].summary,
            activities: updatedActivities
        )

        var updatedDays = currentPlan.days
        updatedDays[dayIndex] = updatedDay

        let updatedPlan = TripPlan(
            tripId: currentPlan.tripId,
            destinationCity: currentPlan.destinationCity,
            startDate: currentPlan.startDate,
            endDate: currentPlan.endDate,
            days: updatedDays,
            travellersCount: currentPlan.travellersCount,
            comfortLevel: currentPlan.comfortLevel,
            interestsSummary: currentPlan.interestsSummary,
            tripSummary: currentPlan.tripSummary,
            isLocked: currentPlan.isLocked,
            cityPhotoReference: currentPlan.cityPhotoReference
        )

        self.plan = updatedPlan

        print("📏 Updated activity with travel: \(travelTimeMinutes ?? 0) min, \(travelDistanceMeters ?? 0) m")
    }

    /// Map backend category string to iOS category
    private func mapCategoryFromBackend(_ category: String) -> TripActivityCategory {
        switch category.lowercased() {
        case "restaurant", "cafe", "food":
            return .food
        case "museum":
            return .museum
        case "attraction", "viewpoint":
            return .viewpoint
        case "park", "walk":
            return .walk
        case "nightlife", "bar", "club":
            return .nightlife
        default:
            return .other
        }
    }

    // MARK: - Revision Tracking

    /// Initialize revisions for all days in the plan (start at 1)
    private func initializeRevisions() {
        guard let plan = plan else { return }

        dayRevisions.removeAll()
        for dayIndex in 0..<plan.days.count {
            dayRevisions[dayIndex] = 1
        }

        print("📝 Initialized revisions for \(plan.days.count) days")
    }

    /// Get current revision for a day
    func getCurrentRevision(forDay dayIndex: Int) -> Int {
        return dayRevisions[dayIndex] ?? 1
    }

    /// Update revision after successful backend operation
    private func updateRevision(forDay dayIndex: Int, newRevision: Int) {
        dayRevisions[dayIndex] = newRevision
        print("📝 Updated revision for day \(dayIndex): \(newRevision)")
    }

}
