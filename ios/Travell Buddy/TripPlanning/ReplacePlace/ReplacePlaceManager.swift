//
//  ReplacePlaceManager.swift
//  Travell Buddy
//
//  Manages the state machine for the "Replace place" UX flow.
//

import Foundation
import SwiftUI

// MARK: - Replace Place State

/// Represents a replacement option shown in the bottom sheet
struct ReplacementOption: Identifiable {
    let id: UUID
    let title: String
    let subtitle: String
    let category: TripActivityCategory
    let rating: Double?
    let distance: String
    let tags: [String]?
    let address: String?

    // Fields to create a TripActivity from this option
    let poiId: String?
    let latitude: Double?
    let longitude: Double?
}

/// State machine for the replace place flow
enum ReplacePlaceState: Equatable {
    case idle
    case finding(activityId: UUID)
    case selecting(activityId: UUID, options: [ReplacementOption])
    case applying(activityId: UUID, selected: ReplacementOption)
    case error(activityId: UUID, message: String)

    static func == (lhs: ReplacePlaceState, rhs: ReplacePlaceState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle):
            return true
        case (.finding(let lhsId), .finding(let rhsId)):
            return lhsId == rhsId
        case (.selecting(let lhsId, _), .selecting(let rhsId, _)):
            return lhsId == rhsId
        case (.applying(let lhsId, _), .applying(let rhsId, _)):
            return lhsId == rhsId
        case (.error(let lhsId, _), .error(let rhsId, _)):
            return lhsId == rhsId
        default:
            return false
        }
    }

    var activeActivityId: UUID? {
        switch self {
        case .idle:
            return nil
        case .finding(let id), .selecting(let id, _), .applying(let id, _), .error(let id, _):
            return id
        }
    }

    var isShowingSheet: Bool {
        if case .selecting = self { return true }
        return false
    }
}

// MARK: - Replace Place Manager

@MainActor
final class ReplacePlaceManager: ObservableObject {
    @Published private(set) var state: ReplacePlaceState = .idle
    @Published private(set) var recentlyReplacedActivityId: UUID?
    @Published var errorMessage: String?

    private var findingTask: Task<Void, Never>?
    private var badgeDismissTask: Task<Void, Never>?

    /// The currently displayed replacement options (for sheet binding)
    var currentOptions: [ReplacementOption] {
        if case .selecting(_, let options) = state {
            return options
        }
        return []
    }

    /// Whether the bottom sheet should be shown
    var isShowingSheet: Bool {
        state.isShowingSheet
    }

    /// Check if a specific activity is currently in the replace flow
    func isActivityInReplaceFlow(_ activityId: UUID) -> Bool {
        return state.activeActivityId == activityId
    }

    /// Check if a specific activity is in the "finding" state
    func isActivityFinding(_ activityId: UUID) -> Bool {
        if case .finding(let id) = state {
            return id == activityId
        }
        return false
    }

    /// Start the replace flow for an activity
    func startReplace(
        for activity: TripActivity,
        tripId: String,
        dayIndex: Int,
        stopIndex: Int
    ) {
        // ✅ Protection against duplicate calls - check state instead of task
        guard case .idle = state else {
            print("⚠️ Replace flow already in progress (state: \(state)), ignoring duplicate call")
            return
        }

        // Cancel any existing flow
        cancelCurrentFlow()

        // Transition to finding state
        state = .finding(activityId: activity.id)

        // Start async task to fetch real replacement options
        findingTask = Task {
            defer {
                // ✅ CRITICAL FIX: Clear task when done to allow next replacement
                self.findingTask = nil
                print("🧹 Cleared findingTask")
            }

            do {
                // Show shimmer for at least 0.6s for better UX
                try await Task.sleep(nanoseconds: 600_000_000)

                guard !Task.isCancelled else {
                    print("🚫 Finding task cancelled")
                    await MainActor.run { self.state = .idle }
                    return
                }

                // Build API request
                let request = ReplacementOptionsRequestDTO(
                    dayIndex: dayIndex,
                    blockIndex: stopIndex,
                    placeId: activity.poiId ?? "",
                    category: Self.mapCategoryToBackend(activity.category),
                    lat: activity.latitude ?? 0,
                    lng: activity.longitude ?? 0,
                    constraints: ReplacementConstraintsDTO(
                        maxDistanceM: 3000,
                        sameCategory: true,
                        excludeExistingInDay: true,
                        excludePlaceIds: []  // TODO: collect from day in ViewModel
                    ),
                    limit: 5
                )

                // Call API
                let apiClient = TripPlanningAPIClient.shared
                let response = try await apiClient.getReplacementOptions(
                    tripId: tripId,
                    request: request
                )

                guard !Task.isCancelled else {
                    print("🚫 Finding task cancelled after API call")
                    await MainActor.run { self.state = .idle }
                    return
                }

                // Convert DTOs to ReplacementOption
                let options = response.options.map { dto in
                    ReplacementOption(
                        id: UUID(),
                        title: dto.name,
                        subtitle: dto.area ?? "",
                        category: Self.mapCategoryFromBackend(dto.category),
                        rating: dto.rating,
                        distance: Self.formatDistance(dto.distanceM),
                        tags: dto.tags,
                        address: dto.address,
                        poiId: dto.placeId,
                        latitude: dto.lat,
                        longitude: dto.lng
                    )
                }

                // Check if we got any options
                if options.isEmpty {
                    print("⚠️ No replacement options found")
                    await MainActor.run {
                        self.errorMessage = "Альтернативы не найдены. Попробуйте позже."
                        self.state = .error(activityId: activity.id, message: self.errorMessage!)
                    }
                } else {
                    // Transition to selecting state
                    print("✅ Got \(options.count) replacement options, transitioning to selecting state")
                    await MainActor.run {
                        self.state = .selecting(activityId: activity.id, options: options)
                    }
                }

            } catch {
                print("❌ Error fetching replacement options: \(error)")

                // Determine error message based on error type
                let message: String
                if let apiError = error as? APIError {
                    switch apiError {
                    case .networkError:
                        message = "Не удалось загрузить альтернативы. Проверьте подключение к интернету."
                    case .httpError(let statusCode, _):
                        if statusCode == 409 {
                            message = "День изменился. Обновите страницу."
                        } else {
                            message = "Ошибка сервера. Попробуйте позже."
                        }
                    case .decodingError:
                        message = "Ошибка обработки данных."
                    default:
                        message = "Не удалось загрузить альтернативы."
                    }
                } else {
                    message = "Не удалось загрузить альтернативы."
                }

                await MainActor.run {
                    self.errorMessage = message
                    self.state = .error(activityId: activity.id, message: message)
                }
            }
        }
    }

    /// User selected a replacement option
    func selectOption(_ option: ReplacementOption, onReplace: @escaping (UUID, ReplacementOption) -> Void) {
        guard case .selecting(let activityId, _) = state else {
            print("⚠️ Cannot select option - not in selecting state (current: \(state))")
            return
        }

        print("👆 User selected replacement option: \(option.title)")

        // Transition to applying state
        state = .applying(activityId: activityId, selected: option)

        // Perform the replacement callback
        onReplace(activityId, option)

        // Show "Replaced" badge briefly then reset
        recentlyReplacedActivityId = activityId
        state = .idle
        print("✅ Transitioned to idle, ready for next replacement")

        // Clear badge after 1.5 seconds
        badgeDismissTask?.cancel()
        badgeDismissTask = Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            recentlyReplacedActivityId = nil
        }
    }

    /// Cancel the current replace flow
    func cancel() {
        print("🚫 Cancelling replace flow (current state: \(state))")
        cancelCurrentFlow()
        state = .idle
        print("✅ Reset to idle after cancel")
    }

    /// Dismiss the sheet (same as cancel when in selecting state)
    func dismissSheet() {
        if case .selecting = state {
            print("📋 Dismissing sheet, cancelling flow")
            cancel()
        }
    }

    private func cancelCurrentFlow() {
        if findingTask != nil {
            print("🧹 Cancelling and clearing findingTask")
            findingTask?.cancel()
            findingTask = nil
        }
    }

    // MARK: - Helper Methods

    /// Map iOS category to backend category string
    private static func mapCategoryToBackend(_ category: TripActivityCategory) -> String {
        switch category {
        case .food:
            return "restaurant"
        case .museum:
            return "museum"
        case .viewpoint:
            return "attraction"
        case .walk:
            return "park"
        case .nightlife:
            return "nightlife"
        case .other:
            return "other"
        }
    }

    /// Map backend category string to iOS category
    private static func mapCategoryFromBackend(_ category: String) -> TripActivityCategory {
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

    /// Format distance in meters to readable string
    private static func formatDistance(_ meters: Int) -> String {
        if meters < 1000 {
            return "\(meters) м"
        } else {
            let km = Double(meters) / 1000.0
            return String(format: "%.1f км", km)
        }
    }
}

// MARK: - Mock Replacement Generator

enum MockReplacementGenerator {

    /// Generates mock replacement options similar to the given activity
    static func generateAlternatives(for activity: TripActivity, count: Int) -> [ReplacementOption] {
        let templates = getTemplates(for: activity.category)

        // Shuffle and pick 'count' items
        let selectedTemplates = templates.shuffled().prefix(count)

        return selectedTemplates.map { template in
            ReplacementOption(
                id: UUID(),
                title: template.name,
                subtitle: template.area,
                category: activity.category,
                rating: template.rating,
                distance: template.distance,
                tags: template.tags,
                address: template.address,
                poiId: nil,
                latitude: activity.latitude.map { $0 + Double.random(in: -0.01...0.01) },
                longitude: activity.longitude.map { $0 + Double.random(in: -0.01...0.01) }
            )
        }
    }

    private struct MockTemplate {
        let name: String
        let area: String
        let rating: Double?
        let distance: String
        let tags: [String]?
        let address: String?
    }

    private static func getTemplates(for category: TripActivityCategory) -> [MockTemplate] {
        switch category {
        case .food:
            return [
                MockTemplate(name: "Le Petit Bistro", area: "Марэ", rating: 4.6, distance: "350 м", tags: ["Французская", "Бистро"], address: "12 Rue des Rosiers"),
                MockTemplate(name: "Cafe de Flore", area: "Сен-Жермен", rating: 4.4, distance: "500 м", tags: ["Кафе", "Классика"], address: "172 Boulevard Saint-Germain"),
                MockTemplate(name: "L'As du Fallafel", area: "Марэ", rating: 4.7, distance: "200 м", tags: ["Ближневосточная", "Быстро"], address: "34 Rue des Rosiers"),
                MockTemplate(name: "Breizh Cafe", area: "Марэ", rating: 4.5, distance: "450 м", tags: ["Блинная", "Бретонская"], address: "109 Rue Vieille du Temple"),
                MockTemplate(name: "Pink Mamma", area: "Пигаль", rating: 4.3, distance: "800 м", tags: ["Итальянская", "Модная"], address: "20 Rue de Douai"),
                MockTemplate(name: "Bouillon Chartier", area: "Гранд Бульвар", rating: 4.2, distance: "1.2 км", tags: ["Традиционная", "Историческая"], address: "7 Rue du Faubourg Montmartre"),
            ]
        case .museum:
            return [
                MockTemplate(name: "Музей Орсе", area: "Сен-Жермен", rating: 4.8, distance: "600 м", tags: ["Импрессионизм", "Искусство"], address: "1 Rue de la Legion d'Honneur"),
                MockTemplate(name: "Центр Помпиду", area: "Бобур", rating: 4.6, distance: "450 м", tags: ["Современное искусство", "Архитектура"], address: "Place Georges-Pompidou"),
                MockTemplate(name: "Музей Родена", area: "Инвалиды", rating: 4.7, distance: "1.1 км", tags: ["Скульптура", "Сад"], address: "77 Rue de Varenne"),
                MockTemplate(name: "Музей Пикассо", area: "Марэ", rating: 4.5, distance: "300 м", tags: ["Модернизм", "Пикассо"], address: "5 Rue de Thorigny"),
                MockTemplate(name: "Малый дворец", area: "Елисейские поля", rating: 4.4, distance: "900 м", tags: ["Бесплатный", "Классика"], address: "Avenue Winston Churchill"),
                MockTemplate(name: "Музей Оранжери", area: "Тюильри", rating: 4.6, distance: "700 м", tags: ["Моне", "Кувшинки"], address: "Jardin des Tuileries"),
            ]
        case .viewpoint:
            return [
                MockTemplate(name: "Монмартр", area: "18-й округ", rating: 4.7, distance: "2.5 км", tags: ["Панорама", "Базилика"], address: "35 Rue du Chevalier de la Barre"),
                MockTemplate(name: "Башня Монпарнас", area: "Монпарнас", rating: 4.3, distance: "3 км", tags: ["Небоскреб", "360°"], address: "33 Avenue du Maine"),
                MockTemplate(name: "Галерея Лафайет", area: "Опера", rating: 4.2, distance: "1.8 км", tags: ["Бесплатно", "Терраса"], address: "40 Boulevard Haussmann"),
                MockTemplate(name: "Триумфальная арка", area: "Елисейские поля", rating: 4.8, distance: "2.2 км", tags: ["Историческая", "Панорама"], address: "Place Charles de Gaulle"),
                MockTemplate(name: "Институт арабского мира", area: "5-й округ", rating: 4.1, distance: "1.5 км", tags: ["Архитектура", "Терраса"], address: "1 Rue des Fosses Saint-Bernard"),
            ]
        case .walk:
            return [
                MockTemplate(name: "Сад Тюильри", area: "1-й округ", rating: 4.6, distance: "800 м", tags: ["Парк", "Скульптуры"], address: "Place de la Concorde"),
                MockTemplate(name: "Люксембургский сад", area: "6-й округ", rating: 4.8, distance: "1.4 км", tags: ["Парк", "Фонтаны"], address: "Rue de Medicis"),
                MockTemplate(name: "Канал Сен-Мартен", area: "10-й округ", rating: 4.5, distance: "2 км", tags: ["Набережная", "Мосты"], address: "Quai de Jemmapes"),
                MockTemplate(name: "Остров Сите", area: "4-й округ", rating: 4.7, distance: "500 м", tags: ["Историческое", "Сена"], address: "Ile de la Cite"),
                MockTemplate(name: "Крытые переходы", area: "2-й округ", rating: 4.4, distance: "1.1 км", tags: ["Шопинг", "Архитектура"], address: "Passage des Panoramas"),
            ]
        case .nightlife:
            return [
                MockTemplate(name: "Le Baron", area: "8-й округ", rating: 4.3, distance: "1.5 км", tags: ["Клуб", "Электро"], address: "6 Avenue Marceau"),
                MockTemplate(name: "Experimental Cocktail Club", area: "2-й округ", rating: 4.6, distance: "700 м", tags: ["Коктейли", "Speakeasy"], address: "37 Rue Saint-Sauveur"),
                MockTemplate(name: "Rosa Bonheur", area: "Бют-Шомон", rating: 4.4, distance: "3 км", tags: ["Гуанетта", "Терраса"], address: "Parc des Buttes-Chaumont"),
                MockTemplate(name: "Le Perchoir", area: "11-й округ", rating: 4.5, distance: "2.5 км", tags: ["Руфтоп", "Коктейли"], address: "14 Rue Crespin du Gast"),
                MockTemplate(name: "Wanderlust", area: "13-й округ", rating: 4.2, distance: "2.8 км", tags: ["Сена", "Танцпол"], address: "32 Quai d'Austerlitz"),
            ]
        case .other:
            return [
                MockTemplate(name: "Шопинг на Марэ", area: "4-й округ", rating: 4.4, distance: "400 м", tags: ["Бутики", "Винтаж"], address: "Rue des Francs-Bourgeois"),
                MockTemplate(name: "Блошиный рынок", area: "Сент-Уан", rating: 4.3, distance: "5 км", tags: ["Антиквариат", "Винтаж"], address: "Marche aux Puces de Saint-Ouen"),
                MockTemplate(name: "Латинский квартал", area: "5-й округ", rating: 4.5, distance: "1 км", tags: ["Студенческий", "Кафе"], address: "Place de la Sorbonne"),
                MockTemplate(name: "Бато-Муш", area: "Сена", rating: 4.2, distance: "1.2 км", tags: ["Круиз", "Достопримечательности"], address: "Port de la Conference"),
                MockTemplate(name: "Катакомбы", area: "14-й округ", rating: 4.6, distance: "3.5 км", tags: ["Подземелье", "История"], address: "1 Avenue du Colonel Henri Rol-Tanguy"),
            ]
        }
    }
}
