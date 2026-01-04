//
//  PlaceDetailsSections.swift
//  Travell Buddy
//

import SwiftUI
import MapKit

struct HeroPhotoSection: View {
    let photos: [PlaceDetailsPhoto]
    @Binding var selectedIndex: Int

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            if photos.isEmpty {
                Rectangle()
                    .fill(LinearGradient(
                        colors: [Color.travelBuddyOrangeLight, Color.travelBuddyOrange],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ))
                    .frame(height: 280)
                    .overlay {
                        Image(systemName: "photo")
                            .font(.system(size: 60))
                            .foregroundColor(.white.opacity(0.6))
                    }
            } else {
                TabView(selection: $selectedIndex) {
                    ForEach(Array(photos.enumerated()), id: \.element.id) { index, photo in
                        AsyncImage(url: photo.url) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            case .failure:
                                Rectangle()
                                    .fill(Color.gray.opacity(0.2))
                                    .overlay {
                                        Image(systemName: "photo")
                                            .foregroundColor(.gray)
                                    }
                            case .empty:
                                Rectangle()
                                    .fill(Color.gray.opacity(0.1))
                                    .overlay {
                                        ProgressView()
                                    }
                            @unknown default:
                                EmptyView()
                            }
                        }
                        .frame(height: 280)
                        .clipped()
                        .tag(index)
                    }
                }
                .frame(height: 280)
                .tabViewStyle(.page(indexDisplayMode: .never))

                if photos.count > 1 {
                    Text("\(selectedIndex + 1)/\(photos.count)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            Capsule()
                                .fill(Color.black.opacity(0.6))
                        )
                        .padding([.trailing, .bottom], DesignSystem.Spacing.medium)
                }
            }
        }
    }
}

struct PlaceIdentitySection: View {
    let name: String
    let categoryLabel: String
    let categoryIcon: String

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.small) {
            Text(name)
                .font(.system(size: 28, weight: .bold))
                .foregroundColor(.primary)

            if !categoryLabel.isEmpty {
                HStack(spacing: DesignSystem.Spacing.small) {
                    Image(systemName: categoryIcon)
                        .foregroundColor(.travelBuddyOrange)
                    Text(categoryLabel)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct StatusRowSection: View {
    let isOpenNow: Bool?
    let nextOpenTime: String?
    let nextCloseTime: String?
    let openingHours: [String]
    let rating: Double?
    let reviewsCount: Int?
    let durationText: String?
    let priceLevel: PriceLevel?

    var body: some View {
        HStack(spacing: 0) {
            if isOpenNow != nil || !openingHours.isEmpty {
                StatusItem(
                    icon: isOpenNow == nil ? "clock.fill" : (isOpenNow == true ? "checkmark.circle.fill" : "xmark.circle.fill"),
                    iconColor: isOpenNow == true ? .green : .red,
                    title: statusTitle,
                    subtitle: statusSubtitle
                )
            }

            if (isOpenNow != nil || !openingHours.isEmpty) && (rating != nil || durationText != nil || priceLevel != nil) {
                Divider().frame(height: 46)
            }

            if let rating = rating {
                StatusItem(
                    icon: "star.fill",
                    iconColor: .yellow,
                    title: String(format: "%.1f", rating),
                    subtitle: ratingSubtitle
                )
            }

            if rating != nil && (durationText != nil || priceLevel != nil) {
                Divider().frame(height: 46)
            }

            if let durationText = durationText {
                StatusItem(
                    icon: "clock.fill",
                    iconColor: .blue,
                    title: durationText,
                    subtitle: "Визит"
                )
            }

            if let priceLevel = priceLevel {
                StatusItem(
                    icon: "dollarsign.circle.fill",
                    iconColor: .green,
                    title: priceLevel.displayText,
                    subtitle: "Цена"
                )
            }
        }
        .padding(.vertical, 16)
        .padding(.horizontal, 12)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
        .cardShadow()
    }

    private var statusTitle: String {
        if isOpenNow == true { return "Открыто" }
        if isOpenNow == false { return "Закрыто" }
        return "Часы"
    }

    private var statusSubtitle: String? {
        if isOpenNow == true, let nextCloseTime = nextCloseTime {
            return "до \(nextCloseTime)"
        }
        if isOpenNow == false, let nextOpenTime = nextOpenTime {
            return "откроется \(nextOpenTime)"
        }
        return openingHours.first
    }

    private var ratingSubtitle: String? {
        guard let reviewsCount = reviewsCount else {
            return "Google"
        }
        return "\(reviewsCount) отзывов • Google"
    }
}

struct StatusItem: View {
    let icon: String
    let iconColor: Color
    let title: String
    let subtitle: String?

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundColor(iconColor)

            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            if let subtitle = subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
    }
}

struct DescriptionSection: View {
    let text: String
    let chips: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.medium) {
            SectionHeader(title: "Описание")
            Text(text)
                .font(.system(size: 15))
                .foregroundColor(.secondary)
                .lineSpacing(4)

            if !chips.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(chips, id: \.self) { chip in
                            Text(chip)
                                .font(.caption)
                                .fontWeight(.medium)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Color(UIColor.systemBackground))
                                .cornerRadius(14)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 14)
                                        .stroke(Color(UIColor.systemGray5), lineWidth: 1)
                                )
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct LocationSection: View {
    let address: String?
    let coordinate: CLLocationCoordinate2D
    let placeName: String
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.medium) {
            SectionHeader(title: "Местоположение")

            Map(coordinateRegion: .constant(MKCoordinateRegion(
                center: coordinate,
                span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
            )), annotationItems: [MapPin(coordinate: coordinate)]) { pin in
                MapMarker(coordinate: pin.coordinate, tint: .travelBuddyOrange)
            }
            .frame(height: 180)
            .cornerRadius(DesignSystem.CornerRadius.medium)

            if let address = address, !address.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "mappin.circle.fill")
                        .foregroundColor(.travelBuddyOrange)
                    Text(address)
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
            }

            Button {
                if let url = AppleMapsDeepLink.directionsURL(name: placeName, coordinate: coordinate) {
                    openURL(url)
                }
            } label: {
                HStack {
                    Image(systemName: "arrow.triangle.turn.up.right.circle.fill")
                    Text("Построить маршрут")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.travelBuddyOrange)
                .foregroundColor(.white)
                .cornerRadius(DesignSystem.CornerRadius.medium)
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
        .padding(.horizontal, DesignSystem.Spacing.medium)
    }
}

struct TravelInfoSection: View {
    let distanceKm: Double
    let etaMinutes: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Расстояние и ETA")

            HStack(spacing: 16) {
                HStack(spacing: 6) {
                    Image(systemName: "figure.walk")
                        .foregroundColor(.travelBuddyBlue)
                    Text(String(format: "%.1f км", distanceKm))
                        .font(.system(size: 14))
                }

                HStack(spacing: 6) {
                    Image(systemName: "clock")
                        .foregroundColor(.secondary)
                    Text("~\(etaMinutes) мин")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }

                Spacer()
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct ActionsSection: View {
    @Binding var isSaved: Bool
    @Binding var isInRoute: Bool
    @Binding var isMustVisit: Bool
    let noteText: String
    let shareURL: URL?
    let onNoteTap: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            SectionHeader(title: "Действия")

            if !isInRoute {
                HStack(spacing: 12) {
                    ActionButton(
                        icon: isSaved ? "bookmark.fill" : "bookmark",
                        title: "Сохранить",
                        isActive: isSaved
                    ) {
                        isSaved.toggle()
                    }

                    ActionButton(
                        icon: isInRoute ? "checkmark.circle.fill" : "plus.circle",
                        title: "В маршрут",
                        isActive: isInRoute
                    ) {
                        isInRoute.toggle()
                    }
                }

                HStack(spacing: 12) {
                    ActionButton(
                        icon: isMustVisit ? "star.fill" : "star",
                        title: "Must-visit",
                        isActive: isMustVisit
                    ) {
                        isMustVisit.toggle()
                    }

                    if let shareURL = shareURL {
                        ShareLink(item: shareURL) {
                            ActionButton(icon: "square.and.arrow.up", title: "Поделиться", isActive: false) {}
                        }
                    } else {
                        ActionButton(icon: "square.and.arrow.up", title: "Поделиться", isActive: false) {}
                    }

                    ActionButton(
                        icon: noteText.isEmpty ? "note.text.badge.plus" : "note.text",
                        title: "Заметка",
                        isActive: !noteText.isEmpty
                    ) {
                        onNoteTap()
                    }
                }
            } else {
                HStack(spacing: 12) {
                    if let shareURL = shareURL {
                        ShareLink(item: shareURL) {
                            ActionButton(icon: "square.and.arrow.up", title: "Поделиться", isActive: false) {}
                        }
                    } else {
                        ActionButton(icon: "square.and.arrow.up", title: "Поделиться", isActive: false) {}
                    }

                    ActionButton(
                        icon: noteText.isEmpty ? "note.text.badge.plus" : "note.text",
                        title: "Заметка",
                        isActive: !noteText.isEmpty
                    ) {
                        onNoteTap()
                    }
                }
            }
        }
        .padding(.bottom, DesignSystem.Spacing.large)
    }
}

struct ActionButton: View {
    let icon: String
    let title: String
    let isActive: Bool
    var isPrimary: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.title3)
                Text(title)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(
                isPrimary ?
                    AnyView(Color.travelBuddyOrange) :
                    AnyView(isActive ? Color.travelBuddyOrange.opacity(0.15) : Color.gray.opacity(0.08))
            )
            .foregroundColor(
                isPrimary ? .white :
                    (isActive ? Color.travelBuddyOrange : .primary)
            )
            .cornerRadius(DesignSystem.CornerRadius.medium)
        }
    }
}

struct RestaurantInfoSection: View {
    let website: URL?
    let phone: String?
    let reservable: Bool
    let googleMapsURL: URL?
    let priceLevel: PriceLevel?
    let cuisineLabel: String

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.medium) {
            SectionHeader(title: "Информация о ресторане")

            HStack(spacing: 8) {
                if let priceLevel = priceLevel {
                    InfoChip(icon: "dollarsign.circle.fill", text: priceLevel.displayText)
                }
                if !cuisineLabel.isEmpty {
                    InfoChip(icon: "fork.knife.circle.fill", text: cuisineLabel)
                }
            }

            VStack(spacing: 12) {
                if let website = website {
                    ContactButton(icon: "globe", title: "Сайт", url: website)
                }

                if let phone = phone {
                    ContactButton(icon: "phone.fill", title: phone, url: URL(string: "tel:\(phone)"))
                }

            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct InfoChip: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.caption)
            Text(text)
                .font(.caption)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.gray.opacity(0.12))
        .cornerRadius(DesignSystem.CornerRadius.capsule)
    }
}

struct ContactButton: View {
    let icon: String
    let title: String
    let url: URL?

    @Environment(\.openURL) private var openURL

    var body: some View {
        if let url = url {
            Link(destination: url) {
                HStack {
                    Image(systemName: icon)
                    Text(title)
                        .fontWeight(.medium)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption)
                }
                .padding()
                .background(Color.gray.opacity(0.08))
                .cornerRadius(DesignSystem.CornerRadius.small)
                .foregroundColor(.primary)
            }
        } else {
            HStack {
                Image(systemName: icon)
                Text(title)
                    .fontWeight(.medium)
                    .foregroundColor(.secondary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding()
            .background(Color.gray.opacity(0.08))
            .cornerRadius(DesignSystem.CornerRadius.small)
        }
    }
}

struct AmenitiesSection: View {
    let amenities: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.medium) {
            SectionHeader(title: "Удобства")

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                ForEach(amenities, id: \.self) { amenity in
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle")
                            .foregroundColor(.green)
                        Text(amenity)
                            .font(.subheadline)
                        Spacer()
                    }
                }
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct ReviewsSection: View {
    let reviews: [PlaceDetailsReview]

    var body: some View {
        VStack(alignment: .leading, spacing: DesignSystem.Spacing.medium) {
            SectionHeader(title: "Отзывы")

            VStack(spacing: 12) {
                ForEach(reviews) { review in
                    ReviewCard(review: review)
                }
            }
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct ReviewCard: View {
    let review: PlaceDetailsReview

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(review.authorName)
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                HStack(spacing: 4) {
                    Image(systemName: "star.fill")
                        .font(.caption)
                        .foregroundColor(.yellow)
                    Text(String(format: "%.1f", review.rating))
                        .font(.caption)
                        .fontWeight(.medium)
                }
            }

            Text(review.text)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .lineLimit(3)

            Text(review.relativeTime)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(12)
        .background(Color.gray.opacity(0.05))
        .cornerRadius(DesignSystem.CornerRadius.small)
    }
}

struct LoadingSection: View {
    var body: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text("Загружаем детали места…")
                .font(.system(size: 14))
                .foregroundColor(.secondary)
            Spacer()
        }
        .padding(16)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct ErrorSection: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                Text(message)
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
            }
            Button("Повторить", action: retry)
                .font(.system(size: 14, weight: .semibold))
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(Color(UIColor.systemBackground))
        .cornerRadius(DesignSystem.CornerRadius.medium)
    }
}

struct SectionHeader: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(.secondary)
            .textCase(.uppercase)
    }
}

struct NoteEditorSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var noteText: String

    var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                TextEditor(text: $noteText)
                    .padding(12)
                    .background(Color(UIColor.systemGray6))
                    .cornerRadius(12)
                    .frame(maxHeight: 220)
                    .padding(.horizontal, 16)

                Spacer()
            }
            .navigationTitle("Заметка")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Закрыть") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Сохранить") {
                        dismiss()
                    }
                }
            }
        }
    }
}

private struct MapPin: Identifiable {
    let id = UUID()
    let coordinate: CLLocationCoordinate2D
}
