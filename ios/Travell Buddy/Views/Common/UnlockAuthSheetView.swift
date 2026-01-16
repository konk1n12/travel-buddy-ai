//
//  UnlockAuthSheetView.swift
//  Travell Buddy
//
//  Premium glassmorphism auth sheet UI for guest gating.
//  Design: "Quiet Luxury" — dark, soft, cinematic.
//

import SwiftUI
import AuthenticationServices

// MARK: - Quiet Luxury Theme Constants

private enum QuietLuxury {
    // Surface colors
    static let surfaceBg = Color.black.opacity(0.45)
    static let surfaceBorder = Color.white.opacity(0.10)
    static let surfaceHighlight = Color.white.opacity(0.06)

    // Text hierarchy
    static let primaryText = Color.white.opacity(0.94)
    static let secondaryText = Color.white.opacity(0.68)
    static let tertiaryText = Color.white.opacity(0.48)

    // Accent (orange) — subtle
    static let accentOrange = Color.travelBuddyOrange
    static let accentOrangeMuted = Color.travelBuddyOrange.opacity(0.85)
    static let accentChipBg = Color.travelBuddyOrange.opacity(0.12)
    static let accentChipBorder = Color.travelBuddyOrange.opacity(0.55)

    // Background layers — lighter dim for "airy" feel like Preferences screen
    static let dimOverlay = Color.black.opacity(0.30)
    static let warmTint = Color.travelBuddyOrange.opacity(0.10)

    // Button backgrounds
    static let buttonDarkBg = Color.black.opacity(0.32)
    static let buttonBorder = Color.white.opacity(0.10)
    static let buttonText = Color.white.opacity(0.88)

    // Shadows
    static let cardShadow = Color.black.opacity(0.45)
    static let cardShadowRadius: CGFloat = 32
    static let cardShadowY: CGFloat = 18

    // Icon opacity
    static let iconOpacity: Double = 0.80
}

struct UnlockAuthSheetView: View {
    let dayNumber: Int?
    let unlockedFeaturesLabel: String
    let subtitle: String?
    let footerText: String
    let isLoading: Bool
    let isAppleLoading: Bool
    let isGoogleLoading: Bool
    let errorText: String?
    let onClose: () -> Void
    let onAppleRequest: (ASAuthorizationAppleIDRequest) -> Void
    let onAppleCompletion: (Result<ASAuthorization, Error>) -> Void
    let onEmail: () -> Void
    let onGoogle: () -> Void

    private var resolvedSubtitle: String {
        if let subtitle {
            return subtitle
        }
        if let dayNumber {
            return "День \(dayNumber) доступен после входа"
        }
        return "Доступно после входа"
    }

    var body: some View {
        ZStack {
            UnlockAuthBackground()

            GeometryReader { proxy in
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 16) {
                        TopSheetControls(onClose: onClose)

                        Spacer(minLength: 4)

                        GlassCard {
                            VStack(spacing: 16) {
                                LockHeaderView(unlockedFeaturesLabel: unlockedFeaturesLabel)

                                VStack(spacing: 8) {
                                    Text("Разблокируйте полный маршрут")
                                        .font(.system(size: 26, weight: .bold, design: .rounded))
                                        .foregroundColor(QuietLuxury.primaryText)
                                        .multilineTextAlignment(.center)
                                        .lineSpacing(2)
                                        .minimumScaleFactor(0.85)

                                    Text(resolvedSubtitle)
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(QuietLuxury.secondaryText)
                                        .multilineTextAlignment(.center)
                                }
                                .padding(.bottom, 4)

                                VStack(spacing: 12) {
                                    ZStack {
                                        SignInWithAppleButton(.signIn, onRequest: onAppleRequest, onCompletion: onAppleCompletion)
                                            .signInWithAppleButtonStyle(.white)
                                            .frame(height: 52)
                                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                                            .opacity(isAppleLoading ? 0.7 : 1)
                                            .disabled(isLoading)
                                            .modifier(PressableScaleEffect())

                                        if isAppleLoading {
                                            ProgressView()
                                                .tint(.black)
                                        }
                                    }

                                    Button(action: onEmail) {
                                        AuthRowLabel(
                                            title: "Продолжить по email",
                                            isLoading: false,
                                            leading: {
                                                Image(systemName: "envelope.fill")
                                                    .foregroundColor(.white.opacity(QuietLuxury.iconOpacity))
                                            }
                                        )
                                    }
                                    .buttonStyle(PrimaryButtonStyle())
                                    .disabled(isLoading)

                                    Button(action: onGoogle) {
                                        AuthRowLabel(
                                            title: "Продолжить с Google",
                                            isLoading: isGoogleLoading,
                                            leading: {
                                                GoogleMarkView()
                                            }
                                        )
                                    }
                                    .buttonStyle(SecondaryGlassButtonStyle())
                                    .disabled(isLoading)
                                }

                                if let errorText {
                                    Text(errorText)
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundColor(.red.opacity(0.9))
                                        .multilineTextAlignment(.center)
                                }
                            }
                        }

                        Spacer(minLength: 8)

                        Text(footerText)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(QuietLuxury.tertiaryText)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 28)
                    }
                    .frame(minHeight: proxy.size.height)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 16)
                }
            }
        }
    }
}

private struct UnlockAuthBackground: View {
    var body: some View {
        ZStack {
            // Reuse SmokyBackgroundView from Preferences/NewTrip screen
            // for consistent "airy" and warm feel across the app
            SmokyBackgroundView()

            // Light dim overlay to ensure card readability
            // Much lighter than before (0.30 vs 0.62)
            Rectangle()
                .fill(QuietLuxury.dimOverlay)
        }
        .ignoresSafeArea()
    }
}

private struct TopSheetControls: View {
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            Capsule()
                .fill(Color.white.opacity(0.25))
                .frame(width: 36, height: 5)

            HStack {
                Button("Закрыть", action: onClose)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(QuietLuxury.secondaryText)

                Spacer()
            }
        }
    }
}

private struct GlassCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(.horizontal, 22)
            .padding(.vertical, 20)
            .frame(maxWidth: 440)
            .background(GlassCardBackground())
    }
}

private struct GlassCardBackground: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 28, style: .continuous)
            // Glass material base — visible blur behind card
            .fill(.ultraThinMaterial)
            .background(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    // Semi-transparent dark fill for readability
                    .fill(Color.black.opacity(0.38))
            )
            // Subtle inner highlight at top
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.08),
                                Color.clear
                            ],
                            startPoint: .top,
                            endPoint: .center
                        )
                    )
            )
            // Soft border
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
            )
            // Gentle shadow for depth
            .shadow(
                color: Color.black.opacity(0.35),
                radius: 28,
                x: 0,
                y: 14
            )
    }
}

private struct LockHeaderView: View {
    let unlockedFeaturesLabel: String

    var body: some View {
        VStack(spacing: 14) {
            // Lock icon container — darker, more subtle
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.black.opacity(0.35))
                .frame(width: 60, height: 60)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(QuietLuxury.surfaceBorder, lineWidth: 1)
                )
                .overlay(
                    Image(systemName: "lock.fill")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundColor(QuietLuxury.accentOrangeMuted)
                )

            // Feature chip — subtle accent
            Text(unlockedFeaturesLabel)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(QuietLuxury.accentOrangeMuted)
                .padding(.horizontal, 12)
                .padding(.vertical, 5)
                .background(
                    Capsule()
                        .stroke(QuietLuxury.accentChipBorder, lineWidth: 1)
                        .background(Capsule().fill(QuietLuxury.accentChipBg))
                )
        }
    }
}

private struct AuthRowLabel<Leading: View>: View {
    let title: String
    let isLoading: Bool
    let leading: Leading

    init(title: String, isLoading: Bool, @ViewBuilder leading: () -> Leading) {
        self.title = title
        self.isLoading = isLoading
        self.leading = leading()
    }

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                if isLoading {
                    ProgressView()
                        .tint(.white.opacity(0.8))
                } else {
                    leading
                }
            }
            .frame(width: 20, height: 20)

            Text(title)
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(QuietLuxury.buttonText)

            Spacer()
        }
        .padding(.horizontal, 16)
        .frame(height: 52)
    }
}

private struct GoogleMarkView: View {
    private let gradient = AngularGradient(
        gradient: Gradient(stops: [
            .init(color: Color(red: 0.26, green: 0.52, blue: 0.96), location: 0.0),
            .init(color: Color(red: 0.91, green: 0.26, blue: 0.20), location: 0.25),
            .init(color: Color(red: 0.98, green: 0.78, blue: 0.18), location: 0.5),
            .init(color: Color(red: 0.20, green: 0.78, blue: 0.35), location: 0.75),
            .init(color: Color(red: 0.26, green: 0.52, blue: 0.96), location: 1.0)
        ]),
        center: .center
    )

    var body: some View {
        Text("G")
            .font(.system(size: 17, weight: .bold, design: .rounded))
            .foregroundStyle(gradient)
            .opacity(0.88) // Slightly muted for quiet luxury
    }
}

private struct PressableScaleEffect: ViewModifier {
    @GestureState private var isPressed: Bool = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(isPressed ? 0.98 : 1)
            .opacity(isPressed ? 0.9 : 1)
            .animation(.easeOut(duration: 0.12), value: isPressed)
            .simultaneousGesture(
                DragGesture(minimumDistance: 0)
                    .updating($isPressed) { _, state, _ in
                        state = true
                    }
            )
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(QuietLuxury.buttonDarkBg)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(QuietLuxury.buttonBorder, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct SecondaryGlassButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.black.opacity(0.28))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(QuietLuxury.buttonBorder, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
