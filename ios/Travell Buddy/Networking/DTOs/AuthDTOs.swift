//
//  AuthDTOs.swift
//  Travell Buddy
//
//  DTOs for authentication endpoints.
//

import Foundation

struct SessionResponseDTO: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
    let user: UserDTO

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
        case user
    }
}

struct UserDTO: Codable {
    let id: String
    let email: String?
    let displayName: String?
    let avatarUrl: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case email
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
        case createdAt = "created_at"
    }
}

struct EmailStartRequestDTO: Codable {
    let email: String
}

struct EmailStartResponseDTO: Codable {
    let challengeId: String
    let message: String

    enum CodingKeys: String, CodingKey {
        case challengeId = "challenge_id"
        case message
    }
}

struct EmailVerifyRequestDTO: Codable {
    let challengeId: String
    let code: String

    enum CodingKeys: String, CodingKey {
        case challengeId = "challenge_id"
        case code
    }
}

struct RefreshRequestDTO: Codable {
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct LogoutRequestDTO: Codable {
    let refreshToken: String?

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct AppleAuthRequestDTO: Codable {
    let idToken: String
    let firstName: String?
    let lastName: String?

    enum CodingKeys: String, CodingKey {
        case idToken = "id_token"
        case firstName = "first_name"
        case lastName = "last_name"
    }
}

struct GoogleAuthRequestDTO: Codable {
    let idToken: String

    enum CodingKeys: String, CodingKey {
        case idToken = "id_token"
    }
}
