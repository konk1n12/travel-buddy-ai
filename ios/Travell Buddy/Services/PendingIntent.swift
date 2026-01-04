//
//  PendingIntent.swift
//  Travell Buddy
//
//  Stores the intent to resume after authentication.
//

import Foundation

struct TripGenerationParams {
    let destinationCity: String
    let startDate: Date
    let endDate: Date
    let selectedInterests: [String]
    let budgetLevel: String
    let travellersCount: Int
    let pace: String
}

enum PendingIntent {
    case openDay(Int)
    case openMap
    case generateTrip(TripGenerationParams)
}
