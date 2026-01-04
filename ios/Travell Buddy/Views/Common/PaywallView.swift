//
//  PaywallView.swift
//  Travell Buddy
//
//  Paywall modal shown for locked actions.
//

import SwiftUI
import AuthenticationServices

struct PaywallView: View {
    let errorMessage: String?
    let onAuthSuccess: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var isShowingEmailAuth: Bool = false
    @State private var isLoading: Bool = false
    @State private var errorText: String?

    private let authClient = AuthAPIClient()
    private let googleAuthService = GoogleAuthService()

    var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                VStack(spacing: 8) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 30, weight: .semibold))
                        .foregroundColor(.orange)

                    Text("Разблокируйте полный маршрут")
                        .font(.system(size: 20, weight: .semibold))

                    Text(errorMessage ?? "Доступно после входа")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 16)
                }

                VStack(spacing: 12) {
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handleAppleResult(result)
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 48)
                    .cornerRadius(12)

                    Button {
                        isShowingEmailAuth = true
                    } label: {
                        HStack {
                            Image(systemName: "envelope.fill")
                            Text("Продолжить по email")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .foregroundColor(.white)
                        .background(Color(red: 0.15, green: 0.18, blue: 0.22))
                        .cornerRadius(12)
                    }

                    Button {
                        Task {
                            await handleGoogleSignIn()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "globe")
                            Text("Продолжить с Google")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .foregroundColor(.white)
                        .background(Color(red: 0.25, green: 0.30, blue: 0.38))
                        .cornerRadius(12)
                    }
                }
                .padding(.top, 8)

                if let errorText {
                    Text(errorText)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                }

                Spacer()

                if isLoading {
                    ProgressView()
                        .padding(.bottom, 12)
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Закрыть") {
                        errorText = nil
                        dismiss()
                    }
                }
            }
            .sheet(isPresented: $isShowingEmailAuth) {
                EmailAuthView(
                    onComplete: { session in
                        storeSession(session)
                        onAuthSuccess()
                    }
                )
            }
        }
    }

    private func handleAppleResult(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let token = String(data: tokenData, encoding: .utf8) else {
                errorText = "Не удалось получить Apple токен"
                return
            }

            let firstName = credential.fullName?.givenName
            let lastName = credential.fullName?.familyName
            isLoading = true

            Task {
                do {
                    let session = try await authClient.authenticateApple(
                        idToken: token,
                        firstName: firstName,
                        lastName: lastName
                    )
                    await MainActor.run {
                        storeSession(session)
                        onAuthSuccess()
                    }
                } catch {
                    await MainActor.run {
                        errorText = (error as? LocalizedError)?.errorDescription ?? "Ошибка авторизации"
                    }
                }
                await MainActor.run { isLoading = false }
            }
        case .failure(let error):
            errorText = error.localizedDescription
        }
    }

    @MainActor
    private func handleGoogleSignIn() async {
        isLoading = true
        errorText = nil

        do {
            let idToken = try await googleAuthService.signIn()
            let session = try await authClient.authenticateGoogle(idToken: idToken)
            storeSession(session)
            onAuthSuccess()
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Не удалось войти через Google"
        }

        isLoading = false
    }

    private func storeSession(_ session: SessionResponseDTO) {
        AuthSessionStore.shared.accessToken = session.accessToken
        AuthSessionStore.shared.refreshToken = session.refreshToken
    }
}

private struct EmailAuthView: View {
    let onComplete: (SessionResponseDTO) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var email: String = ""
    @State private var code: String = ""
    @State private var challengeId: String?
    @State private var isLoading: Bool = false
    @State private var errorText: String?

    private let authClient = AuthAPIClient()

    var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                Text(challengeId == nil ? "Введите email" : "Введите код из письма")
                    .font(.system(size: 18, weight: .semibold))

                if challengeId == nil {
                    TextField("email@example.com", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .padding(12)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(10)
                } else {
                    TextField("Код", text: $code)
                        .keyboardType(.numberPad)
                        .textInputAutocapitalization(.never)
                        .padding(12)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(10)
                }

                if let errorText {
                    Text(errorText)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                }

                Button {
                    Task { await handlePrimaryAction() }
                } label: {
                    Text(challengeId == nil ? "Отправить код" : "Подтвердить")
                        .font(.system(size: 16, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color(red: 1.0, green: 0.45, blue: 0.35))
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .disabled(isLoading)

                if isLoading {
                    ProgressView()
                        .padding(.top, 4)
                }

                Spacer()
            }
            .padding(24)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Закрыть") { dismiss() }
                }
            }
        }
    }

    private func handlePrimaryAction() async {
        errorText = nil
        isLoading = true

        do {
            if challengeId == nil {
                let response = try await authClient.startEmailAuth(email: email)
                challengeId = response.challengeId
            } else if let challengeId {
                let session = try await authClient.verifyEmailAuth(challengeId: challengeId, code: code)
                onComplete(session)
                dismiss()
            }
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Ошибка авторизации"
        }

        isLoading = false
    }
}
