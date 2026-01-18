//
//  ChatView.swift
//  Travell Buddy
//
//  Full-screen chat with AI assistant.
//

import SwiftUI

// MARK: - Chat Tab View

/// Обёртка для таба "Чат" с собственным состоянием сообщений
/// Note: This is a placeholder - real chat needs a trip ID
struct ChatTabView: View {
    @StateObject private var viewModel: ChatViewModel

    init() {
        // Placeholder: use a dummy UUID until we have a real trip
        // In production, this should be passed from the parent view
        _viewModel = StateObject(wrappedValue: ChatViewModel(
            tripId: UUID(),
            initialMessages: [ChatMessage.welcomeMessage]
        ))
    }

    var body: some View {
        ChatView(viewModel: viewModel)
    }
}

// MARK: - Full Chat View

/// Полноэкранный чат с AI‑агентом (открывается из чат-бара или таба "Чат").
struct ChatView: View {
    @StateObject var viewModel: ChatViewModel
    @State private var messageText: String = ""
    @FocusState private var isTextFieldFocused: Bool
    @Environment(\.dismiss) private var dismiss
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let mutedWarmGray = Color(red: 0.70, green: 0.67, blue: 0.63)
    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)
    private let inputFill = Color.white.opacity(0.06)
    private let inputBorder = Color.white.opacity(0.12)

    init(viewModel: ChatViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ZStack {
            SmokyBackgroundView()

            VStack(spacing: 0) {
                // Заголовок чата
                chatHeaderView

                // Область сообщений
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(viewModel.messages) { message in
                                ChatBubbleView(message: message)
                                    .id(message.id)
                            }
                        }
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                        .padding(.bottom, 16)
                    }
                    .scrollIndicators(.hidden)
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: viewModel.messages.count) { _ in
                        if let lastMessage = viewModel.messages.last {
                            withAnimation {
                                proxy.scrollTo(lastMessage.id, anchor: .bottom)
                            }
                        }
                    }
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 8) {
                if viewModel.lastSendFailed {
                    retryBanner
                }

                chatInputView
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .background(
                LinearGradient(
                    colors: [
                        Color.clear,
                        Color.black.opacity(0.4)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea(edges: .bottom)
            )
        }
        .navigationBarHidden(true)
        .hideTabBar()
    }

    // MARK: Retry Banner

    private var retryBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Color.travelBuddyOrange.opacity(0.9))

            Text("chat.messageFailed".localized)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(warmWhite)

            Spacer()

            Button(action: { retrySend() }) {
                Text("common.button.retry".localized)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Color.travelBuddyOrange)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(glassFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(glassBorder, lineWidth: 1)
        )
    }

    // MARK: Chat Header

    private var chatHeaderView: some View {
        HStack {
            // Кнопка назад
            Button(action: { dismiss() }) {
                Image(systemName: "chevron.left")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(mutedWarmGray)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(.plain)

            Spacer()
        }
        .overlay(
            Text("Travel Buddy")
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .foregroundColor(Color.travelBuddyOrange)
        )
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(glassFill)
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(glassBorder, lineWidth: 1)
                )
        )
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 8)
    }

    // MARK: Chat Input

    private var chatInputView: some View {
        HStack(spacing: 10) {
            TextField("chat.placeholder".localized, text: $messageText, axis: .vertical)
                .font(.system(size: 14))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(inputFill)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(inputBorder, lineWidth: 1)
                )
                .focused($isTextFieldFocused)
                .lineLimit(1...3)
                .tint(Color.travelBuddyOrange)

            // Кнопка отправки
            Button {
                sendMessage()
            } label: {
                if viewModel.isSending {
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
            .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSending)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(glassFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(glassBorder, lineWidth: 1)
        )
    }

    // MARK: Send Message

    private func sendMessage() {
        let trimmedText = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Clear input field immediately
        let textToSend = trimmedText
        messageText = ""
        isTextFieldFocused = false

        // Send message via ViewModel (async)
        Task {
            await viewModel.sendMessage(textToSend)
        }
    }

    // MARK: Retry Send

    private func retrySend() {
        Task {
            await viewModel.retrySendMessage()
        }
    }
}
