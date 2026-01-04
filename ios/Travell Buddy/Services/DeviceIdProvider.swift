//
//  DeviceIdProvider.swift
//  Travell Buddy
//
//  Provides a stable device identifier for guest tracking.
//

import Foundation

final class DeviceIdProvider {
    static let shared = DeviceIdProvider()

    private let storageKey = "travelbuddy.device_id"

    private init() {}

    var deviceId: String {
        if let existing = UserDefaults.standard.string(forKey: storageKey), !existing.isEmpty {
            return existing
        }

        let generated = UUID().uuidString.lowercased()
        UserDefaults.standard.set(generated, forKey: storageKey)
        return generated
    }
}
