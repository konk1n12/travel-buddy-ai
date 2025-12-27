//
//  ErrorBannerView.swift
//  Travell Buddy
//
//  Reusable error banner component with optional retry action.
//  All user-facing text is in Russian.
//

import SwiftUI

/// A banner view displaying an error message with optional retry button.
struct ErrorBannerView: View {
    let message: String
    var retryAction: (() -> Void)?
    var dismissAction: (() -> Void)?

    var body: some View {
        HStack(spacing: 12) {
            // Error icon
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)

            // Message
            Text(message)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white)
                .lineLimit(2)

            Spacer(minLength: 8)

            // Actions
            HStack(spacing: 12) {
                if let retryAction {
                    Button(action: retryAction) {
                        Text("Повторить")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(Color.white.opacity(0.2))
                            )
                    }
                    .buttonStyle(.plain)
                }

                if let dismissAction {
                    Button(action: dismissAction) {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(.white.opacity(0.8))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.red.opacity(0.9))
        )
        .shadow(color: Color.red.opacity(0.3), radius: 8, x: 0, y: 4)
    }
}

/// An inline error text view for subtle error display.
struct InlineErrorView: View {
    let message: String
    var retryAction: (() -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.system(size: 14))
                .foregroundColor(.red)

            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.red)
                .lineLimit(2)

            if let retryAction {
                Spacer()
                Button(action: retryAction) {
                    Text("Повторить")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.travelBuddyOrange)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.red.opacity(0.1))
        )
    }
}

// MARK: - Preview

#Preview("Error Banner") {
    VStack(spacing: 20) {
        ErrorBannerView(
            message: "Не удалось загрузить маршрут",
            retryAction: { print("Retry") },
            dismissAction: { print("Dismiss") }
        )

        ErrorBannerView(
            message: "Проблема с подключением к интернету"
        )

        InlineErrorView(
            message: "Не удалось отправить сообщение",
            retryAction: { print("Retry") }
        )

        InlineErrorView(
            message: "Ошибка загрузки"
        )
    }
    .padding()
}
