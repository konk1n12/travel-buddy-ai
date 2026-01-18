//
//  ChatBubbleView.swift
//  Travell Buddy
//
//  Single chat message bubble (user or AI).
//

import SwiftUI

struct ChatBubbleView: View {
    let message: ChatMessage
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let glassBorder = Color.white.opacity(0.14)
    private let assistantFill = Color.white.opacity(0.06)
    private let userFill = Color.white.opacity(0.10)
    private let maxBubbleWidth = min(UIScreen.main.bounds.width * 0.72, 320)

    var body: some View {
        if message.isFromUser {
            // Сообщение пользователя (справа)
            HStack(alignment: .top, spacing: 12) {
                Spacer(minLength: 40)

                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(warmWhite)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .frame(maxWidth: maxBubbleWidth, alignment: .trailing)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(userFill)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(Color.travelBuddyOrange.opacity(0.6), lineWidth: 1)
                    )
            }
        } else {
            // Сообщение AI (слева)
            HStack(alignment: .top, spacing: 12) {
                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(warmWhite)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .frame(maxWidth: maxBubbleWidth, alignment: .leading)
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
        }
    }
}
