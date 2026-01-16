//
//  ReplaceOptionsBottomSheet.swift
//  Travell Buddy
//
//  Bottom sheet displaying replacement options for a place.
//

import SwiftUI

struct ReplaceOptionsBottomSheet: View {
    let currentActivityTitle: String
    let dayIndex: Int?
    let stopIndex: Int?
    let options: [ReplacementOption]
    let onSelect: (ReplacementOption) -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Header
            sheetHeader
                .padding(.top, 8)
                .padding(.bottom, 16)

            // Options list
            ScrollView(showsIndicators: false) {
                VStack(spacing: 12) {
                    ForEach(options) { option in
                        OptionCard(option: option) {
                            onSelect(option)
                        }
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 24)
            }

            // Cancel button
            cancelButton
                .padding(.horizontal, 20)
                .padding(.bottom, 16)
        }
        .background(sheetBackground)
    }

    // MARK: - Header

    private var sheetHeader: some View {
        VStack(spacing: 6) {
            // Drag indicator
            RoundedRectangle(cornerRadius: 2.5)
                .fill(Color.white.opacity(0.3))
                .frame(width: 36, height: 5)
                .padding(.bottom, 8)

            Text("Заменить место")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(.white)

            Text(headerSubtitle)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .padding(.horizontal, 40)
        }
    }

    private var headerSubtitle: String {
        var parts: [String] = []

        // Add day/stop info if available
        if let day = dayIndex, let stop = stopIndex {
            parts.append("День \(day + 1) \u{2022} Остановка \(stop + 1)")
        } else if let day = dayIndex {
            parts.append("День \(day + 1)")
        }

        // Add current place name (truncated if needed)
        let truncatedTitle = currentActivityTitle.count > 30
            ? String(currentActivityTitle.prefix(27)) + "..."
            : currentActivityTitle
        parts.append("«\(truncatedTitle)»")

        return parts.joined(separator: " \u{2022} ")
    }

    // MARK: - Cancel Button

    private var cancelButton: some View {
        Button(action: onCancel) {
            Text("Отмена")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.white.opacity(0.9))
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color.white.opacity(0.1))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(Color.white.opacity(0.15), lineWidth: 1)
                        )
                )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Background

    private var sheetBackground: some View {
        LinearGradient(
            colors: [
                Color(red: 0.14, green: 0.08, blue: 0.06),
                Color(red: 0.10, green: 0.06, blue: 0.04)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
    }
}

// MARK: - Option Card

private struct OptionCard: View {
    let option: ReplacementOption
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 14) {
                // Category icon
                categoryIcon

                // Content
                VStack(alignment: .leading, spacing: 6) {
                    // Title
                    Text(option.title)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)

                    // Subtitle row: area + distance
                    HStack(spacing: 8) {
                        Text(option.subtitle)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.6))

                        Text("\u{2022}")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))

                        HStack(spacing: 4) {
                            Image(systemName: "location.fill")
                                .font(.system(size: 9, weight: .semibold))
                            Text(option.distance)
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundColor(.white.opacity(0.5))
                    }

                    // Tags
                    if let tags = option.tags, !tags.isEmpty {
                        HStack(spacing: 6) {
                            ForEach(tags.prefix(3), id: \.self) { tag in
                                Text(tag)
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundColor(.white.opacity(0.7))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(
                                        Capsule()
                                            .fill(Color.white.opacity(0.1))
                                    )
                            }
                        }
                    }
                }

                Spacer()

                // Rating + chevron
                VStack(alignment: .trailing, spacing: 8) {
                    if let rating = option.rating {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(.yellow)
                            Text(String(format: "%.1f", rating))
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(.white.opacity(0.9))
                        }
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.white.opacity(0.4))
                }
            }
            .padding(16)
            .background(cardBackground)
        }
        .buttonStyle(.plain)
    }

    private var categoryIcon: some View {
        ZStack {
            LinearGradient(
                colors: [
                    categoryColor.opacity(0.9),
                    categoryColor.opacity(0.5)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            Image(systemName: categoryIconName)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
        }
        .frame(width: 42, height: 42)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var categoryColor: Color {
        switch option.category {
        case .food: return Color(red: 1.0, green: 0.55, blue: 0.30)
        case .walk: return Color(red: 0.26, green: 0.66, blue: 0.45)
        case .museum: return Color(red: 0.42, green: 0.48, blue: 0.95)
        case .viewpoint: return Color(red: 0.15, green: 0.6, blue: 0.9)
        case .nightlife: return Color(red: 0.7, green: 0.4, blue: 0.9)
        case .other: return Color(.systemGray)
        }
    }

    private var categoryIconName: String {
        switch option.category {
        case .food: return "fork.knife"
        case .walk: return "figure.walk"
        case .museum: return "building.columns"
        case .viewpoint: return "binoculars"
        case .nightlife: return "moon.stars.fill"
        case .other: return "star.fill"
        }
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(Color(red: 0.18, green: 0.18, blue: 0.20).opacity(0.8))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.2), radius: 8, x: 0, y: 4)
    }
}

// MARK: - Preview

#if DEBUG
struct ReplaceOptionsBottomSheet_Previews: PreviewProvider {
    static var previews: some View {
        ReplaceOptionsBottomSheet(
            currentActivityTitle: "Musee du Louvre",
            dayIndex: 0,
            stopIndex: 2,
            options: [
                ReplacementOption(
                    id: UUID(),
                    title: "Musee d'Orsay",
                    subtitle: "Saint-Germain",
                    category: .museum,
                    rating: 4.8,
                    distance: "600 m",
                    tags: ["Impressionism", "Art"],
                    address: "1 Rue de la Legion d'Honneur",
                    poiId: nil,
                    latitude: 48.8600,
                    longitude: 2.3266
                ),
                ReplacementOption(
                    id: UUID(),
                    title: "Centre Pompidou",
                    subtitle: "Beaubourg",
                    category: .museum,
                    rating: 4.6,
                    distance: "450 m",
                    tags: ["Modern Art", "Architecture"],
                    address: "Place Georges-Pompidou",
                    poiId: nil,
                    latitude: 48.8607,
                    longitude: 2.3522
                ),
                ReplacementOption(
                    id: UUID(),
                    title: "Musee Rodin",
                    subtitle: "Invalides",
                    category: .museum,
                    rating: 4.7,
                    distance: "1.1 km",
                    tags: ["Sculpture", "Garden"],
                    address: "77 Rue de Varenne",
                    poiId: nil,
                    latitude: 48.8552,
                    longitude: 2.3158
                )
            ],
            onSelect: { _ in },
            onCancel: {}
        )
        .preferredColorScheme(.dark)
    }
}
#endif
