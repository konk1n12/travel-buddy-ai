//
//  TravelersPickerStyle.swift
//  Travell Buddy
//
//  Shared styling tokens for TravelersPicker screens.
//

import SwiftUI

enum TravelersPickerStyle {
    enum Colors {
        static let backgroundTop = Color(red: 0.20, green: 0.20, blue: 0.22)
        static let backgroundBottom = Color(red: 0.11, green: 0.11, blue: 0.12)
        static let smoke = Color(red: 0.26, green: 0.26, blue: 0.28)
        static let primaryText = Color(red: 0.96, green: 0.95, blue: 0.93)
        static let secondaryText = Color(red: 0.72, green: 0.69, blue: 0.64)
        static let accent = Color.travelBuddyOrange

        static let cardTint = Color.black.opacity(0.35)
        static let cardStroke = Color.white.opacity(0.10)
        static let cardShadow = Color.black.opacity(0.35)

        static let controlFill = Color.white.opacity(0.08)
        static let controlStroke = Color.white.opacity(0.12)
        static let controlDisabled = Color.white.opacity(0.05)

        static let badgeFillBase = Color.travelBuddyOrange.opacity(0.25)
        static let badgeStroke = Color.travelBuddyOrange.opacity(0.35)
    }

    enum Radius {
        static let card: CGFloat = 20
        static let control: CGFloat = 22
    }

    enum Layout {
        static let horizontalPadding: CGFloat = 20
        static let sectionSpacing: CGFloat = 18
        static let cardPadding: CGFloat = 16
        static let iconSize: CGFloat = 46
        static let controlSize: CGFloat = 44
    }
}
