//
//  HomeStyle.swift
//  Travell Buddy
//
//  Shared style tokens for Home screen matching HTML design.
//

import SwiftUI
import UIKit

enum HomeStyle {

    // MARK: - Colors (exact values from HTML/Tailwind)
    enum Colors {
        // Background: #0f0f11
        static let background = Color(red: 15/255, green: 15/255, blue: 17/255)

        // Primary: #f97a1f
        static let primary = Color(red: 249/255, green: 122/255, blue: 31/255)

        // Glass surfaces
        static let glassSurface = Color.white.opacity(0.05)      // rgba(255,255,255,0.05)
        static let glassBorder = Color.white.opacity(0.1)        // rgba(255,255,255,0.1)

        // Panel fills
        static let panelFill = Color(red: 30/255, green: 30/255, blue: 30/255).opacity(0.5)  // rgba(30,30,30,0.5)
        static let panelFillStrong = Color.black.opacity(0.4)    // bg-black/40

        // Text colors
        static let textMuted = Color.white.opacity(0.4)          // text-white/40
        static let textMutedSoft = Color.white.opacity(0.6)      // text-white/60

        // Tab bar: rgba(18,18,20,0.85)
        static let tabBarFill = Color(red: 18/255, green: 18/255, blue: 20/255).opacity(0.85)
        static let tabBarBorder = Color.white.opacity(0.08)      // border-white/8

        // Card badge border (for notification dot)
        static let badgeBorder = Color(red: 45/255, green: 45/255, blue: 45/255) // #2d2d2d
    }

    // MARK: - Corner Radii
    enum Radius {
        static let heroBottom: CGFloat = 40      // rounded-b-[2.5rem] = 40px
        static let panel: CGFloat = 32           // rounded-[32px]
        static let card: CGFloat = 24            // rounded-[24px] / rounded-[1.5rem]
        static let thumb: CGFloat = 16           // rounded-2xl = 16px
        static let chip: CGFloat = 9999          // rounded-full
        static let tabBar: CGFloat = 32          // rounded-t-[2rem]
    }

    // MARK: - Layout Constants
    enum Layout {
        // Global spacing
        static let horizontalPadding: CGFloat = 16    // Consistent horizontal padding
        static let sectionSpacing: CGFloat = 20       // Vertical spacing between sections
        static let tabBarHeight: CGFloat = 96         // Actual tab bar height
        static let tabBarClearance: CGFloat = 112     // Bottom padding to clear tab bar
        static let heroHeightRatio: CGFloat = 0.48    // Reduced hero height

        // Header
        static let headerTopPadding: CGFloat = 14
        static let headerHorizontalPadding: CGFloat = 16
        static let avatarSize: CGFloat = 44
        static let avatarInnerSize: CGFloat = 40

        // CTA Button
        static let ctaHeight: CGFloat = 48
        static let ctaHorizontalPadding: CGFloat = 24
        static let ctaIndicatorSpacing: CGFloat = 16  // Spacing between CTA and dots

        // Action Panel - reduced for compactness
        static let actionPanelPadding: CGFloat = 10
        static let actionPanelGap: CGFloat = 10
        static let iconBadgeSizeLarge: CGFloat = 36
        static let iconBadgeSizeSmall: CGFloat = 32
        static let bottomButtonHeight: CGFloat = 48
        static let hotelCardHeight: CGFloat = 130     // Fixed hotel card height

        // Trip Cards
        static let tripCardWidth: CGFloat = 200
        static let tripCardHeight: CGFloat = 240

        // Destination Rows
        static let destinationThumbSize: CGFloat = 56

        // Tab Bar
        static let tabBarTopPadding: CGFloat = 8
        static let tabBarBottomPadding: CGFloat = 24
        static let tabBarHorizontalPadding: CGFloat = 24
        static let tabIconSize: CGFloat = 24
    }

    // MARK: - Shadows
    enum Shadows {
        static let primaryGlow = Color(red: 249/255, green: 122/255, blue: 31/255).opacity(0.3)
        static let primaryGlowLight = Color(red: 249/255, green: 122/255, blue: 31/255).opacity(0.2)
        static let cardShadow = Color.black.opacity(0.35)
    }
}

// MARK: - Glass Panel Modifier

struct GlassPanel: ViewModifier {
    let cornerRadius: CGFloat
    let blurRadius: CGFloat
    let fill: Color
    let border: Color

    func body(content: Content) -> some View {
        content
            .background(fill)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(border, lineWidth: 1)
            )
    }
}

extension View {
    func glassPanel(cornerRadius: CGFloat, blur: CGFloat = 24, fill: Color, border: Color) -> some View {
        modifier(GlassPanel(cornerRadius: cornerRadius, blurRadius: blur, fill: fill, border: border))
    }
}

// MARK: - Rounded Corner Shape (for bottom-only rounding)

struct RoundedCornerShape: Shape {
    let radius: CGFloat
    let corners: UIRectCorner

    func path(in rect: CGRect) -> Path {
        let path = UIBezierPath(
            roundedRect: rect,
            byRoundingCorners: corners,
            cornerRadii: CGSize(width: radius, height: radius)
        )
        return Path(path.cgPath)
    }
}

// MARK: - Top Rounded Corner Shape (for TabBar)

struct TopRoundedRectangle: Shape {
    let radius: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: 0, y: rect.maxY))
        path.addLine(to: CGPoint(x: 0, y: radius))
        path.addArc(
            center: CGPoint(x: radius, y: radius),
            radius: radius,
            startAngle: .degrees(180),
            endAngle: .degrees(270),
            clockwise: false
        )
        path.addLine(to: CGPoint(x: rect.maxX - radius, y: 0))
        path.addArc(
            center: CGPoint(x: rect.maxX - radius, y: radius),
            radius: radius,
            startAngle: .degrees(270),
            endAngle: .degrees(0),
            clockwise: false
        )
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
