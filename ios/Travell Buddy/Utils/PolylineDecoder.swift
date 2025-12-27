//
//  PolylineDecoder.swift
//  Travell Buddy
//
//  Utility for decoding Google's encoded polyline format into coordinates.
//  Reference: https://developers.google.com/maps/documentation/utilities/polylinealgorithm
//

import Foundation
import CoreLocation

/// Decodes Google's encoded polyline format into an array of coordinates.
enum PolylineDecoder {

    /// Decodes an encoded polyline string into an array of CLLocationCoordinate2D.
    /// - Parameter encodedPolyline: The encoded polyline string from Google's API.
    /// - Returns: An array of coordinates, or an empty array if decoding fails.
    static func decode(_ encodedPolyline: String) -> [CLLocationCoordinate2D] {
        guard !encodedPolyline.isEmpty else { return [] }

        var coordinates: [CLLocationCoordinate2D] = []
        var index = encodedPolyline.startIndex
        var latitude: Int32 = 0
        var longitude: Int32 = 0

        while index < encodedPolyline.endIndex {
            // Decode latitude
            guard let latDelta = decodeValue(from: encodedPolyline, at: &index) else {
                return coordinates  // Return what we have so far
            }
            latitude += latDelta

            // Decode longitude
            guard let lonDelta = decodeValue(from: encodedPolyline, at: &index) else {
                return coordinates  // Return what we have so far
            }
            longitude += lonDelta

            // Convert to decimal degrees (divide by 1e5)
            let lat = Double(latitude) / 1e5
            let lon = Double(longitude) / 1e5

            coordinates.append(CLLocationCoordinate2D(latitude: lat, longitude: lon))
        }

        return coordinates
    }

    /// Decodes a single value from the encoded polyline.
    /// - Parameters:
    ///   - polyline: The encoded polyline string.
    ///   - index: The current index, updated as characters are consumed.
    /// - Returns: The decoded value, or nil if decoding fails.
    private static func decodeValue(from polyline: String, at index: inout String.Index) -> Int32? {
        var result: Int32 = 0
        var shift: Int32 = 0

        while index < polyline.endIndex {
            // Get the next character's ASCII value and subtract 63
            let char = polyline[index]
            guard let asciiValue = char.asciiValue else { return nil }

            let value = Int32(asciiValue) - 63
            index = polyline.index(after: index)

            // Add the 5 low-order bits to the result
            result |= (value & 0x1F) << shift
            shift += 5

            // If the high bit is not set, we're done with this value
            if value < 0x20 {
                // Handle negative numbers (two's complement)
                if result & 1 != 0 {
                    return ~(result >> 1)
                } else {
                    return result >> 1
                }
            }
        }

        return nil  // Incomplete encoding
    }
}
