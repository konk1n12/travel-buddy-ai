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

    var body: some View {
        if message.isFromUser {
            userBubbleView
        } else {
            assistantBubbleView
        }
    }

    // MARK: - User Bubble

    private var userBubbleView: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Spacer(minLength: 40)

            VStack(alignment: .trailing, spacing: 4) {
                // Message text bubble
                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(warmWhite)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .fixedSize(horizontal: false, vertical: true) // FIX: Dynamic height, no empty spaces
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(statusBackgroundColor)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(statusBorderColor, lineWidth: 1)
                    )

                // Status indicator (sending/sent/failed)
                if let status = message.status {
                    statusView(for: status)
                }
            }
        }
    }

    // MARK: - Assistant Bubble

    private var assistantBubbleView: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(message.text)
                .font(.system(size: 15))
                .foregroundColor(warmWhite)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .fixedSize(horizontal: false, vertical: true) // FIX: Dynamic height
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

    // MARK: - Status Views

    @ViewBuilder
    private func statusView(for status: MessageStatus) -> some View {
        switch status {
        case .sending:
            HStack(spacing: 4) {
                ProgressView()
                    .progressViewStyle(CircularProgressViewStyle(tint: warmWhite.opacity(0.6)))
                    .scaleEffect(0.7)

                Text("chat.messageSending".localized)
                    .font(.system(size: 11))
                    .foregroundColor(warmWhite.opacity(0.6))
            }
            .padding(.trailing, 4)

        case .sent:
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 12))
                .foregroundColor(Color.travelBuddyOrange.opacity(0.7))
                .padding(.trailing, 4)

        case .failed:
            VStack(alignment: .trailing, spacing: 4) {
                // Error icon and message
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(.red)

                    if let errorMsg = message.errorMessage {
                        Text(errorMsg)
                            .font(.system(size: 11))
                            .foregroundColor(.red)
                            .lineLimit(2)
                    }
                }

                // Retry button
                if let onRetry = message.onRetry {
                    Button(action: onRetry) {
                        Text("common.button.retry".localized)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(Color.travelBuddyOrange)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(
                                Capsule()
                                    .fill(Color.travelBuddyOrange.opacity(0.15))
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.trailing, 4)
        }
    }

    // MARK: - Status Colors

    private var statusBackgroundColor: Color {
        if message.status == .failed {
            return Color.red.opacity(0.12)
        }
        return userFill
    }

    private var statusBorderColor: Color {
        if message.status == .failed {
            return Color.red.opacity(0.5)
        }
        return Color.travelBuddyOrange.opacity(0.6)
    }
}
