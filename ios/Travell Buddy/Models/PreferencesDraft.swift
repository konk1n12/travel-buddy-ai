//
//  PreferencesDraft.swift
//  Travell Buddy
//
//  Unified model for collecting trip preferences from multiple sources.
//

import Foundation

/// Collects trip preferences from free text, chat, and tags
struct PreferencesDraft {
    var freeText: String = ""
    var chatMessages: [ChatMessage] = []
    var selectedTags: Set<String> = []

    /// Build combined wishes text for trip generation
    func buildWishesPayload() -> String {
        var parts: [String] = []

        // 1. Chat notes from user messages (last 10) - MOST IMPORTANT
        let userMessages = chatMessages
            .filter { $0.isFromUser }
            .suffix(10)
            .map { $0.text }

        if !userMessages.isEmpty {
            // Format as natural conversation
            let chatNotes = "Пожелания путешественника:\n" + userMessages.joined(separator: "\n- ")
            parts.append(chatNotes)
        }

        // 2. Free text input (if not sent as message yet)
        let trimmedFreeText = freeText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedFreeText.isEmpty {
            // Check if this text is already in chat messages to avoid duplication
            let isAlreadyInChat = userMessages.contains { $0 == trimmedFreeText }
            if !isAlreadyInChat {
                parts.append(trimmedFreeText)
            }
        }

        // 3. Selected tags/styles
        if !selectedTags.isEmpty {
            let tagsText = "Интересы: " + selectedTags.sorted().joined(separator: ", ")
            parts.append(tagsText)
        }

        return parts.joined(separator: "\n\n")
    }
}
