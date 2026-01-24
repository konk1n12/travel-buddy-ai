//
//  AIStudioViewModel.swift
//  Travell Buddy
//
//  ViewModel for AI Studio day editing with pending changes tracking.
//

import Foundation
import Combine

// MARK: - Domain Models

enum StudioTempo: String, CaseIterable, Identifiable {
    case low = "low"
    case medium = "medium"
    case high = "high"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .low: return "Низкий"
        case .medium: return "Средний"
        case .high: return "Высокий"
        }
    }

    var icon: String {
        switch self {
        case .low: return "tortoise"
        case .medium: return "figure.walk"
        case .high: return "hare"
        }
    }
}

enum StudioBudget: String, CaseIterable, Identifiable {
    case low = "low"
    case medium = "medium"
    case high = "high"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .low: return "$"
        case .medium: return "$$"
        case .high: return "$$$"
        }
    }
}

enum DayPreset: String, CaseIterable, Identifiable {
    case overview = "overview"
    case food = "food"
    case walks = "walks"
    case avoidCrowds = "avoid_crowds"
    case art = "art"
    case architecture = "architecture"
    case cozy = "cozy"
    case nightlife = "nightlife"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: return "Обзорно"
        case .food: return "Еда"
        case .walks: return "Прогулки"
        case .avoidCrowds: return "Без толп"
        case .art: return "Искусство"
        case .architecture: return "Архитектура"
        case .cozy: return "Уютно"
        case .nightlife: return "Ночная"
        }
    }

    var icon: String {
        switch self {
        case .overview: return "binoculars"
        case .food: return "fork.knife"
        case .walks: return "figure.walk"
        case .avoidCrowds: return "person.2.slash"
        case .art: return "paintpalette"
        case .architecture: return "building.columns"
        case .cozy: return "cup.and.saucer"
        case .nightlife: return "moon.stars"
        }
    }
}

// MARK: - Pending Change Types

enum PendingChangeType: Equatable, Hashable {
    case updateSettings
    case setPreset(DayPreset?)
    case addPlace(placeId: String, placement: PlacePlacement)
    case replacePlace(placeId: String)  // NEW (2026-01-24): Mark for replacement (backend auto-selects)
    case removePlace(placeId: String)
    case addWishMessage(text: String)
}

enum PlacePlacement: Equatable, Hashable {
    case auto
    case inSlot(slotIndex: Int)
    case atTime(hour: Int, minute: Int)
}

struct PendingChange: Identifiable, Equatable, Hashable {
    let id: UUID
    let type: PendingChangeType
    let createdAt: Date

    init(type: PendingChangeType) {
        self.id = UUID()
        self.type = type
        self.createdAt = Date()
    }
}

// MARK: - Place Models

struct StudioPlace: Identifiable, Equatable {
    let id: String
    let name: String
    let latitude: Double
    let longitude: Double
    let timeStart: String
    let timeEnd: String
    let category: String
    let rating: Double?
    let priceLevel: Int?
    let photoURL: URL?
    let address: String?
}

struct StudioSearchResult: Identifiable, Equatable {
    let id: String
    let name: String
    let category: String
    let rating: Double?
    let address: String?
    let photoURL: URL?
}

struct WishMessage: Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let text: String
    let createdAt: Date

    enum MessageRole: String {
        case user
        case assistant
    }
}

struct DayMetrics: Equatable {
    let distanceKm: Double
    let stepsEstimate: Int
    let placesCount: Int
    let walkingTimeMinutes: Int

    var formattedDistance: String {
        String(format: "%.1f км", distanceKm)
    }

    var formattedSteps: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return "\(formatter.string(from: NSNumber(value: stepsEstimate)) ?? "\(stepsEstimate)") шагов"
    }

    var formattedPlaces: String {
        "\(placesCount) мест"
    }
}

// MARK: - Server State

struct DayStudioState: Equatable {
    var places: [StudioPlace]
    var tempo: StudioTempo
    var startTime: Date
    var endTime: Date
    var budget: StudioBudget
    var preset: DayPreset?
    var aiSummary: String
    var metrics: DayMetrics
    var wishes: [WishMessage]
    var revision: Int

    static var empty: DayStudioState {
        DayStudioState(
            places: [],
            tempo: .medium,
            startTime: Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date(),
            endTime: Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date()) ?? Date(),
            budget: .medium,
            preset: nil,
            aiSummary: "",
            metrics: DayMetrics(distanceKm: 0, stepsEstimate: 0, placesCount: 0, walkingTimeMinutes: 0),
            wishes: [],
            revision: 0
        )
    }
}

// MARK: - ViewModel

@MainActor
final class AIStudioViewModel: ObservableObject {
    // MARK: - Published State

    // Server state (source of truth from backend)
    @Published var serverState: DayStudioState = .empty

    // Local editing state
    @Published var tempo: StudioTempo = .medium
    @Published var startTime: Date = Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()
    @Published var endTime: Date = Calendar.current.date(bySettingHour: 18, minute: 0, second: 0, of: Date()) ?? Date()
    @Published var budget: StudioBudget = .medium
    @Published var selectedPreset: DayPreset?

    // Wishes chat
    @Published var wishesThread: [WishMessage] = []
    @Published var wishInputText: String = ""

    // Place management
    @Published var searchQuery: String = ""
    @Published var searchResults: [StudioSearchResult] = []
    @Published var isSearching: Bool = false
    // Places marked for replacement (will show orange UI)
    @Published var markedForReplacement: Set<String> = []

    // Pending changes
    @Published var pendingChanges: [PendingChange] = []

    // UI State
    @Published var isLoading: Bool = false
    @Published var isApplying: Bool = false
    @Published var errorMessage: String?
    @Published var shouldDismiss: Bool = false

    // MARK: - Properties

    let tripId: UUID
    let dayId: Int
    let cityName: String
    let dayDate: Date
    var onChangesApplied: (() async -> Void)?

    var dirtyCount: Int {
        pendingChanges.count
    }

    var hasChanges: Bool {
        !pendingChanges.isEmpty
    }

    var timeWindowText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return "\(formatter.string(from: startTime))–\(formatter.string(from: endTime))"
    }

    var dayDateFormatted: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")
        formatter.dateFormat = "d MMMM, EEEE"
        return formatter.string(from: dayDate)
    }

    // MARK: - Init

    init(tripId: UUID, dayId: Int, cityName: String, dayDate: Date) {
        self.tripId = tripId
        self.dayId = dayId
        self.cityName = cityName
        self.dayDate = dayDate
    }

    // MARK: - Load Data

    func loadStudioData() async {
        isLoading = true
        errorMessage = nil

        do {
            let state = try await fetchStudioState()
            serverState = state
            syncLocalStateFromServer()
        } catch {
            errorMessage = "Не удалось загрузить данные: \(error.localizedDescription)"
        }

        isLoading = false
    }

    private func syncLocalStateFromServer() {
        tempo = serverState.tempo
        startTime = serverState.startTime
        endTime = serverState.endTime
        budget = serverState.budget
        selectedPreset = serverState.preset
        wishesThread = serverState.wishes
    }

    // MARK: - Settings Changes

    func updateTempo(_ newTempo: StudioTempo) {
        guard newTempo != tempo else { return }
        tempo = newTempo
        addSettingsChangeIfNeeded()
    }

    func updateStartTime(_ newTime: Date) {
        guard newTime != startTime else { return }
        startTime = newTime
        addSettingsChangeIfNeeded()
    }

    func updateEndTime(_ newTime: Date) {
        guard newTime != endTime else { return }
        endTime = newTime
        addSettingsChangeIfNeeded()
    }

    func updateBudget(_ newBudget: StudioBudget) {
        guard newBudget != budget else { return }
        budget = newBudget
        addSettingsChangeIfNeeded()
    }

    private func addSettingsChangeIfNeeded() {
        // Remove existing settings change and add new one
        pendingChanges.removeAll { change in
            if case .updateSettings = change.type { return true }
            return false
        }

        // Only add if different from server state
        if tempo != serverState.tempo ||
           startTime != serverState.startTime ||
           endTime != serverState.endTime ||
           budget != serverState.budget {
            pendingChanges.append(PendingChange(type: .updateSettings))
            print("📝 Added settings change. Total pending: \(pendingChanges.count)")
        } else {
            print("⚠️ Settings unchanged, not adding to pending")
        }
    }

    // MARK: - Preset Changes

    func selectPreset(_ preset: DayPreset?) {
        guard preset != selectedPreset else { return }
        selectedPreset = preset

        // Remove existing preset change
        pendingChanges.removeAll { change in
            if case .setPreset = change.type { return true }
            return false
        }

        // Only add if different from server state
        if preset != serverState.preset {
            pendingChanges.append(PendingChange(type: .setPreset(preset)))
            print("📝 Added preset change: \(preset?.rawValue ?? "nil"). Total pending: \(pendingChanges.count)")
        } else {
            print("⚠️ Preset unchanged, not adding to pending")
        }
    }

    // MARK: - Wishes Chat

    func sendWish() {
        let text = wishInputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        let message = WishMessage(
            id: UUID(),
            role: .user,
            text: text,
            createdAt: Date()
        )
        wishesThread.append(message)
        wishInputText = ""

        pendingChanges.append(PendingChange(type: .addWishMessage(text: text)))
    }

    // MARK: - Place Management

    func searchPlaces() async {
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            searchResults = []
            return
        }

        isSearching = true

        do {
            searchResults = try await performPlaceSearch(query: query)
        } catch {
            searchResults = []
        }

        isSearching = false
    }

    func addPlace(_ result: StudioSearchResult, placement: PlacePlacement) {
        pendingChanges.append(PendingChange(type: .addPlace(placeId: result.id, placement: placement)))
        print("📝 Added place: \(result.name). Total pending: \(pendingChanges.count)")
        searchQuery = ""
        searchResults = []
    }

    // NEW (2026-01-24): Mark place for replacement (backend will auto-select)
    func toggleMarkForReplacement(_ placeId: String) {
        if markedForReplacement.contains(placeId) {
            // Unmark
            markedForReplacement.remove(placeId)
            // Remove pending change if exists
            pendingChanges.removeAll { change in
                if case .replacePlace(let id) = change.type, id == placeId {
                    return true
                }
                return false
            }
            print("📝 Unmarked place for replacement: \(placeId). Total pending: \(pendingChanges.count)")
        } else {
            // Mark for replacement
            markedForReplacement.insert(placeId)
            pendingChanges.append(PendingChange(type: .replacePlace(placeId: placeId)))
            print("📝 Marked place for replacement: \(placeId). Total pending: \(pendingChanges.count)")
        }
    }

    func removePlace(_ placeId: String) {
        pendingChanges.append(PendingChange(type: .removePlace(placeId: placeId)))
        print("📝 Remove place: \(placeId). Total pending: \(pendingChanges.count)")
    }

    // MARK: - Apply / Reset

    func applyChanges() async {
        guard hasChanges else { return }

        print("🚀 Applying \(pendingChanges.count) pending changes to server")
        for (i, change) in pendingChanges.enumerated() {
            print("   Change \(i+1): \(change.type)")
        }

        isApplying = true
        errorMessage = nil

        do {
            let newState = try await submitChanges()
            serverState = newState
            pendingChanges.removeAll()
            syncLocalStateFromServer()

            print("✅ Changes applied successfully")

            // Notify parent to refresh itinerary
            if let onChangesApplied = onChangesApplied {
                print("🔄 Calling onChangesApplied callback to refresh itinerary")
                await onChangesApplied()
            } else {
                print("⚠️ No onChangesApplied callback set")
            }

            // Success - trigger dismiss after a short delay
            try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
            shouldDismiss = true
        } catch {
            print("❌ Failed to apply changes: \(error)")
            errorMessage = "Не удалось применить изменения: \(error.localizedDescription)"
        }

        isApplying = false
    }

    func resetChanges() {
        pendingChanges.removeAll()
        syncLocalStateFromServer()
        searchQuery = ""
        searchResults = []
        markedForReplacement.removeAll()
    }

    // MARK: - Pending Change Helpers

    func isPlacePendingRemoval(_ placeId: String) -> Bool {
        pendingChanges.contains { change in
            if case .removePlace(let id) = change.type {
                return id == placeId
            }
            return false
        }
    }

    func isPlacePendingReplacement(_ placeId: String) -> Bool {
        pendingChanges.contains { change in
            if case .replacePlace(let id) = change.type {
                return id == placeId
            }
            return false
        }
    }

    // MARK: - API Calls

    private let apiClient = TripPlanningAPIClient.shared

    private func fetchStudioState() async throws -> DayStudioState {
        let response = try await apiClient.getDayStudio(tripId: tripId, dayId: dayId)
        return response.toStudioState()
    }

    private func submitChanges() async throws -> DayStudioState {
        let changes = buildChangeDTOs()
        let request = ApplyChangesRequestDTO(
            baseRevision: serverState.revision,
            changes: changes
        )

        let response = try await apiClient.applyDayChanges(
            tripId: tripId,
            dayId: dayId,
            request: request
        )

        return response.toStudioState()
    }

    private func performPlaceSearch(query: String) async throws -> [StudioSearchResult] {
        let request = PlaceSearchRequestDTO(
            query: query,
            city: cityName,
            limit: 10
        )

        let response = try await apiClient.searchPlaces(request: request)
        return response.results.map { $0.toSearchResult() }
    }

    private func buildChangeDTOs() -> [DayChangeDTO] {
        var changes: [DayChangeDTO] = []

        for change in pendingChanges {
            switch change.type {
            case .updateSettings:
                let formatter = DateFormatter()
                formatter.dateFormat = "HH:mm"

                changes.append(DayChangeDTO(
                    type: "update_settings",
                    data: .updateSettings(
                        tempo: tempo.rawValue,
                        startTime: formatter.string(from: startTime),
                        endTime: formatter.string(from: endTime),
                        budget: budget.rawValue
                    )
                ))

            case .setPreset(let preset):
                changes.append(DayChangeDTO(
                    type: "set_preset",
                    data: .setPreset(preset?.rawValue)
                ))

            case .addPlace(let placeId, let placement):
                let placementDTO: PlacementDTO
                switch placement {
                case .auto:
                    placementDTO = .auto
                case .inSlot(let index):
                    placementDTO = .inSlot(index)
                case .atTime(let hour, let minute):
                    placementDTO = .atTime(hour: hour, minute: minute)
                }

                changes.append(DayChangeDTO(
                    type: "add_place",
                    data: .addPlace(placeId: placeId, placement: placementDTO)
                ))

            case .replacePlace(let placeId):
                // NEW (2026-01-24): Mark for replacement - backend auto-selects best alternative
                changes.append(DayChangeDTO(
                    type: "replace_place",
                    data: .replacePlace(from: placeId, to: nil)  // toId = nil triggers auto-selection
                ))

            case .removePlace(let placeId):
                changes.append(DayChangeDTO(
                    type: "remove_place",
                    data: .removePlace(placeId)
                ))

            case .addWishMessage(let text):
                changes.append(DayChangeDTO(
                    type: "add_wish_message",
                    data: .addWish(text)
                ))
            }
        }

        return changes
    }
}
