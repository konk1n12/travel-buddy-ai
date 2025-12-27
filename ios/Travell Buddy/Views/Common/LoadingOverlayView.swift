//
//  LoadingOverlayView.swift
//  Travell Buddy
//
//  Reusable loading overlay component.
//  All user-facing text is in Russian.
//

import SwiftUI

/// A semi-transparent overlay with a loading spinner and optional message.
struct LoadingOverlayView: View {
    var message: String = "Загрузка..."
    var showBackground: Bool = true

    var body: some View {
        ZStack {
            if showBackground {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
            }

            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.2)
                    .progressViewStyle(CircularProgressViewStyle(tint: .white))

                Text(message)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(.white)
            }
            .padding(.horizontal, 32)
            .padding(.vertical, 24)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color(.systemGray).opacity(0.95))
            )
            .shadow(color: Color.black.opacity(0.2), radius: 10, x: 0, y: 4)
        }
    }
}

/// A compact inline loading indicator.
struct InlineLoadingView: View {
    var message: String = "Загрузка..."

    var body: some View {
        HStack(spacing: 10) {
            ProgressView()
                .scaleEffect(0.9)

            Text(message)
                .font(.system(size: 14))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(.systemGray6))
        )
    }
}

// MARK: - View Modifier

extension View {
    /// Shows a loading overlay on top of the view when `isLoading` is true.
    func loadingOverlay(
        isLoading: Bool,
        message: String = "Загрузка..."
    ) -> some View {
        ZStack {
            self
                .disabled(isLoading)
                .blur(radius: isLoading ? 1 : 0)

            if isLoading {
                LoadingOverlayView(message: message)
            }
        }
    }
}

// MARK: - Preview

#Preview("Loading Overlay") {
    ZStack {
        Color.blue
            .ignoresSafeArea()

        VStack(spacing: 20) {
            LoadingOverlayView(message: "Генерирую маршрут...")

            InlineLoadingView(message: "Отправка...")
        }
    }
}
