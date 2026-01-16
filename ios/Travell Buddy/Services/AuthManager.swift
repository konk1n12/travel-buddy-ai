//
//  AuthManager.swift
//  Travell Buddy
//
//  Central authentication manager with observable state.
//  Handles all auth flows: Apple, Google, Email OTP.
//

import Foundation
import SwiftUI
import AuthenticationServices
import CryptoKit

// MARK: - Auth State

enum AuthState: Equatable {
    case unknown          // Initial state, checking stored session
    case loggedOut        // No valid session
    case loggingIn        // Auth in progress
    case loggedIn(User)   // Successfully authenticated
    case error(String)    // Auth error with message

    static func == (lhs: AuthState, rhs: AuthState) -> Bool {
        switch (lhs, rhs) {
        case (.unknown, .unknown): return true
        case (.loggedOut, .loggedOut): return true
        case (.loggingIn, .loggingIn): return true
        case (.loggedIn(let u1), .loggedIn(let u2)): return u1.id == u2.id
        case (.error(let m1), .error(let m2)): return m1 == m2
        default: return false
        }
    }
}

// MARK: - User Model

struct User: Codable, Equatable {
    let id: String
    let email: String?
    let displayName: String?
    let avatarUrl: String?

    init(from dto: UserDTO) {
        self.id = dto.id
        self.email = dto.email
        self.displayName = dto.displayName
        self.avatarUrl = dto.avatarUrl
    }

    init(id: String, email: String?, displayName: String?, avatarUrl: String?) {
        self.id = id
        self.email = email
        self.displayName = displayName
        self.avatarUrl = avatarUrl
    }
}

// MARK: - AuthManager

@MainActor
final class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published private(set) var state: AuthState = .unknown
    @Published private(set) var currentUser: User?

    private let authClient = AuthAPIClient()
    private let googleAuthService = GoogleAuthService()
    private let sessionStore = AuthSessionStore.shared

    // Keys for user profile storage
    private let userProfileKey = "com.travelbuddy.user_profile"

    // Current nonce for Apple Sign In (must persist during auth flow)
    private var currentNonce: String?

    private init() {}

    // MARK: - Session Restoration

    /// Call on app launch to restore session from Keychain
    func restoreSessionOnLaunch() async {
        guard sessionStore.accessToken != nil else {
            state = .loggedOut
            return
        }

        // Try to load cached user profile
        if let user = loadUserProfile() {
            currentUser = user
            state = .loggedIn(user)

            // Optionally refresh token in background
            Task {
                await refreshSessionSilently()
            }
        } else {
            // Token exists but no user profile - try to refresh
            await refreshSessionSilently()

            if case .loggedIn = state {
                // Success
            } else {
                // Failed to refresh - logout
                logout()
            }
        }
    }

    // MARK: - Sign In with Apple

    /// Generate a new nonce for Apple Sign In. Call before showing Apple auth UI.
    func prepareAppleSignIn() -> String {
        let nonce = generateNonce()
        currentNonce = nonce
        return sha256(nonce)
    }

    /// Handle Apple authorization result
    func handleAppleAuthorization(_ authorization: ASAuthorization) async {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            state = .error("Не удалось получить данные Apple ID")
            return
        }

        guard let tokenData = credential.identityToken,
              let idToken = String(data: tokenData, encoding: .utf8) else {
            state = .error("Не удалось получить Apple токен")
            return
        }

        guard let nonce = currentNonce else {
            state = .error("Ошибка безопасности: отсутствует nonce")
            return
        }

        // Extract user info (only available on first sign in)
        let firstName = credential.fullName?.givenName
        let lastName = credential.fullName?.familyName

        state = .loggingIn

        do {
            let session = try await authClient.authenticateApple(
                idToken: idToken,
                nonce: nonce,
                firstName: firstName,
                lastName: lastName
            )
            handleSuccessfulAuth(session)
        } catch {
            handleAuthError(error)
        }

        currentNonce = nil
    }

    /// Handle Apple authorization error
    func handleAppleError(_ error: Error) {
        // User cancelled is not an error
        if let authError = error as? ASAuthorizationError,
           authError.code == .canceled {
            if case .loggingIn = state {
                state = .loggedOut
            }
            return
        }

        state = .error(error.localizedDescription)
        currentNonce = nil
    }

    // MARK: - Sign In with Google

    func signInWithGoogle() async {
        state = .loggingIn

        do {
            let idToken = try await googleAuthService.signIn()
            let session = try await authClient.authenticateGoogle(idToken: idToken)
            handleSuccessfulAuth(session)
        } catch {
            // User cancelled is not an error
            if let gidError = error as NSError?,
               gidError.domain == "com.google.GIDSignIn",
               gidError.code == -5 { // GIDSignInErrorCode.canceled
                state = .loggedOut
                return
            }
            handleAuthError(error)
        }
    }

    // MARK: - Email OTP

    /// Request OTP code to be sent to email
    func requestEmailCode(email: String) async throws -> String {
        let response = try await authClient.startEmailAuth(email: email)
        return response.challengeId
    }

    /// Verify OTP code and complete authentication
    func verifyEmailCode(challengeId: String, code: String) async {
        state = .loggingIn

        do {
            let session = try await authClient.verifyEmailAuth(challengeId: challengeId, code: code)
            handleSuccessfulAuth(session)
        } catch {
            handleAuthError(error)
        }
    }

    // MARK: - Refresh Token

    /// Refresh session token. Returns true if successful.
    @discardableResult
    func refreshSession() async -> Bool {
        guard let refreshToken = sessionStore.refreshToken else {
            logout()
            return false
        }

        do {
            let session = try await authClient.refreshSession(refreshToken: refreshToken)
            sessionStore.accessToken = session.accessToken
            sessionStore.refreshToken = session.refreshToken
            let user = User(from: session.user)
            currentUser = user
            saveUserProfile(user)
            state = .loggedIn(user)
            return true
        } catch {
            // Refresh failed - likely token expired
            logout()
            return false
        }
    }

    /// Silent refresh - doesn't change state to loggingIn
    private func refreshSessionSilently() async {
        guard let refreshToken = sessionStore.refreshToken else {
            state = .loggedOut
            return
        }

        do {
            let session = try await authClient.refreshSession(refreshToken: refreshToken)
            sessionStore.accessToken = session.accessToken
            sessionStore.refreshToken = session.refreshToken
            let user = User(from: session.user)
            currentUser = user
            saveUserProfile(user)
            state = .loggedIn(user)
        } catch {
            // Don't logout on silent refresh failure if we have cached user
            if currentUser == nil {
                state = .loggedOut
            }
        }
    }

    // MARK: - Logout

    func logout() {
        // Try to notify server (fire and forget)
        if let refreshToken = sessionStore.refreshToken {
            Task {
                try? await authClient.logout(refreshToken: refreshToken)
            }
        }

        // Clear local state
        sessionStore.clear()
        clearUserProfile()
        currentUser = nil
        state = .loggedOut
    }

    // MARK: - Helpers

    private func handleSuccessfulAuth(_ session: SessionResponseDTO) {
        sessionStore.accessToken = session.accessToken
        sessionStore.refreshToken = session.refreshToken
        let user = User(from: session.user)
        currentUser = user
        saveUserProfile(user)
        state = .loggedIn(user)
    }

    private func handleAuthError(_ error: Error) {
        let message = (error as? LocalizedError)?.errorDescription ?? "Ошибка авторизации"
        state = .error(message)
    }

    // MARK: - Nonce Generation (for Apple Sign In)

    private func generateNonce(length: Int = 32) -> String {
        precondition(length > 0)
        var randomBytes = [UInt8](repeating: 0, count: length)
        let errorCode = SecRandomCopyBytes(kSecRandomDefault, randomBytes.count, &randomBytes)
        if errorCode != errSecSuccess {
            fatalError("Unable to generate nonce. SecRandomCopyBytes failed with OSStatus \(errorCode)")
        }

        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        let nonce = randomBytes.map { byte in
            charset[Int(byte) % charset.count]
        }
        return String(nonce)
    }

    private func sha256(_ input: String) -> String {
        let inputData = Data(input.utf8)
        let hashedData = SHA256.hash(data: inputData)
        let hashString = hashedData.compactMap {
            String(format: "%02x", $0)
        }.joined()
        return hashString
    }

    // MARK: - User Profile Persistence

    private func saveUserProfile(_ user: User) {
        if let data = try? JSONEncoder().encode(user) {
            UserDefaults.standard.set(data, forKey: userProfileKey)
        }
    }

    private func loadUserProfile() -> User? {
        guard let data = UserDefaults.standard.data(forKey: userProfileKey),
              let user = try? JSONDecoder().decode(User.self, from: data) else {
            return nil
        }
        return user
    }

    private func clearUserProfile() {
        UserDefaults.standard.removeObject(forKey: userProfileKey)
    }

    // MARK: - Convenience

    var isAuthenticated: Bool {
        if case .loggedIn = state {
            return true
        }
        return false
    }
}
