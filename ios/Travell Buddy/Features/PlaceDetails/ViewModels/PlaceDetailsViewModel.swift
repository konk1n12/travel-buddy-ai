//
//  PlaceDetailsViewModel.swift
//  Travell Buddy
//
//  ViewModel for Google Places-backed place details.
//

import Foundation
import SwiftUI
import CoreLocation

enum PlaceDetailsState {
    case idle
    case loading
    case loaded(PlaceDetailsViewData)
    case error(String)
}

@MainActor
final class PlaceDetailsViewModel: ObservableObject {
    @Published private(set) var state: PlaceDetailsState = .idle
    @Published var isSaved: Bool = false
    @Published var isInRoute: Bool = false
    @Published var isMustVisit: Bool = false
    @Published var noteText: String = ""
    @Published private(set) var distanceKm: Double?
    @Published private(set) var etaMinutes: Int?

    let placeId: String
    let fallbackPlace: Place?

    private let service: PlaceDetailsServiceProtocol
    private var loadTask: Task<Void, Never>?

    init(placeId: String, fallbackPlace: Place? = nil, service: PlaceDetailsServiceProtocol = PlaceDetailsService.shared) {
        self.placeId = placeId
        self.fallbackPlace = fallbackPlace
        self.service = service
        self.noteText = fallbackPlace?.note ?? ""
        self.isInRoute = fallbackPlace != nil
    }

    var details: PlaceDetailsViewData? {
        if case .loaded(let details) = state {
            return details
        }
        return nil
    }

    var isLoading: Bool {
        if case .loading = state {
            return true
        }
        return false
    }

    var errorMessage: String? {
        if case .error(let message) = state {
            return message
        }
        return nil
    }

    func loadDetails() {
        if case .loading = state {
            return
        }

        loadTask?.cancel()
        state = .loading

        loadTask = Task {
            do {
                let dto = try await service.fetchDetails(for: placeId)
                let viewData = dto.toViewData(apiBaseURL: AppConfig.baseURL)
                guard !Task.isCancelled else { return }
                state = .loaded(viewData)
            } catch {
                guard !Task.isCancelled else { return }
                state = .error(error.localizedDescription)
            }
        }
    }

    func retry() {
        loadDetails()
    }

    func updateDistance(from location: CLLocation?) {
        guard let location = location else { return }
        let target = details?.coordinate ?? fallbackPlace?.coordinate
        guard let target else { return }
        let distance = DistanceETA.distanceKm(from: location.coordinate, to: target)
        distanceKm = distance
        etaMinutes = DistanceETA.estimateETA(distanceKm: distance, mode: .walking)
    }

    func highlightChips() -> [String] {
        guard let details else {
            return GooglePlaceTypeMapper.highlightChips(types: fallbackPlace?.tags ?? [], rating: nil, reviewsCount: nil)
        }
        return GooglePlaceTypeMapper.highlightChips(
            types: details.types,
            rating: details.rating,
            reviewsCount: details.reviewsCount
        )
    }

    func estimatedVisitDurationText() -> String? {
        let types = details?.types ?? fallbackPlace?.tags ?? []
        guard let duration = EstimatedDurationMapper.estimate(for: types) else { return nil }
        return duration
    }
}

enum EstimatedDurationMapper {
    static func estimate(for types: [String]) -> String? {
        if types.contains("restaurant") || types.contains("cafe") || types.contains("bar") {
            return "~1 ч"
        }
        if types.contains("museum") {
            return "~1 ч 30 мин"
        }
        if types.contains("park") {
            return "~1 ч"
        }
        if types.contains("tourist_attraction") {
            return "~1 ч"
        }
        return nil
    }
}
