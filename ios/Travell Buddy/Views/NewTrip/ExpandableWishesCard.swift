//
//  ExpandableWishesCard.swift
//  Travell Buddy
//
//  Main expandable wishes card that switches between compact and expanded states.
//

import SwiftUI

struct ExpandableWishesCard: View {
    @StateObject private var chatViewModel: ChatViewModel
    @Binding var messageText: String
    @Binding var preferencesDraft: PreferencesDraft
    @FocusState.Binding var isTextFieldFocused: Bool

    @State private var isExpanded: Bool = false

    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)

    // Computed heights
    private var compactHeight: CGFloat { 160 }
    private var expandedHeight: CGFloat {
        // Use 70% of screen height, but ensure it doesn't get cut off
        min(UIScreen.main.bounds.height * 0.7, UIScreen.main.bounds.height - 100)
    }

    init(
        messageText: Binding<String>,
        preferencesDraft: Binding<PreferencesDraft>,
        isTextFieldFocused: FocusState<Bool>.Binding,
        tripId: UUID? = nil
    ) {
        self._messageText = messageText
        self._preferencesDraft = preferencesDraft
        self._isTextFieldFocused = isTextFieldFocused

        // Initialize ChatViewModel with optional tripId (nil = demo mode)
        self._chatViewModel = StateObject(wrappedValue: ChatViewModel(
            tripId: tripId,
            initialMessages: []
        ))
    }

    var body: some View {
        VStack(spacing: 0) {
            if isExpanded {
                // Expanded state - full chat
                ExpandedWishesView(
                    chatViewModel: chatViewModel,
                    messageText: $messageText,
                    isTextFieldFocused: $isTextFieldFocused,
                    onCollapse: {
                        collapseCard()
                    },
                    onSend: {
                        sendMessage()
                    }
                )
                .frame(height: expandedHeight)
                .transition(.asymmetric(
                    insertion: .scale(scale: 0.95).combined(with: .opacity),
                    removal: .scale(scale: 0.98).combined(with: .opacity)
                ))
            } else {
                // Collapsed state - compact view
                CompactWishesView(
                    messageText: $messageText,
                    isTextFieldFocused: $isTextFieldFocused,
                    onExpand: {
                        expandCard()
                    },
                    onChipTap: { tag in
                        messageText = tag
                        expandCard()
                        // Auto-focus when chip tapped
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                            isTextFieldFocused = true
                        }
                    }
                )
                .frame(height: compactHeight)
                .transition(.asymmetric(
                    insertion: .scale(scale: 0.98).combined(with: .opacity),
                    removal: .scale(scale: 0.95).combined(with: .opacity)
                ))
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(glassFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(glassBorder, lineWidth: 1)
        )
        .onChange(of: isTextFieldFocused) { focused in
            if focused && !isExpanded {
                expandCard()
            }
        }
        .onChange(of: chatViewModel.messages) { _ in
            // Sync chat messages to preferences draft in real-time
            updatePreferencesDraft()
        }
        .id("wishes-card")
    }

    // MARK: - Actions

    private func expandCard() {
        // Haptic feedback for expansion
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()

        // Smooth spring animation with bounce
        withAnimation(.spring(response: 0.45, dampingFraction: 0.75)) {
            isExpanded = true
        }
    }

    private func collapseCard() {
        // Haptic feedback for collapse
        let generator = UIImpactFeedbackGenerator(style: .soft)
        generator.impactOccurred()

        // Smooth collapse animation
        isTextFieldFocused = false

        withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
            isExpanded = false
        }

        // Update preferences draft after collapse
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            updatePreferencesDraft()
        }
    }

    private func sendMessage() {
        let trimmedText = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Send via ChatViewModel
        Task {
            await chatViewModel.sendMessage(trimmedText)

            await MainActor.run {
                messageText = ""

                // Update preferences draft
                updatePreferencesDraft()
            }
        }
    }

    private func updatePreferencesDraft() {
        // Sync chat messages to PreferencesDraft
        preferencesDraft.chatMessages = chatViewModel.messages

        // Also update freeText if there's unsent text
        let trimmed = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            preferencesDraft.freeText = trimmed
        } else {
            // Clear freeText if input is empty
            preferencesDraft.freeText = ""
        }

        // Debug log to verify sync
        print("📝 PreferencesDraft updated: \(preferencesDraft.chatMessages.count) messages")
    }
}

// MARK: - Preview

#Preview {
    @Previewable @State var messageText: String = ""
    @Previewable @State var preferencesDraft = PreferencesDraft()
    @Previewable @FocusState var isFocused: Bool

    return ZStack {
        SmokyBackgroundView()

        ScrollView {
            VStack(spacing: 20) {
                ExpandableWishesCard(
                    messageText: $messageText,
                    preferencesDraft: $preferencesDraft,
                    isTextFieldFocused: $isFocused,
                    tripId: nil
                )

                Spacer()
            }
            .padding()
        }
    }
}
