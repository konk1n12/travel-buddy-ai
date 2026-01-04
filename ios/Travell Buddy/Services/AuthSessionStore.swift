//
//  AuthSessionStore.swift
//  Travell Buddy
//
//  Secure token storage using Keychain for authenticated requests.
//

import Foundation
import Security

final class AuthSessionStore {
    static let shared = AuthSessionStore()

    private let accessTokenKey = "com.travelbuddy.access_token"
    private let refreshTokenKey = "com.travelbuddy.refresh_token"
    private let service = "com.travelbuddy.auth"

    private init() {}

    var accessToken: String? {
        get { readFromKeychain(key: accessTokenKey) }
        set {
            if let value = newValue, !value.isEmpty {
                saveToKeychain(key: accessTokenKey, value: value)
            } else {
                deleteFromKeychain(key: accessTokenKey)
            }
        }
    }

    var refreshToken: String? {
        get { readFromKeychain(key: refreshTokenKey) }
        set {
            if let value = newValue, !value.isEmpty {
                saveToKeychain(key: refreshTokenKey, value: value)
            } else {
                deleteFromKeychain(key: refreshTokenKey)
            }
        }
    }

    var isAuthenticated: Bool {
        accessToken != nil
    }

    func clear() {
        accessToken = nil
        refreshToken = nil
    }

    // MARK: - Keychain Operations

    private func saveToKeychain(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }

        // Delete existing item first
        deleteFromKeychain(key: key)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            print("[AuthSessionStore] Failed to save to keychain: \(status)")
        }
    }

    private func readFromKeychain(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }

        return string
    }

    private func deleteFromKeychain(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        SecItemDelete(query as CFDictionary)
    }
}
