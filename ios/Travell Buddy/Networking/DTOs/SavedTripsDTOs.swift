//
//  SavedTripsDTOs.swift
//  Travell Buddy
//
//  DTOs for saved trips (bookmarks) endpoints.
//

import Foundation

// MARK: - Request DTOs

struct SaveTripRequestDTO: Codable {
    let tripId: String
    let cityName: String
    let startDate: String  // YYYY-MM-DD
    let endDate: String    // YYYY-MM-DD
    let heroImageUrl: String?
    let routeSnapshot: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case tripId = "trip_id"
        case cityName = "city_name"
        case startDate = "start_date"
        case endDate = "end_date"
        case heroImageUrl = "hero_image_url"
        case routeSnapshot = "route_snapshot"
    }
}

// MARK: - Response DTOs

struct SavedTripResponseDTO: Codable {
    let id: String
    let tripId: String
    let cityName: String
    let startDate: String  // YYYY-MM-DD
    let endDate: String    // YYYY-MM-DD
    let heroImageUrl: String?
    let alreadySaved: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case tripId = "trip_id"
        case cityName = "city_name"
        case startDate = "start_date"
        case endDate = "end_date"
        case heroImageUrl = "hero_image_url"
        case alreadySaved = "already_saved"
    }
}

struct SavedTripsListResponseDTO: Codable {
    let trips: [SavedTripResponseDTO]
    let total: Int
}

// MARK: - Domain Models

struct SavedTripCard: Identifiable, Equatable {
    let id: UUID
    let tripId: UUID
    let cityName: String
    let startDate: Date
    let endDate: Date
    let heroImageUrl: String?
    let alreadySaved: Bool

    /// Date range formatted as "12-18 Ноя"
    var dateRangeFormatted: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ru_RU")

        let startDay = Calendar.current.component(.day, from: startDate)
        let endDay = Calendar.current.component(.day, from: endDate)

        formatter.dateFormat = "MMM"
        let month = formatter.string(from: startDate).capitalized

        return "\(startDay)-\(endDay) \(month)"
    }

    /// Convert from DTO
    static func fromDTO(_ dto: SavedTripResponseDTO) -> SavedTripCard? {
        guard let id = UUID(uuidString: dto.id),
              let tripId = UUID(uuidString: dto.tripId) else {
            return nil
        }

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"

        guard let startDate = dateFormatter.date(from: dto.startDate),
              let endDate = dateFormatter.date(from: dto.endDate) else {
            return nil
        }

        return SavedTripCard(
            id: id,
            tripId: tripId,
            cityName: dto.cityName,
            startDate: startDate,
            endDate: endDate,
            heroImageUrl: dto.heroImageUrl,
            alreadySaved: dto.alreadySaved
        )
    }
}

// MARK: - Helper for encoding arbitrary JSON

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            self.value = array.map { $0.value }
        } else if let dictionary = try? container.decode([String: AnyCodable].self) {
            self.value = dictionary.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dictionary as [String: Any]:
            try container.encode(dictionary.mapValues { AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: container.codingPath, debugDescription: "Unknown type"))
        }
    }
}
