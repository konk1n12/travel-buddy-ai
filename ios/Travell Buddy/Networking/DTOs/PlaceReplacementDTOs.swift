//
//  PlaceReplacementDTOs.swift
//  Travell Buddy
//
//  DTOs for place replacement API endpoints.
//
//  Note: AnyCodable is defined in SavedTripsDTOs.swift
//

import Foundation

// MARK: - Request DTOs

struct ReplacementConstraintsDTO: Codable {
    let maxDistanceM: Int?
    let sameCategory: Bool?
    let excludeExistingInDay: Bool?
    let excludePlaceIds: [String]?

    enum CodingKeys: String, CodingKey {
        case maxDistanceM = "max_distance_m"
        case sameCategory = "same_category"
        case excludeExistingInDay = "exclude_existing_in_day"
        case excludePlaceIds = "exclude_place_ids"
    }
}

struct ReplacementOptionsRequestDTO: Codable {
    let dayIndex: Int
    let blockIndex: Int
    let placeId: String
    let category: String
    let lat: Double
    let lng: Double
    let constraints: ReplacementConstraintsDTO?
    let limit: Int?

    enum CodingKeys: String, CodingKey {
        case dayIndex = "day_index"
        case blockIndex = "block_index"
        case placeId = "place_id"
        case category
        case lat
        case lng
        case constraints
        case limit
    }
}

struct ApplyReplacementRequestDTO: Codable {
    let dayIndex: Int
    let blockIndex: Int
    let oldPlaceId: String
    let newPlaceId: String
    let idempotencyKey: String
    let clientRouteVersion: Int?

    enum CodingKeys: String, CodingKey {
        case dayIndex = "day_index"
        case blockIndex = "block_index"
        case oldPlaceId = "old_place_id"
        case newPlaceId = "new_place_id"
        case idempotencyKey = "idempotency_key"
        case clientRouteVersion = "client_route_version"
    }
}

// MARK: - Response DTOs

struct ReplacementOptionDTO: Codable, Identifiable {
    let placeId: String
    let name: String
    let category: String
    let area: String?
    let distanceM: Int
    let rating: Double?
    let reviewsCount: Int?
    let photoUrl: String?
    let reason: String?
    let lat: Double
    let lng: Double
    let address: String?
    let tags: [String]?

    var id: String { placeId }

    enum CodingKeys: String, CodingKey {
        case placeId = "place_id"
        case name
        case category
        case area
        case distanceM = "distance_m"
        case rating
        case reviewsCount = "reviews_count"
        case photoUrl = "photo_url"
        case reason
        case lat
        case lng
        case address
        case tags
    }
}

struct ReplacementOptionsResponseDTO: Codable {
    let options: [ReplacementOptionDTO]
    let requestId: String

    enum CodingKeys: String, CodingKey {
        case options
        case requestId = "request_id"
    }
}

struct ReplacementAppliedResponseDTO: Codable {
    let success: Bool
    let updatedBlock: [String: AnyCodable]
    let routeVersion: Int
    let message: String?

    enum CodingKeys: String, CodingKey {
        case success
        case updatedBlock = "updated_block"
        case routeVersion = "route_version"
        case message
    }
}
