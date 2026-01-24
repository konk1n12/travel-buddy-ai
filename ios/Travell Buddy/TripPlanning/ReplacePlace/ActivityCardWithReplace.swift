//
//  ActivityCardWithReplace.swift
//  Travell Buddy
//
//  Activity card component with replace functionality (ellipsis button + overlay).
//

import SwiftUI

struct ActivityCardWithReplace: View {
    let activity: TripActivity
    let dayIndex: Int
    let stopIndex: Int
    let isFinding: Bool
    let showReplacedBadge: Bool
    let onTapCard: () -> Void
    let onTapReplace: () -> Void
    let onCancelReplace: (() -> Void)?

    @State private var showMenu: Bool = false

    private let showsThumbnail: Bool
    private let isMustSee: Bool
    private let mealBadge: String?

    init(
        activity: TripActivity,
        dayIndex: Int,
        stopIndex: Int,
        isFinding: Bool,
        showReplacedBadge: Bool,
        onTapCard: @escaping () -> Void,
        onTapReplace: @escaping () -> Void,
        onCancelReplace: (() -> Void)? = nil
    ) {
        self.activity = activity
        self.dayIndex = dayIndex
        self.stopIndex = stopIndex
        self.isFinding = isFinding
        self.showReplacedBadge = showReplacedBadge
        self.onTapCard = onTapCard
        self.onTapReplace = onTapReplace
        self.onCancelReplace = onCancelReplace

        self.showsThumbnail = activity.category == .museum || activity.category == .viewpoint || activity.category == .walk
        self.isMustSee = activity.note?.localizedCaseInsensitiveContains("must") == true || activity.category == .museum
        self.mealBadge = Self.mealTitle(for: activity)
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            // Main card content
            Button(action: onTapCard) {
                cardContent
            }
            .buttonStyle(.plain)
            .disabled(isFinding)

            // "Finding alternatives" overlay
            if isFinding {
                findingOverlay
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            }

            // "Replaced" badge
            if showReplacedBadge {
                replacedBadge
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.8).combined(with: .opacity),
                        removal: .opacity
                    ))
            }

            // Ellipsis menu button (only when not finding)
            if !isFinding {
                ellipsisButton
                    .padding(.top, 10)
                    .padding(.trailing, 10)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: isFinding)
        .animation(.spring(response: 0.4, dampingFraction: 0.7), value: showReplacedBadge)
    }

    // MARK: - Card Content

    private var cardContent: some View {
        HStack(alignment: .top, spacing: 12) {
            if showsThumbnail {
                thumbnailView
            }

            VStack(alignment: .leading, spacing: 6) {
                if let mealBadge {
                    badge(text: mealBadge, tint: Color.white.opacity(0.12), textColor: .white.opacity(0.85))
                } else if isMustSee {
                    badge(text: "MUST SEE", tint: Color.travelBuddyOrange.opacity(0.18), textColor: Color.travelBuddyOrange)
                }

                Text(activity.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                Text(activity.description)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.65))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                if let note = activity.note {
                    Text(note)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }
            }

            Spacer()

            // Map pin icon (shifted up a bit to make room for ellipsis)
            VStack {
                Spacer()
                Image(systemName: "mappin.and.ellipse")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white.opacity(0.5))
                Spacer()
            }
            .frame(width: 24)
        }
        .padding(14)
        .padding(.trailing, 20) // Extra padding for ellipsis button area
        .background(cardBackground)
    }

    // MARK: - Ellipsis Button

    private var ellipsisButton: some View {
        Menu {
            Button(action: onTapReplace) {
                Label("Заменить место", systemImage: "arrow.triangle.2.circlepath")
            }
        } label: {
            Image(systemName: "ellipsis")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(.white.opacity(0.6))
                .frame(width: 32, height: 32)
                .background(
                    Circle()
                        .fill(Color.black.opacity(0.3))
                )
        }
    }

    // MARK: - Finding Overlay

    private var findingOverlay: some View {
        ZStack {
            // Dimming + blur
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.black.opacity(0.5))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))

            // Content
            VStack(spacing: 12) {
                // Shimmer progress indicator
                ShimmerProgressView()

                Text("Поиск альтернатив...")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
            }

            // Cancel button
            if let onCancelReplace = onCancelReplace {
                VStack {
                    HStack {
                        Spacer()
                        Button(action: onCancelReplace) {
                            Image(systemName: "xmark")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundColor(.white.opacity(0.7))
                                .frame(width: 26, height: 26)
                                .background(
                                    Circle()
                                        .fill(Color.white.opacity(0.15))
                                )
                        }
                        .buttonStyle(.plain)
                        .padding(10)
                    }
                    Spacer()
                }
            }
        }
    }

    // MARK: - Replaced Badge

    private var replacedBadge: some View {
        VStack {
            HStack {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12, weight: .semibold))
                    Text("Заменено")
                        .font(.system(size: 11, weight: .bold))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                    Capsule()
                        .fill(Color.green.opacity(0.9))
                )
                .shadow(color: Color.green.opacity(0.4), radius: 8, x: 0, y: 4)

                Spacer()
            }
            .padding(.top, 10)
            .padding(.leading, 10)

            Spacer()
        }
    }

    // MARK: - Helpers

    private var thumbnailView: some View {
        ZStack {
            LinearGradient(
                colors: [
                    categoryColor.opacity(0.9),
                    categoryColor.opacity(0.4)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Image(systemName: categoryIcon)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)
        }
        .frame(width: 44, height: 44)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func badge(text: String, tint: Color, textColor: Color) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(textColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(tint)
            )
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 20, style: .continuous)
            .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.7))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .shadow(color: Color.black.opacity(0.25), radius: 12, x: 0, y: 8)
    }

    private var categoryColor: Color {
        switch activity.category {
        case .food: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .walk: return Color(red: 0.26, green: 0.66, blue: 0.45)
        case .museum: return Color(red: 0.42, green: 0.48, blue: 0.95)
        case .viewpoint: return Color(red: 0.15, green: 0.6, blue: 0.9)
        case .nightlife: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .other: return Color(.systemGray)
        }
    }

    private var categoryIcon: String {
        switch activity.category {
        case .food: return "fork.knife"
        case .walk: return "figure.walk"
        case .museum: return "building.columns"
        case .viewpoint: return "binoculars"
        case .nightlife: return "moon.stars.fill"
        case .other: return "star.fill"
        }
    }

    private static func mealTitle(for activity: TripActivity) -> String? {
        guard activity.category == .food else { return nil }
        let hour = Int(activity.time.prefix(2)) ?? 12
        switch hour {
        case 5..<11:
            return "Завтрак"
        case 11..<16:
            return "Обед"
        case 16..<22:
            return "Ужин"
        default:
            return "Еда"
        }
    }
}

// MARK: - Shimmer Progress View

private struct ShimmerProgressView: View {
    @State private var isAnimating = false

    var body: some View {
        ZStack {
            // Track
            Capsule()
                .fill(Color.white.opacity(0.15))
                .frame(width: 120, height: 4)

            // Shimmer
            Capsule()
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.1),
                            Color.white.opacity(0.6),
                            Color.white.opacity(0.1)
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(width: 40, height: 4)
                .offset(x: isAnimating ? 50 : -50)
        }
        .frame(width: 120)
        .clipShape(Capsule())
        .onAppear {
            withAnimation(
                .easeInOut(duration: 0.8)
                .repeatForever(autoreverses: true)
            ) {
                isAnimating = true
            }
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ActivityCardWithReplace_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 20) {
            // Normal state
            ActivityCardWithReplace(
                activity: TripActivity(
                    id: UUID(),
                    time: "10:00",
                    endTime: "12:00",
                    title: "Musee du Louvre",
                    description: "World-famous art museum",
                    category: .museum,
                    address: "Rue de Rivoli",
                    note: "Must see Mona Lisa",
                    latitude: 48.8606,
                    longitude: 2.3376,
                    travelPolyline: nil,
                    rating: 4.8,
                    tags: ["Art", "History"],
                    poiId: "ChIJD3uTd9hx5kcR1IQvGfr8dbk",
                    travelTimeMinutes: nil,
                    travelDistanceMeters: nil
                ),
                dayIndex: 0,
                stopIndex: 1,
                isFinding: false,
                showReplacedBadge: false,
                onTapCard: {},
                onTapReplace: {}
            )

            // Finding state
            ActivityCardWithReplace(
                activity: TripActivity(
                    id: UUID(),
                    time: "14:00",
                    endTime: "15:30",
                    title: "Cafe de Flore",
                    description: "Historic Parisian cafe",
                    category: .food,
                    address: "172 Boulevard Saint-Germain",
                    note: nil,
                    latitude: 48.8541,
                    longitude: 2.3334,
                    travelPolyline: nil,
                    rating: 4.4,
                    tags: ["Cafe", "Classic"],
                    poiId: nil,
                    travelTimeMinutes: nil,
                    travelDistanceMeters: nil
                ),
                dayIndex: 0,
                stopIndex: 2,
                isFinding: true,
                showReplacedBadge: false,
                onTapCard: {},
                onTapReplace: {}
            )

            // Replaced badge state
            ActivityCardWithReplace(
                activity: TripActivity(
                    id: UUID(),
                    time: "16:00",
                    endTime: "17:00",
                    title: "Eiffel Tower",
                    description: "Iconic Parisian landmark",
                    category: .viewpoint,
                    address: "Champ de Mars",
                    note: nil,
                    latitude: 48.8584,
                    longitude: 2.2945,
                    travelPolyline: nil,
                    rating: 4.7,
                    tags: ["Landmark", "Views"],
                    poiId: nil,
                    travelTimeMinutes: nil,
                    travelDistanceMeters: nil
                ),
                dayIndex: 0,
                stopIndex: 3,
                isFinding: false,
                showReplacedBadge: true,
                onTapCard: {},
                onTapReplace: {}
            )
        }
        .padding()
        .background(Color(red: 0.10, green: 0.10, blue: 0.12))
        .preferredColorScheme(.dark)
    }
}
#endif
