//
//  RootView.swift
//  Travell Buddy
//
//  Root view: always shows main content.
//  Authorization is optional - feature gating is handled via AuthGatingManager.
//

import SwiftUI

struct RootView: View {
    @StateObject private var authManager = AuthManager.shared

    var body: some View {
        Group {
            switch authManager.state {
            case .unknown:
                // Loading state - checking stored session
                SplashLoadingView()

            case .loggingIn:
                // Auth in progress - show main content with loading overlay
                MainTabView()
                    .overlay(
                        LoadingOverlayView(message: "Входим...")
                    )

            case .loggedOut, .error, .loggedIn:
                // Always show main content - auth is optional (guest mode)
                MainTabView()
            }
        }
        .task {
            await authManager.restoreSessionOnLaunch()
        }
    }
}

// MARK: - Splash Loading View

private struct SplashLoadingView: View {
    var body: some View {
        ZStack {
            Color(red: 0.06, green: 0.06, blue: 0.07)
                .ignoresSafeArea()

            VStack(spacing: 24) {
                Image(systemName: "airplane.departure")
                    .font(.system(size: 48, weight: .medium))
                    .foregroundColor(.travelBuddyOrange)

                ProgressView()
                    .tint(.white)
            }
        }
    }
}

