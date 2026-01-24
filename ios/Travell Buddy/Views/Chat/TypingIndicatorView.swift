//
//  TypingIndicatorView.swift
//  Travell Buddy
//
//  Animated typing indicator shown while assistant is composing response.
//

import SwiftUI

/// Animated typing indicator with 3 pulsing dots
struct TypingIndicatorView: View {
    @State private var dotScale: [CGFloat] = [1.0, 1.0, 1.0]

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let assistantFill = Color.white.opacity(0.06)
    private let glassBorder = Color.white.opacity(0.14)

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(warmWhite.opacity(0.5))
                        .frame(width: 8, height: 8)
                        .scaleEffect(dotScale[index])
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(assistantFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(glassBorder, lineWidth: 1)
            )

            Spacer(minLength: 40)
        }
        .transition(.scale.combined(with: .opacity))
        .onAppear(perform: startAnimation)
    }

    // MARK: - Animation

    private func startAnimation() {
        // Staggered pulse animation for each dot
        for index in 0..<3 {
            let animation = Animation.easeInOut(duration: 0.6)
                .repeatForever(autoreverses: true)
                .delay(Double(index) * 0.2)

            withAnimation(animation) {
                dotScale[index] = 0.4
            }
        }
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        Color.black.ignoresSafeArea()

        VStack {
            TypingIndicatorView()
        }
        .padding()
    }
}
