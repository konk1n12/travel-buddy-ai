//
//  ChatMessage.swift
//  Travell Buddy
//
//  Data model for chat messages between user and AI assistant.
//

import Foundation

// MARK: - Message Status

/// Status of a user message during send lifecycle
enum MessageStatus: Equatable {
    case sending    // API call in progress
    case sent       // Successfully delivered
    case failed     // Send error, retry available
}

// MARK: - Chat Message

struct ChatMessage: Identifiable, Equatable {
    let id: UUID
    let text: String
    let isFromUser: Bool
    let timestamp: Date

    // Status tracking for user messages
    var status: MessageStatus?

    // Error details for failed messages
    var errorMessage: String?

    // Retry handler for failed messages
    var onRetry: (() -> Void)?

    // MARK: - Equatable

    static func == (lhs: ChatMessage, rhs: ChatMessage) -> Bool {
        lhs.id == rhs.id &&
        lhs.text == rhs.text &&
        lhs.isFromUser == rhs.isFromUser &&
        lhs.status == rhs.status &&
        lhs.errorMessage == rhs.errorMessage
        // Note: onRetry closure is intentionally excluded from equality comparison
    }
}

// MARK: - Default Messages

extension ChatMessage {
    /// Приветственное сообщение для чата
    static var welcomeMessage: ChatMessage {
        ChatMessage(
            id: UUID(),
            text: "Расскажи мне о своих пожеланиях: любишь ли ты много ходить, хочешь больше музеев или баров, есть ли ограничения?",
            isFromUser: false,
            timestamp: Date()
        )
    }
}
