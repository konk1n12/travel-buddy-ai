//
//  PlaceDetailsSheet.swift
//  Travell Buddy
//
//  Wrapper to present the new Google Places details view in a sheet.
//

import SwiftUI

struct PlaceDetailsSheet: View {
    let place: Place

    var body: some View {
        if let placeId = place.googlePlaceId {
            PlaceDetailsView(placeId: placeId, fallbackPlace: place)
        } else {
            MissingPlaceIdView(placeName: place.name)
        }
    }
}
