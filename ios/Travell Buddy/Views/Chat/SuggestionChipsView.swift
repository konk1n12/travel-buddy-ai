//
//  SuggestionChipsView.swift
//  Travell Buddy
//
//  Quick reply suggestion chips for chat.
//

import SwiftUI

// MARK: - Suggestion Chip Model

struct SuggestionChip: Identifiable {
    let id = UUID()
    let text: String
    let fullMessage: String  // Full message to send when tapped
}

// MARK: - Suggestion Chips View

/// Horizontal scrolling suggestion chips for quick replies
struct SuggestionChipsView: View {
    let chips: [SuggestionChip]
    let onTap: (SuggestionChip) -> Void

    @State private var selectedId: UUID?

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let glassBorder = Color.white.opacity(0.14)

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(chips) { chip in
                    chipButton(chip)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 8)
        }
    }

    // MARK: - Chip Button

    private func chipButton(_ chip: SuggestionChip) -> some View {
        let isSelected = selectedId == chip.id

        return Button {
            // Animate selection
            withAnimation(.spring(response: 0.3)) {
                selectedId = chip.id
            }
            // Trigger callback
            onTap(chip)
        } label: {
            Text(chip.text)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(isSelected ? Color.travelBuddyOrange : warmWhite)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(isSelected ? Color.white.opacity(0.08) : Color.clear)
                )
                .overlay(
                    Capsule()
                        .stroke(
                            isSelected ? Color.travelBuddyOrange : glassBorder,
                            lineWidth: 1.5
                        )
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Default Suggestions

extension SuggestionChip {
    static var defaults: [SuggestionChip] {
        [
            SuggestionChip(
                text: "Спокойный темп",
                fullMessage: "Я люблю спокойный темп, не хочу спешить"
            ),
            SuggestionChip(
                text: "Избегать толп",
                fullMessage: "Хочу избегать туристических толп"
            ),
            SuggestionChip(
                text: "Больше музеев",
                fullMessage: "Интересуют музеи и культурные места"
            ),
            SuggestionChip(
                text: "Местная кухня",
                fullMessage: "Хочу попробовать местную кухню"
            ),
            SuggestionChip(
                text: "Активный отдых",
                fullMessage: "Предпочитаю активный отдых"
            )
        ]
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        Color.black.ignoresSafeArea()

        VStack {
            Spacer()

            SuggestionChipsView(chips: SuggestionChip.defaults) { chip in
                print("Tapped: \(chip.text)")
            }
        }
    }
}
