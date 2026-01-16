//
//  AuthGatingManager.swift
//  Travell Buddy
//
//  Centralized manager for feature gating with optional authentication.
//  Handles showing auth modal for protected features and executing pending actions after login.
//

import Foundation
import SwiftUI
import Combine

// MARK: - Protected Action

/// Actions that require authentication for guests.
enum ProtectedAction: Equatable {
    case viewMap
    case viewDay(dayIndex: Int)

    var gatingMessage: String {
        switch self {
        case .viewMap:
            return "Карта доступна после входа"
        case .viewDay(let dayIndex):
            return "День \(dayIndex + 1) доступен после входа"
        }
    }

    var dayNumber: Int? {
        switch self {
        case .viewDay(let dayIndex):
            return dayIndex + 1
        case .viewMap:
            return nil
        }
    }
}

// MARK: - AuthGatingManager

/// Singleton manager for feature gating.
/// Use `requireAuth(for:)` to gate features that require authentication.
@MainActor
final class AuthGatingManager: ObservableObject {
    static let shared = AuthGatingManager()

    /// Whether the auth modal is currently presented.
    @Published var isAuthModalPresented: Bool = false

    /// The pending action that will be executed after successful authentication.
    @Published private(set) var pendingAction: ProtectedAction?

    /// Message shown in the auth modal.
    @Published private(set) var gatingMessage: String?

    /// Callback to execute when auth succeeds.
    private var pendingCallback: (() -> Void)?

    private var cancellables = Set<AnyCancellable>()

    private init() {
        // Listen to auth state changes
        AuthManager.shared.$state
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                if case .loggedIn = state {
                    self?.handleAuthStateChanged(isAuthenticated: true)
                }
            }
            .store(in: &cancellables)
    }

    // MARK: - Public API

    /// Check if user is authenticated. If not, show auth modal and save callback.
    /// - Parameters:
    ///   - action: The protected action being attempted
    ///   - onAllowed: Callback executed immediately if authenticated, or after successful login
    func requireAuth(for action: ProtectedAction, onAllowed: @escaping () -> Void) {
        if AuthManager.shared.isAuthenticated {
            // User is logged in - execute immediately
            onAllowed()
        } else {
            // User is guest - show auth modal
            pendingAction = action
            pendingCallback = onAllowed
            gatingMessage = action.gatingMessage
            isAuthModalPresented = true
        }
    }

    /// Called when user successfully authenticates.
    /// Closes modal and executes pending action.
    func handleAuthSuccess() {
        isAuthModalPresented = false

        // Execute pending callback
        if let callback = pendingCallback {
            // Small delay to allow modal to dismiss
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                callback()
            }
        }

        clearPendingState()
    }

    /// Called when user cancels auth modal.
    /// Clears pending state without executing callback.
    func cancelPendingAction() {
        isAuthModalPresented = false
        clearPendingState()
    }

    /// Check if a day requires authentication (Day 2+).
    func isDayLocked(dayIndex: Int) -> Bool {
        return !AuthManager.shared.isAuthenticated && dayIndex > 0
    }

    /// Check if map requires authentication.
    func isMapLocked() -> Bool {
        return !AuthManager.shared.isAuthenticated
    }

    // MARK: - Private

    private func handleAuthStateChanged(isAuthenticated: Bool) {
        if isAuthenticated && isAuthModalPresented {
            handleAuthSuccess()
        }
    }

    private func clearPendingState() {
        pendingAction = nil
        pendingCallback = nil
        gatingMessage = nil
    }
}
