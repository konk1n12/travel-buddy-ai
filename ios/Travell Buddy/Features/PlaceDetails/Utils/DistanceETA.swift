//
//  DistanceETA.swift
//  Travell Buddy
//

import Foundation
import CoreLocation

enum DistanceETA {
    static func distanceKm(from: CLLocationCoordinate2D, to: CLLocationCoordinate2D) -> Double {
        let earthRadius = 6371.0

        let lat1 = from.latitude * Double.pi / 180
        let lon1 = from.longitude * Double.pi / 180
        let lat2 = to.latitude * Double.pi / 180
        let lon2 = to.longitude * Double.pi / 180

        let dLat = lat2 - lat1
        let dLon = lon2 - lon1

        let a = sin(dLat / 2) * sin(dLat / 2) +
            cos(lat1) * cos(lat2) * sin(dLon / 2) * sin(dLon / 2)
        let c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return earthRadius * c
    }

    static func estimateETA(distanceKm: Double, mode: TravelMode) -> Int {
        let speedKmh: Double
        switch mode {
        case .walking:
            speedKmh = 4.8
        case .driving:
            speedKmh = 25.0
        case .transit:
            speedKmh = 18.0
        case .cycling:
            speedKmh = 14.0
        }

        let hours = distanceKm / max(speedKmh, 1.0)
        return max(Int((hours * 60).rounded()), 1)
    }
}
