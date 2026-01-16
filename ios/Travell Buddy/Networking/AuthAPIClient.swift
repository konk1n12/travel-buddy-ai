//
//  AuthAPIClient.swift
//  Travell Buddy
//
//  API client for authentication endpoints.
//

import Foundation

final class AuthAPIClient {
    private let session: URLSession
    private let requestBuilder: RequestBuilder

    init(session: URLSession = .shared, requestBuilder: RequestBuilder = RequestBuilder()) {
        self.session = session
        self.requestBuilder = requestBuilder
    }

    func startEmailAuth(email: String) async throws -> EmailStartResponseDTO {
        let request = EmailStartRequestDTO(email: email)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/email/start",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        switch httpResponse.statusCode {
        case 200, 201:
            return try JSONDecoder().decode(EmailStartResponseDTO.self, from: data)
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    func verifyEmailAuth(challengeId: String, code: String) async throws -> SessionResponseDTO {
        let request = EmailVerifyRequestDTO(challengeId: challengeId, code: code)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/email/verify",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        switch httpResponse.statusCode {
        case 200, 201:
            return try JSONDecoder().decode(SessionResponseDTO.self, from: data)
        case 401:
            throw APIError.unauthorized
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    func authenticateApple(idToken: String, nonce: String? = nil, firstName: String?, lastName: String?) async throws -> SessionResponseDTO {
        let request = AppleAuthRequestDTO(idToken: idToken, nonce: nonce, firstName: firstName, lastName: lastName)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/apple",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        switch httpResponse.statusCode {
        case 200, 201:
            return try JSONDecoder().decode(SessionResponseDTO.self, from: data)
        case 401:
            throw APIError.unauthorized
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    func authenticateGoogle(idToken: String) async throws -> SessionResponseDTO {
        let request = GoogleAuthRequestDTO(idToken: idToken)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/google",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        switch httpResponse.statusCode {
        case 200, 201:
            return try JSONDecoder().decode(SessionResponseDTO.self, from: data)
        case 401:
            throw APIError.unauthorized
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    func refreshSession(refreshToken: String) async throws -> SessionResponseDTO {
        let request = RefreshRequestDTO(refreshToken: refreshToken)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/refresh",
            method: .post,
            body: bodyData
        )

        let (data, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        switch httpResponse.statusCode {
        case 200, 201:
            return try JSONDecoder().decode(SessionResponseDTO.self, from: data)
        case 401:
            throw APIError.unauthorized
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    func logout(refreshToken: String?) async throws {
        let request = LogoutRequestDTO(refreshToken: refreshToken)
        let encoder = JSONEncoder()
        let bodyData = try encoder.encode(request)

        let urlRequest = try requestBuilder.buildRequest(
            path: "auth/logout",
            method: .post,
            body: bodyData
        )

        let (_, response) = try await session.data(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(NSError(domain: "Invalid response", code: -1))
        }

        if httpResponse.statusCode != 204 {
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: nil)
        }
    }
}
