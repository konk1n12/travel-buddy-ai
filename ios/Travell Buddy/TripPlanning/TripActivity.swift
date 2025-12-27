//
//  TripActivity.swift
//  Travell Buddy
//
//  One concrete activity within a trip day.
//

import Foundation
import CoreLocation

struct TripActivity: Identifiable {
    let id: UUID
    let time: String
    let title: String
    let description: String
    let category: TripActivityCategory
    let address: String?
    let note: String?

    // Map-related fields
    let latitude: Double?
    let longitude: Double?
    let travelPolyline: String?  // Encoded polyline from previous activity

    /// Returns coordinate if both lat/lon are available
    var coordinate: CLLocationCoordinate2D? {
        guard let lat = latitude, let lon = longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    /// Returns true if this activity has valid map coordinates
    var hasCoordinates: Bool {
        latitude != nil && longitude != nil
    }
}

enum TripActivityCategory: CaseIterable {
    case food
    case walk
    case museum
    case viewpoint
    case nightlife
    case other
}
