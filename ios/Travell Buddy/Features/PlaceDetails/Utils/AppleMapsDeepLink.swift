//
//  AppleMapsDeepLink.swift
//  Travell Buddy
//

import Foundation
import CoreLocation

enum AppleMapsDeepLink {
    static func directionsURL(name: String, coordinate: CLLocationCoordinate2D) -> URL? {
        var components = URLComponents(string: "http://maps.apple.com/")
        components?.queryItems = [
            URLQueryItem(name: "daddr", value: "\(coordinate.latitude),\(coordinate.longitude)"),
            URLQueryItem(name: "q", value: name)
        ]
        return components?.url
    }
}
