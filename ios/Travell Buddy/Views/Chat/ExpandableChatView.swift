//
//  ExpandableChatView.swift
//  Travell Buddy
//
//  Expandable chat with compact and full-screen modes.
//

import SwiftUI

/// Expandable chat container with compact bar and full-screen mode
struct ExpandableChatView: View {
    @ObservedObject var viewModel: ChatViewModel
    @State private var isExpanded: Bool = false
    @State private var messageText: String = ""
    @FocusState private var isTextFieldFocused: Bool

    // Design tokens
    private let warmWhite = Color(red: 0.95, green: 0.94, blue: 0.92)
    private let glassFill = Color.white.opacity(0.08)
    private let glassBorder = Color.white.opacity(0.14)

    // Heights
    private let compactHeight: CGFloat = 70
    private var expandedHeight: CGFloat {
        UIScreen.main.bounds.height * 0.85
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            // Dimmed background overlay (only when expanded)
            if isExpanded {
                Color.black.opacity(0.4)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            isExpanded = false
                            isTextFieldFocused = false
                        }
                    }
                    .transition(.opacity)
            }

            // Chat container
            VStack(spacing: 0) {
                if isExpanded {
                    // Drag handle
                    dragHandle
                }

                // Content
                if isExpanded {
                    // Full chat view
                    ChatView(viewModel: viewModel)
                        .frame(height: expandedHeight - 40)
                } else {
                    // Compact preview bar
                    compactChatBar
                        .frame(height: compactHeight)
                }
            }
            .background(
                RoundedRectangle(cornerRadius: isExpanded ? 24 : 18, style: .continuous)
                    .fill(Color.black.opacity(0.90))
                    .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: -10)
            )
            .animation(.spring(response: 0.4, dampingFraction: 0.8), value: isExpanded)
        }
        .ignoresSafeArea(edges: isExpanded ? .all : .bottom)
        .onChange(of: isTextFieldFocused) { focused in
            if focused && !isExpanded {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    isExpanded = true
                }
            }
        }
    }

    // MARK: - Compact Chat Bar

    private var compactChatBar: some View {
        HStack(spacing: 12) {
            // AI icon
            ZStack {
                Circle()
                    .fill(glassFill)
                    .frame(width: 44, height: 44)

                Image(systemName: "sparkles")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(Color.travelBuddyOrange)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("Travel Buddy AI")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(warmWhite)

                if viewModel.isAssistantTyping {
                    HStack(spacing: 4) {
                        ProgressView()
                            .scaleEffect(0.6)
                            .tint(Color.travelBuddyOrange)
                        Text("печатает...")
                            .font(.system(size: 11))
                            .foregroundColor(warmWhite.opacity(0.6))
                    }
                } else if let lastMessage = viewModel.messages.last, !lastMessage.isFromUser {
                    Text(lastMessage.text)
                        .font(.system(size: 12))
                        .foregroundColor(warmWhite.opacity(0.7))
                        .lineLimit(1)
                } else {
                    Text("Напишите свои пожелания")
                        .font(.system(size: 12))
                        .foregroundColor(warmWhite.opacity(0.6))
                }
            }

            Spacer()

            // Expand button
            Button {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    isExpanded = true
                }
            } label: {
                Image(systemName: "chevron.up")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(warmWhite.opacity(0.6))
                    .frame(width: 32, height: 32)
                    .background(
                        Circle()
                            .fill(glassFill)
                    )
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .onTapGesture {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                isExpanded = true
            }
        }
    }

    // MARK: - Drag Handle

    private var dragHandle: some View {
        VStack(spacing: 8) {
            // Visual handle
            RoundedRectangle(cornerRadius: 3)
                .fill(Color.white.opacity(0.3))
                .frame(width: 40, height: 4)
                .padding(.top, 12)
                .padding(.bottom, 8)
        }
        .contentShape(Rectangle())
        .gesture(
            DragGesture()
                .onEnded { value in
                    // Collapse if dragged down more than 100pt
                    if value.translation.height > 100 {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            isExpanded = false
                            isTextFieldFocused = false
                        }
                    }
                }
        )
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        Color.gray.ignoresSafeArea()

        VStack {
            Spacer()

            ExpandableChatView(
                viewModel: ChatViewModel(
                    tripId: nil, // Demo mode
                    initialMessages: []
                )
            )
        }
    }
}
