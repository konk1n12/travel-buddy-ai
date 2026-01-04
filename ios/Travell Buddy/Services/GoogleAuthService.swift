//
//  GoogleAuthService.swift
//  Travell Buddy
//
//  Google OAuth sign-in using ASWebAuthenticationSession.
//

import Foundation
import UIKit
import GoogleSignIn

enum GoogleAuthError: LocalizedError {
    case missingClientId
    case invalidCallbackURL
    case missingIdToken

    var errorDescription: String? {
        switch self {
        case .missingClientId:
            return "Не задан Google Client ID"
        case .invalidCallbackURL:
            return "Некорректный ответ от Google"
        case .missingIdToken:
            return "Не удалось получить токен Google"
        }
    }
}

final class GoogleAuthService {
    func signIn() async throws -> String {
        guard !AppConfig.googleClientId.isEmpty else {
            throw GoogleAuthError.missingClientId
        }

        let configuration = GIDConfiguration(clientID: AppConfig.googleClientId)
        GIDSignIn.sharedInstance.configuration = configuration

        guard let rootViewController = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .flatMap({ $0.windows })
            .first(where: { $0.isKeyWindow })?.rootViewController else {
            throw GoogleAuthError.invalidCallbackURL
        }

        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootViewController)
        guard let idToken = result.user.idToken?.tokenString, !idToken.isEmpty else {
            throw GoogleAuthError.missingIdToken
        }

        return idToken
    }
}
