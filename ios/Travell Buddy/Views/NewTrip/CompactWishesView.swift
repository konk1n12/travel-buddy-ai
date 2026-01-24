//
//  CompactWishesView.swift
//  Travell Buddy
//
//  Compact collapsed state for wishes block (~140-180pt height).
//

import SwiftUI

struct CompactWishesView: View {
    @Binding var messageText: String
    @FocusState.Binding var isTextFieldFocused: Bool
    let onExpand: () -> Void
    let onChipTap: (String) -> Void

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Header with icon and title
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Color.travelBuddyOrange)
                        .frame(width: 28, height: 28)

                    Image(systemName: "sparkles")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }

                Text("Пожелания")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .foregroundColor(warmWhite)

                Spacer()

                // Expand chevron button
                Button(action: onExpand) {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(mutedWarmGray)
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
            }

            // Description
            Text("Опишите идеальное путешествие, и я подберу маршрут специально для вас.")
                .font(.system(size: 13))
                .foregroundColor(mutedWarmGray)
                .fixedSize(horizontal: false, vertical: true)

            // Small text input
            TextField("Хочу спокойный отдых...", text: $messageText, axis: .vertical)
                .font(.system(size: 14))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color.white.opacity(0.06))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
                .focused($isTextFieldFocused)
                .lineLimit(1...2)
                .onTapGesture {
                    onExpand()
                }

            // Suggestion chips (one row)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(["Спокойный темп", "Избегать толп", "Много музеев"], id: \.self) { tag in
                        Button(action: {
                            onChipTap(tag)
                        }) {
                            Text(tag)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundColor(mutedWarmGray)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(
                                    Capsule()
                                        .fill(Color.white.opacity(0.06))
                                )
                                .overlay(
                                    Capsule()
                                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .contentShape(Rectangle())
    }
}

// MARK: - Preview

#Preview {
    @Previewable @State var messageText: String = ""
    @Previewable @FocusState var isFocused: Bool

    return ZStack {
        SmokyBackgroundView()

        CompactWishesView(
            messageText: $messageText,
            isTextFieldFocused: $isFocused,
            onExpand: { print("Expand") },
            onChipTap: { tag in messageText = tag }
        )
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(Color.white.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(Color.white.opacity(0.14), lineWidth: 1)
                )
        )
        .padding()
    }
}
