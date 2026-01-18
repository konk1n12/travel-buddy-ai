//
//  TabBarVisibility.swift
//  Travell Buddy
//
//  Manages tab bar visibility across navigation.
//

import SwiftUI

// MARK: - Tab Bar Visibility Manager

/// Observable object to control tab bar visibility from child views
final class TabBarVisibilityManager: ObservableObject {
    static let shared = TabBarVisibilityManager()

    @Published var isVisible: Bool = true

    private init() {}

    func show() {
        withAnimation(.easeInOut(duration: 0.2)) {
            isVisible = true
        }
    }

    func hide() {
        withAnimation(.easeInOut(duration: 0.2)) {
            isVisible = false
        }
    }
}

// MARK: - Environment Key

private struct TabBarVisibilityKey: EnvironmentKey {
    static let defaultValue: TabBarVisibilityManager = .shared
}

extension EnvironmentValues {
    var tabBarVisibility: TabBarVisibilityManager {
        get { self[TabBarVisibilityKey.self] }
        set { self[TabBarVisibilityKey.self] = newValue }
    }
}

// MARK: - View Modifier for Hiding Tab Bar

struct HideTabBarModifier: ViewModifier {
    @StateObject private var tabBarVisibility = TabBarVisibilityManager.shared

    func body(content: Content) -> some View {
        content
            .onAppear {
                tabBarVisibility.hide()
            }
            .onDisappear {
                tabBarVisibility.show()
            }
    }
}

extension View {
    /// Hides the custom tab bar when this view appears
    func hideTabBar() -> some View {
        modifier(HideTabBarModifier())
    }
}

// MARK: - Conditional Hide Tab Bar Modifier

struct ConditionalHideTabBarModifier: ViewModifier {
    let shouldHide: Bool
    @StateObject private var tabBarVisibility = TabBarVisibilityManager.shared

    func body(content: Content) -> some View {
        content
            .onAppear {
                if shouldHide {
                    tabBarVisibility.hide()
                }
            }
            .onDisappear {
                if shouldHide {
                    tabBarVisibility.show()
                }
            }
    }
}
