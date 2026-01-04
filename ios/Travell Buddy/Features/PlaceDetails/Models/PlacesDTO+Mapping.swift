//
//  PlacesDTO+Mapping.swift
//  Travell Buddy
//
//  Google Places DTOs and mapping into view data.
//

import Foundation
import CoreLocation

struct GooglePlaceDetailsDTO: Decodable {
    let placeId: String
    let name: String
    let types: [String]
    let rating: Double?
    let reviewsCount: Int?
    let priceLevel: Int?
    let isOpenNow: Bool?
    let openingHours: [String]?
    let nextOpenTime: String?
    let nextCloseTime: String?
    let address: String?
    let latitude: Double
    let longitude: Double
    let website: String?
    let phone: String?
    let googleMapsUrl: String?
    let editorialSummary: String?
    let photos: [GooglePlacePhotoDTO]
    let reservable: Bool?
    let servesBreakfast: Bool?
    let servesLunch: Bool?
    let servesDinner: Bool?
    let servesBeer: Bool?
    let servesWine: Bool?
    let servesVegetarianFood: Bool?
    let takeout: Bool?
    let delivery: Bool?
    let dineIn: Bool?
    let curbsidePickup: Bool?
    let wheelchairAccessibleEntrance: Bool?
    let reviews: [GooglePlaceReviewDTO]
}

struct GooglePlacePhotoDTO: Decodable {
    let id: String
    let width: Int?
    let height: Int?
    let attribution: [String]
}

struct GooglePlaceReviewDTO: Decodable {
    let authorName: String
    let rating: Double
    let text: String
    let relativeTime: String
}

struct PlaceDetailsViewData: Identifiable {
    let id: String
    let name: String
    let types: [String]
    let categoryLabel: String
    let categoryIcon: String
    let coordinate: CLLocationCoordinate2D
    let rating: Double?
    let reviewsCount: Int?
    let priceLevel: PriceLevel?
    let isOpenNow: Bool?
    let openingHours: [String]
    let nextOpenTime: String?
    let nextCloseTime: String?
    let address: String?
    let website: URL?
    let phone: String?
    let googleMapsURL: URL?
    let editorialSummary: String?
    let photos: [PlaceDetailsPhoto]
    let amenities: [String]
    let reservable: Bool
    let reviews: [PlaceDetailsReview]

    var isRestaurant: Bool {
        types.contains { ["restaurant", "cafe", "bar", "bakery"].contains($0) }
    }
}

struct PlaceDetailsPhoto: Identifiable {
    let id: String
    let url: URL
    let width: Int?
    let height: Int?
    let attribution: [String]
}

struct PlaceDetailsReview: Identifiable {
    let id: String
    let authorName: String
    let rating: Double
    let text: String
    let relativeTime: String
}

enum GooglePlaceTypeMapper {
    static func categoryInfo(types: [String]) -> (label: String, icon: String) {
        let primary = types.first ?? "point_of_interest"
        switch primary {
        case "restaurant": return ("Ресторан", "fork.knife")
        case "cafe": return ("Кафе", "cup.and.saucer.fill")
        case "bar": return ("Бар", "wineglass.fill")
        case "bakery": return ("Пекарня", "birthday.cake.fill")
        case "museum": return ("Музей", "building.columns.fill")
        case "park": return ("Парк", "leaf.fill")
        case "tourist_attraction": return ("Достопримечательность", "star.fill")
        case "shopping_mall": return ("Шопинг", "bag.fill")
        case "night_club": return ("Ночная жизнь", "moon.stars.fill")
        default: return ("Место", "mappin.and.ellipse")
        }
    }

    static func highlightChips(types: [String], rating: Double?, reviewsCount: Int?) -> [String] {
        var chips: [String] = []
        for type in types.prefix(4) {
            let label = readableType(type)
            if !chips.contains(label) {
                chips.append(label)
            }
        }
        if let rating = rating, rating >= 4.5 {
            chips.append("Хороший рейтинг")
        }
        if let reviewsCount = reviewsCount, reviewsCount >= 1000 {
            chips.append("Популярное")
        }
        return Array(chips.prefix(6))
    }

    static func readableType(_ type: String) -> String {
        switch type {
        case "restaurant": return "Ресторан"
        case "cafe": return "Кафе"
        case "bar": return "Бар"
        case "bakery": return "Пекарня"
        case "museum": return "Музей"
        case "park": return "Парк"
        case "tourist_attraction": return "Достопримечательность"
        case "shopping_mall": return "Шопинг"
        case "night_club": return "Ночная жизнь"
        default: return type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

extension GooglePlaceDetailsDTO {
    func toViewData(apiBaseURL: URL) -> PlaceDetailsViewData {
        let category = GooglePlaceTypeMapper.categoryInfo(types: types)
        let photos = photos.compactMap { photo -> PlaceDetailsPhoto? in
            let url = apiBaseURL.appendingPathComponent("places/photos/\(photo.id)")
            return PlaceDetailsPhoto(
                id: photo.id,
                url: url,
                width: photo.width,
                height: photo.height,
                attribution: photo.attribution
            )
        }
        let amenities = AmenityMapper.from(dto: self)
        let reviews = self.reviews.prefix(2).enumerated().map { index, review in
            PlaceDetailsReview(
                id: "\(placeId)-review-\(index)",
                authorName: review.authorName,
                rating: review.rating,
                text: review.text,
                relativeTime: review.relativeTime
            )
        }

        return PlaceDetailsViewData(
            id: placeId,
            name: name,
            types: types,
            categoryLabel: category.label,
            categoryIcon: category.icon,
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            rating: rating,
            reviewsCount: reviewsCount,
            priceLevel: priceLevel.flatMap { PriceLevel(rawValue: $0) },
            isOpenNow: isOpenNow,
            openingHours: openingHours ?? [],
            nextOpenTime: nextOpenTime,
            nextCloseTime: nextCloseTime,
            address: address,
            website: normalizedURL(website),
            phone: phone,
            googleMapsURL: googleMapsUrl.flatMap(URL.init(string:)),
            editorialSummary: editorialSummary,
            photos: photos,
            amenities: amenities,
            reservable: reservable ?? false,
            reviews: reviews
        )
    }

    private func normalizedURL(_ raw: String?) -> URL? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else {
            return nil
        }
        if let url = URL(string: raw), url.scheme != nil {
            return url
        }
        return URL(string: "https://\(raw)")
    }
}

enum AmenityMapper {
    static func from(dto: GooglePlaceDetailsDTO) -> [String] {
        var items: [String] = []
        if dto.dineIn == true { items.append("Посадка внутри") }
        if dto.takeout == true { items.append("С собой") }
        if dto.delivery == true { items.append("Доставка") }
        if dto.curbsidePickup == true { items.append("Самовывоз") }
        if dto.wheelchairAccessibleEntrance == true { items.append("Доступно для колясок") }
        if dto.servesVegetarianFood == true { items.append("Вегетарианские блюда") }
        if dto.servesBreakfast == true { items.append("Завтраки") }
        if dto.servesLunch == true { items.append("Обеды") }
        if dto.servesDinner == true { items.append("Ужины") }
        if dto.servesBeer == true { items.append("Пиво") }
        if dto.servesWine == true { items.append("Вино") }
        return items
    }
}
