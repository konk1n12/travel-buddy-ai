//
//  ChatViewModel.swift
//  Travell Buddy
//
//  ViewModel for managing chat state and backend communication.
//

import Foundation

final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage]
    @Published var isSending: Bool = false
    @Published var isUpdatingPlan: Bool = false
    @Published var errorMessage: String?
    @Published var lastSendFailed: Bool = false

    private let tripId: UUID
    private let apiClient: TripPlanningAPIClient

    // Store last message for retry
    private var lastFailedMessageText: String?

    /// Callback to trigger plan update in parent view model
    /// Returns true if update succeeded
    var onPlanUpdateRequested: (() async -> Bool)?

    init(
        tripId: UUID,
        initialMessages: [ChatMessage] = [],
        apiClient: TripPlanningAPIClient = .shared,
        onPlanUpdateRequested: (() async -> Bool)? = nil
    ) {
        self.tripId = tripId
        self.apiClient = apiClient
        self.messages = initialMessages
        self.onPlanUpdateRequested = onPlanUpdateRequested

        // Add default welcome message if no initial messages
        if initialMessages.isEmpty {
            self.messages = [
                ChatMessage(
                    id: UUID(),
                    text: "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?",
                    isFromUser: false,
                    timestamp: Date()
                )
            ]
        }
    }

    // MARK: - Public Methods

    /// Send a chat message to the backend
    @MainActor
    func sendMessage(_ text: String) async {
        // Validate input
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // Store for potential retry
        lastFailedMessageText = trimmedText

        // Add user message to chat
        let userMessage = ChatMessage(
            id: UUID(),
            text: trimmedText,
            isFromUser: true,
            timestamp: Date()
        )
        messages.append(userMessage)

        // Set loading state
        isSending = true
        errorMessage = nil
        lastSendFailed = false

        defer { isSending = false }

        print("💬 Sending message to backend for trip: \(tripId)")

        do {
            // Call backend API
            let response = try await apiClient.sendChatMessage(
                tripId: tripId,
                message: trimmedText
            )

            // Clear failed message on success
            lastFailedMessageText = nil

            // Add assistant message to chat
            let assistantMessage = ChatMessage(
                id: UUID(),
                text: response.assistantMessage,
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(assistantMessage)

            print("✅ Chat response received: \(response.assistantMessage.prefix(50))...")

        } catch {
            // Handle error
            let errorDescription = (error as? LocalizedError)?.errorDescription
                ?? "Что-то пошло не так. Попробуйте ещё раз."
            self.errorMessage = errorDescription
            self.lastSendFailed = true
            print("❌ Chat error: \(errorDescription)")

            // Add error message to chat with retry hint
            let errorChatMessage = ChatMessage(
                id: UUID(),
                text: "Не удалось отправить сообщение. Проверьте соединение и попробуйте ещё раз.",
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(errorChatMessage)
        }
    }

    /// Retry sending the last failed message
    @MainActor
    func retrySendMessage() async {
        guard let lastText = lastFailedMessageText else { return }

        // Remove the last error message if present
        if let lastMessage = messages.last, !lastMessage.isFromUser,
           lastMessage.text.contains("Не удалось") {
            messages.removeLast()
        }

        // Remove the failed user message
        if let lastUserMessage = messages.last, lastUserMessage.isFromUser {
            messages.removeLast()
        }

        // Retry with same text
        await sendMessage(lastText)
    }

    /// Request plan update based on chat preferences
    @MainActor
    func requestPlanUpdate() async {
        guard let onPlanUpdateRequested else {
            print("⚠️ No plan update handler configured")
            return
        }

        isUpdatingPlan = true
        errorMessage = nil

        defer { isUpdatingPlan = false }

        print("🔄 Requesting plan update...")

        // Call the parent's update method and check result
        let success = await onPlanUpdateRequested()

        if success {
            // Add success message
            let systemMessage = ChatMessage(
                id: UUID(),
                text: "✅ Маршрут обновлён с учётом ваших пожеланий. Вернитесь к экрану маршрута, чтобы увидеть изменения.",
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(systemMessage)
            print("✅ Plan update completed")
        } else {
            // Add error message with retry hint
            let errorChatMessage = ChatMessage(
                id: UUID(),
                text: "Не удалось обновить маршрут. Нажмите кнопку обновления ещё раз.",
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(errorChatMessage)
            print("❌ Plan update failed")
        }
    }
}
