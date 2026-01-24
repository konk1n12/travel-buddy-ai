//
//  AppDesign.swift
//  Travell Buddy
//
//  Created by Gemini on 05.01.2026.
//

import SwiftUI

enum AppDesign {
    
    enum Colors {
        static let background = Color("TBBackground")
        static let textPrimary = Color("TBTextPrimary")
        static let textSecondary = Color("TBTextSecondary")
        static let accentOrange = Color("TBAccentOrange")
        static let accentOrangeLight = Color("TBAccentOrangeLight")
        static let cardBackground = Color("TBCardBackground")
        static let cardBorder = Color("TBCardBorder")
        static let cardWarm = Color(red: 0.93, green: 0.88, blue: 0.85, opacity: 0.82)
        static let cardIconBackground = Color(red: 0.90, green: 0.88, blue: 0.86, opacity: 0.9)
        static let heroTop = Color(red: 0.82, green: 0.83, blue: 0.80)
        static let heroBottom = Color(red: 0.97, green: 0.88, blue: 0.80)
        static let heroOverlay = Color(red: 0.98, green: 0.93, blue: 0.86, opacity: 0.35)
        static let heroMountain = Color(red: 0.54, green: 0.56, blue: 0.54)
        static let tabMuted = Color(red: 0.54, green: 0.61, blue: 0.58)
        static let pillDark = Color(red: 0.20, green: 0.22, blue: 0.24, opacity: 0.75)
    }

    enum HomeColors {
        static let background = Color(red: 0.984, green: 0.965, blue: 0.937) // #FBF6EF
        static let mistGreen = Color(red: 0.867, green: 0.922, blue: 0.890) // #DDEBE3
        static let textPrimary = Color(red: 0.078, green: 0.082, blue: 0.098) // #141519
        static let textSecondary = Color(red: 0.180, green: 0.227, blue: 0.290) // #2E3A4A
        static let accentOrange = Color(red: 1.000, green: 0.478, blue: 0.239) // #FF7A3D
        static let borderGreen = Color(red: 0.059, green: 0.239, blue: 0.180) // #0F3D2E
        static let scrim = Color(red: 0.984, green: 0.965, blue: 0.937) // #FBF6EF
        static let glassFill = Color(red: 0.984, green: 0.965, blue: 0.937, opacity: 0.52)
        static let glassHighlight = Color.white.opacity(0.35)
    }
    
    enum Fonts {
        static func regular(size: CGFloat) -> Font {
            .system(size: size, weight: .regular)
        }
        
        static func medium(size: CGFloat) -> Font {
            .system(size: size, weight: .medium)
        }
        
        static func semibold(size: CGFloat) -> Font {
            .system(size: size, weight: .semibold)
        }
        
        static func bold(size: CGFloat) -> Font {
            .system(size: size, weight: .bold)
        }
        
        static let greeting = medium(size: 14)
        static let name = semibold(size: 16)

        static let heroTitle = bold(size: 32)
        static let heroSubtitle = regular(size: 15)

        static let cardTitle = semibold(size: 18)
        static let cardSubtitle = regular(size: 14)
        static let cardCTA = semibold(size: 13)

        static let miniCardTitle = semibold(size: 14)

        static let sectionHeader = bold(size: 18)
        static let sectionLink = semibold(size: 14)

        static let tripPill = semibold(size: 12)
        static let tripTitle = semibold(size: 16)
        static let tripCountry = regular(size: 13)

        static let tabBarLabel: CGFloat = 10
    }
    
    enum CornerRadius {
        static let small: CGFloat = 8
        static let medium: CGFloat = 18
        static let large: CGFloat = 24
        static let pill: CGFloat = 999
    }
    
    enum Shadows {
        static let card = ShadowStyle(color: .black.opacity(0.08), radius: 14, x: 0, y: 8)
        static let cardGlow = ShadowStyle(color: Colors.accentOrange.opacity(0.25), radius: 20, x: 0, y: -8)
        static let soft = ShadowStyle(color: .black.opacity(0.05), radius: 8, x: 0, y: 4)
    }
    
    struct ShadowStyle {
        let color: Color
        let radius: CGFloat
        let x: CGFloat
        let y: CGFloat
    }
}

// MARK: - View Modifiers for easy use

extension View {
    func shadow(_ style: AppDesign.ShadowStyle) -> some View {
        self.shadow(color: style.color, radius: style.radius, x: style.x, y: style.y)
    }
}

// These color assets need to be created in Assets.xcassets
/*
 1.  TBBackground: Off-white, e.g., #F9F8F7
 2.  TBTextPrimary: Near-black, e.g., #1C1C1E
 3.  TBTextSecondary: Muted gray-blue, e.g., #8A8A8E
 4.  TBAccentOrange: Bright orange, e.g., #FF6B00
 5.  TBAccentOrangeLight: Lighter orange for gradients/glows, e.g., #FF8C40
 6.  TBCardBackground: Translucent off-white for glass effect, e.g., #FFFFFF at 80% opacity
 7.  TBCardBorder: Subtle border for cards, e.g., #FFFFFF at 50% opacity
 */
