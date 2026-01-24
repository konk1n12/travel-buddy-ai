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

    // NEW: Typing indicator state
    @Published var isAssistantTyping: Bool = false

    // NEW: Show suggestion chips
    @Published var showSuggestions: Bool = true

    private let tripId: UUID?
    private let apiClient: TripPlanningAPIClient

    // Store last message for retry
    private var lastFailedMessageText: String?

    // Demo mode - work without backend if tripId is nil
    private var isDemoMode: Bool { tripId == nil }

    /// Callback to trigger plan update in parent view model
    /// Returns true if update succeeded
    var onPlanUpdateRequested: (() async -> Bool)?

    init(
        tripId: UUID? = nil,
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
            let welcomeText = tripId == nil
                ? "Расскажи о своих пожеланиях к путешествию!"
                : "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?"

            self.messages = [
                ChatMessage(
                    id: UUID(),
                    text: welcomeText,
                    isFromUser: false,
                    timestamp: Date()
                )
            ]
        }
    }

    // MARK: - Public Methods

    /// Send a chat message to the backend with optimistic UI
    @MainActor
    func sendMessage(_ text: String) async {
        // Validate input
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }

        // 1. Optimistic: Create and add user message immediately with .sending status
        let messageId = UUID()
        var userMessage = ChatMessage(
            id: messageId,
            text: trimmedText,
            isFromUser: true,
            timestamp: Date(),
            status: .sending
        )
        messages.append(userMessage)

        // 2. Hide suggestion chips after first message
        showSuggestions = false

        // 3. Show typing indicator
        isAssistantTyping = true
        lastSendFailed = false
        errorMessage = nil

        defer {
            isAssistantTyping = false
        }

        print("💬 [Chat] Sending message: id=\(messageId.uuidString.prefix(8)), length=\(trimmedText.count), demoMode=\(isDemoMode)")

        do {
            let responseText: String

            if isDemoMode {
                // Demo mode: simulate response with delay
                try await Task.sleep(nanoseconds: 1_500_000_000) // 1.5 seconds

                // Generate demo response
                responseText = generateDemoResponse(for: trimmedText)
                print("🎭 [Chat] Demo mode: generated mock response")

            } else {
                // Real mode: call backend API
                guard let tripId = tripId else {
                    throw APIError.invalidURL
                }

                let response = try await apiClient.sendChatMessage(
                    tripId: tripId,
                    message: trimmedText
                )
                responseText = response.assistantMessage
                print("✅ [Chat] Message sent successfully, response length: \(responseText.count)")
            }

            // 5. Update message status to .sent
            if let index = messages.firstIndex(where: { $0.id == messageId }) {
                messages[index].status = .sent
            }

            // Clear failed message tracker on success
            lastFailedMessageText = nil

            // 6. Add assistant response
            let assistantMessage = ChatMessage(
                id: UUID(),
                text: responseText,
                isFromUser: false,
                timestamp: Date()
            )
            messages.append(assistantMessage)

        } catch {
            // 7. Update message status to .failed with retry capability
            if let index = messages.firstIndex(where: { $0.id == messageId }) {
                let errorDesc = (error as? APIError)?.errorDescription ?? "Не удалось отправить"
                messages[index].status = .failed
                messages[index].errorMessage = errorDesc

                // Attach retry closure
                messages[index].onRetry = { [weak self] in
                    Task { @MainActor in
                        await self?.retryMessage(id: messageId, text: trimmedText)
                    }
                }
            }

            // Store for potential retry via banner
            lastFailedMessageText = trimmedText
            self.lastSendFailed = true
            self.errorMessage = (error as? APIError)?.errorDescription

            // Log error with status code
            let statusCode = extractStatusCode(from: error)
            print("❌ [Chat] Send failed: [\(statusCode)] \(error.localizedDescription)")

            // Note: Error is now displayed inline on the message bubble, not as a separate chat message
        }
    }

    /// Retry sending a specific failed message by ID
    @MainActor
    private func retryMessage(id: UUID, text: String) async {
        // Remove the failed message
        messages.removeAll { $0.id == id }

        // Resend with new message ID
        await sendMessage(text)
    }

    /// Retry sending the last failed message (for compatibility with existing retry banner)
    @MainActor
    func retrySendMessage() async {
        guard let lastText = lastFailedMessageText else { return }

        // Find and remove the last failed user message
        if let lastFailedIndex = messages.lastIndex(where: { $0.isFromUser && $0.status == .failed }) {
            messages.remove(at: lastFailedIndex)
        }

        // Retry with same text
        await sendMessage(lastText)
    }

    /// Generate demo response for testing without backend
    private func generateDemoResponse(for userMessage: String) -> String {
        let lowercased = userMessage.lowercased()

        // Simple keyword-based responses
        if lowercased.contains("музе") {
            return "Отлично! Я подберу для вас маршрут с посещением самых интересных музеев города. Вы предпочитаете искусство, историю или науку?"
        } else if lowercased.contains("бар") || lowercased.contains("кафе") || lowercased.contains("еда") || lowercased.contains("кухня") {
            return "Понял! Добавлю в маршрут лучшие бары и рестораны с местной кухней. Есть ли у вас предпочтения по типу кухни?"
        } else if lowercased.contains("спокойн") || lowercased.contains("темп") {
            return "Хорошо, составлю маршрут в спокойном темпе с достаточным временем на отдых. Сколько часов в день вы планируете на прогулки?"
        } else if lowercased.contains("толп") || lowercased.contains("люд") {
            return "Понятно, постараюсь избегать самых туристических мест и подберу менее популярные, но не менее интересные локации."
        } else if lowercased.contains("актив") || lowercased.contains("много ходить") {
            return "Отлично! Составлю активный маршрут с пешими прогулками. Готовы ли вы проходить 10-15 км в день?"
        } else {
            return "Спасибо за информацию! Учту ваши пожелания при планировании маршрута. Расскажите ещё что-нибудь о своих предпочтениях?"
        }
    }

    /// Extract status code from error for logging
    private func extractStatusCode(from error: Error) -> String {
        if let apiError = error as? APIError {
            switch apiError {
            case .httpError(let code, _):
                return "\(code)"
            case .networkError:
                return "network"
            case .decodingError:
                return "decode"
            case .invalidURL:
                return "invalid_url"
            case .serverError:
                return "server_error"
            case .tripNotFound:
                return "404_trip"
            case .unauthorized:
                return "401"
            case .paywallRequired:
                return "402"
            case .timeout:
                return "timeout"
            }
        }
        return "unknown"
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
