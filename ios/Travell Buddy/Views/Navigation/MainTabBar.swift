//
//  MainTabBar.swift
//  Travell Buddy
//
//  Custom glass tab bar for main navigation.
//

import SwiftUI

enum MainTab: Hashable, CaseIterable {
    case home
    case newTrip
    case savedTrips
    case profile

    var title: String {
        switch self {
        case .home:
            return "tabs.home".localized
        case .newTrip:
            return "newTrip.title".localized
        case .savedTrips:
            return "home.myTrips".localized
        case .profile:
            return "tabs.profile".localized
        }
    }

    var systemImage: String {
        switch self {
        case .home:
            return "house.fill"
        case .newTrip:
            return "magnifyingglass"
        case .savedTrips:
            return "bookmark"
        case .profile:
            return "person"
        }
    }

    var protectedAction: ProtectedAction? {
        switch self {
        case .savedTrips:
            return .viewSavedTrips
        case .profile:
            return .viewProfile
        case .home, .newTrip:
            return nil
        }
    }
}

extension Notification.Name {
    static let mainTabSelectionRequested = Notification.Name("mainTabSelectionRequested")
}

struct BottomTabBarView: View {
    let selectedTab: MainTab
    let onSelect: (MainTab) -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Content (icons) with proper padding
            HStack {
                tabButton(.home)
                tabButton(.newTrip)
                tabButton(.savedTrips)
                tabButton(.profile)
            }
            .padding(.horizontal, HomeStyle.Layout.tabBarHorizontalPadding)
            .padding(.top, HomeStyle.Layout.tabBarTopPadding)
            .padding(.bottom, HomeStyle.Layout.tabBarTopPadding)
        }
        .frame(maxWidth: .infinity)
        .background(
            ZStack {
                HomeStyle.Colors.tabBarFill
                    .background(.ultraThinMaterial)
            }
            .clipShape(TopRoundedRectangle(radius: HomeStyle.Radius.tabBar))
            .overlay(
                TopRoundedRectangle(radius: HomeStyle.Radius.tabBar)
                    .stroke(HomeStyle.Colors.tabBarBorder, lineWidth: 1)
            )
            .ignoresSafeArea(edges: .bottom)
        )
    }

    private func tabButton(_ tab: MainTab) -> some View {
        Button {
            onSelect(tab)
        } label: {
            TabBarItem(
                title: tab.title,
                systemImage: tab.systemImage,
                isActive: selectedTab == tab
            )
        }
        .buttonStyle(.plain)
    }
}

private struct TabBarItem: View {
    let title: String
    let systemImage: String
    let isActive: Bool

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: systemImage)
                .font(.system(size: HomeStyle.Layout.tabIconSize, weight: isActive ? .semibold : .regular))
                .symbolVariant(isActive ? .fill : .none)
            Text(title)
                .font(.system(size: 10, weight: .medium))
        }
        .foregroundColor(isActive ? HomeStyle.Colors.primary : HomeStyle.Colors.textMuted)
        .frame(maxWidth: .infinity)
        .frame(minHeight: 44)
    }
}
