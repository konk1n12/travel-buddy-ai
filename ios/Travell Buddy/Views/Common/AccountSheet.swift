//
//  AccountSheet.swift
//  Travell Buddy
//
//  Account management UI with user info, refresh, and logout.
//

import SwiftUI

struct AccountSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var authManager = AuthManager.shared

    @State private var isLoading: Bool = false
    @State private var message: String?
    @State private var isError: Bool = false

    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                // User info section
                userInfoSection

                // Status message
                if let message {
                    Text(message)
                        .font(.system(size: 13))
                        .foregroundColor(isError ? .red : .green)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                // Action buttons
                VStack(spacing: 12) {
                    // Refresh session button
                    Button {
                        Task {
                            await refreshSession()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Обновить сессию")
                        }
                        .font(.system(size: 16, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color(.secondarySystemBackground))
                        .foregroundColor(Color(.label))
                        .cornerRadius(12)
                    }
                    .disabled(isLoading)

                    // Logout button
                    Button {
                        performLogout()
                    } label: {
                        HStack {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                            Text("Выйти из аккаунта")
                        }
                        .font(.system(size: 16, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.travelBuddyOrange)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .disabled(isLoading)
                }

                if isLoading {
                    ProgressView()
                        .padding(.top, 8)
                }

                Spacer()

                // App version
                Text("Travel Buddy v1.0")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .padding(.bottom, 8)
            }
            .padding(24)
            .navigationTitle("Аккаунт")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Готово") {
                        dismiss()
                    }
                }
            }
        }
    }

    // MARK: - User Info Section

    @ViewBuilder
    private var userInfoSection: some View {
        VStack(spacing: 12) {
            // Avatar
            ZStack {
                Circle()
                    .fill(LinearGradient.travelBuddyAvatar)
                    .frame(width: 80, height: 80)

                if let avatarUrl = authManager.currentUser?.avatarUrl,
                   let url = URL(string: avatarUrl) {
                    AsyncImage(url: url) { image in
                        image
                            .resizable()
                            .scaledToFill()
                    } placeholder: {
                        userInitials
                    }
                    .frame(width: 76, height: 76)
                    .clipShape(Circle())
                } else {
                    userInitials
                }
            }

            // Name and email
            VStack(spacing: 4) {
                if let displayName = authManager.currentUser?.displayName, !displayName.isEmpty {
                    Text(displayName)
                        .font(.system(size: 20, weight: .semibold))
                } else {
                    Text("Пользователь")
                        .font(.system(size: 20, weight: .semibold))
                }

                if let email = authManager.currentUser?.email {
                    Text(email)
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var userInitials: some View {
        let initials = getInitials()
        Text(initials)
            .font(.system(size: 28, weight: .semibold))
            .foregroundColor(.white)
    }

    private func getInitials() -> String {
        if let name = authManager.currentUser?.displayName, !name.isEmpty {
            let components = name.split(separator: " ")
            if components.count >= 2 {
                return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
            }
            return String(name.prefix(2)).uppercased()
        }
        if let email = authManager.currentUser?.email {
            return String(email.prefix(2)).uppercased()
        }
        return "TB"
    }

    // MARK: - Actions

    @MainActor
    private func refreshSession() async {
        message = nil
        isLoading = true

        let success = await authManager.refreshSession()

        if success {
            message = "Сессия обновлена"
            isError = false
        } else {
            message = "Не удалось обновить сессию"
            isError = true
        }

        isLoading = false
    }

    private func performLogout() {
        authManager.logout()
        dismiss()
    }
}
