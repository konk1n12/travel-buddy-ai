//
//  ExpandedWishesView.swift
//  Travell Buddy
//
//  Expanded chat state for wishes block with full chat interface.
//

import SwiftUI

struct ExpandedWishesView: View {
    @ObservedObject var chatViewModel: ChatViewModel
    @Binding var messageText: String
    @FocusState.Binding var isTextFieldFocused: Bool
    let onCollapse: () -> Void
    let onSend: () -> Void

    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)

    var body: some View {
        VStack(spacing: 0) {
            // Header with collapse button
            HStack {
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
                }

                Spacer()

                // Collapse button
                Button(action: onCollapse) {
                    Image(systemName: "chevron.up")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(mutedWarmGray)
                        .frame(width: 32, height: 32)
                        .background(
                            Circle()
                                .fill(Color.white.opacity(0.06))
                        )
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)
            .padding(.bottom, 12)

            // Chat messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(chatViewModel.messages) { message in
                            ChatBubbleView(message: message)
                                .id(message.id)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .bottom).combined(with: .opacity),
                                    removal: .opacity
                                ))
                        }

                        // Typing indicator
                        if chatViewModel.isAssistantTyping {
                            TypingIndicatorView()
                                .id("typing-indicator")
                                .transition(.scale(scale: 0.8).combined(with: .opacity))
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
                .scrollIndicators(.hidden)
                .onChange(of: chatViewModel.messages.count) { _ in
                    scrollToBottom(proxy: proxy)
                }
                .onChange(of: chatViewModel.isAssistantTyping) { _ in
                    scrollToBottom(proxy: proxy)
                }
            }

            // Input area with suggestions
            VStack(spacing: 8) {
                // Suggestion chips (show if no messages yet)
                if chatViewModel.showSuggestions {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(Array(SuggestionChip.defaults.enumerated()), id: \.element.id) { index, chip in
                                Button(action: {
                                    messageText = chip.fullMessage
                                    onSend()
                                }) {
                                    Text(chip.text)
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
                                .transition(.scale.combined(with: .opacity))
                                .animation(.spring(response: 0.4, dampingFraction: 0.8).delay(Double(index) * 0.05), value: chatViewModel.showSuggestions)
                            }
                        }
                        .padding(.horizontal, 16)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                // Input field with send button
                HStack(spacing: 10) {
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
                        .lineLimit(1...3)

                    Button(action: onSend) {
                        if chatViewModel.isSending {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.8)
                                .frame(width: 36, height: 36)
                                .background(
                                    Circle()
                                        .fill(Color.travelBuddyOrange)
                                )
                        } else {
                            Image(systemName: "arrow.up")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.white)
                                .frame(width: 36, height: 36)
                                .background(
                                    Circle()
                                        .fill(Color.travelBuddyOrange)
                                )
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || chatViewModel.isSending)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            withAnimation {
                if chatViewModel.isAssistantTyping {
                    proxy.scrollTo("typing-indicator", anchor: .bottom)
                } else if let lastMessage = chatViewModel.messages.last {
                    proxy.scrollTo(lastMessage.id, anchor: .bottom)
                }
            }
        }
    }
}

// MARK: - Preview

#Preview {
    @Previewable @State var messageText: String = ""
    @Previewable @FocusState var isFocused: Bool

    let viewModel = ChatViewModel(
        tripId: nil,
        initialMessages: []
    )

    return ZStack {
        SmokyBackgroundView()

        ExpandedWishesView(
            chatViewModel: viewModel,
            messageText: $messageText,
            isTextFieldFocused: $isFocused,
            onCollapse: { print("Collapse") },
            onSend: { print("Send") }
        )
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
