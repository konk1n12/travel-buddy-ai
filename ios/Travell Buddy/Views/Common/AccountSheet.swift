//
//  AccountSheet.swift
//  Travell Buddy
//
//  Simple account management UI (refresh/logout).
//

import SwiftUI

struct AccountSheet: View {
    @Environment(\.dismiss) private var dismiss

    @State private var isLoading: Bool = false
    @State private var errorText: String?
    @State private var statusText: String = ""

    private let authClient = AuthAPIClient()

    var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                VStack(spacing: 6) {
                    Image(systemName: AuthSessionStore.shared.accessToken == nil ? "person.crop.circle" : "person.crop.circle.fill")
                        .font(.system(size: 34, weight: .semibold))
                        .foregroundColor(.travelBuddyOrange)

                    Text(AuthSessionStore.shared.accessToken == nil ? "Гостевой режим" : "Вход выполнен")
                        .font(.system(size: 18, weight: .semibold))
                }

                if let errorText {
                    Text(errorText)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                }

                VStack(spacing: 12) {
                    Button {
                        Task {
                            await refreshSession()
                        }
                    } label: {
                        Text("Обновить сессию")
                            .font(.system(size: 16, weight: .semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Color(.systemGray5))
                            .foregroundColor(Color(.label))
                            .cornerRadius(12)
                    }

                    Button {
                        Task {
                            await logout()
                        }
                    } label: {
                        Text("Выйти")
                            .font(.system(size: 16, weight: .semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Color(red: 1.0, green: 0.45, blue: 0.35))
                            .foregroundColor(.white)
                            .cornerRadius(12)
                    }
                }

                if isLoading {
                    ProgressView()
                        .padding(.top, 8)
                }

                Spacer()
            }
            .padding(24)
            .navigationTitle("Аккаунт")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Готово") {
                        dismiss()
                    }
                }
            }
        }
        .onAppear {
            statusText = AuthSessionStore.shared.accessToken == nil
                ? "Гостевой режим"
                : "Вход выполнен"
        }
    }

    @MainActor
    private func refreshSession() async {
        errorText = nil
        isLoading = true

        guard let refreshToken = AuthSessionStore.shared.refreshToken else {
            errorText = "Нет refresh токена"
            isLoading = false
            return
        }

        do {
            let session = try await authClient.refreshSession(refreshToken: refreshToken)
            AuthSessionStore.shared.accessToken = session.accessToken
            AuthSessionStore.shared.refreshToken = session.refreshToken
            statusText = "Сессия обновлена"
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Не удалось обновить сессию"
        }

        isLoading = false
    }

    @MainActor
    private func logout() async {
        errorText = nil
        isLoading = true

        do {
            try await authClient.logout(refreshToken: AuthSessionStore.shared.refreshToken)
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Не удалось выйти"
        }

        AuthSessionStore.shared.clear()
        statusText = "Гостевой режим"
        isLoading = false
    }
}
