//
//  PlaceDetailsView.swift
//  Travell Buddy
//

import SwiftUI
import MapKit

struct PlaceDetailsView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: PlaceDetailsViewModel
    @StateObject private var locationManager = LocationManager()
    @State private var selectedPhotoIndex: Int = 0
    @State private var showingNoteEditor: Bool = false

    init(placeId: String, fallbackPlace: Place? = nil) {
        _viewModel = StateObject(wrappedValue: PlaceDetailsViewModel(placeId: placeId, fallbackPlace: fallbackPlace))
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 0) {
                    HeroPhotoSection(
                        photos: viewModel.details?.photos ?? [],
                        selectedIndex: $selectedPhotoIndex
                    )

                    VStack(spacing: DesignSystem.Spacing.large) {
                        PlaceIdentitySection(
                            name: viewModel.details?.name ?? viewModel.fallbackPlace?.name ?? "Place",
                            categoryLabel: viewModel.details?.categoryLabel ?? "",
                            categoryIcon: viewModel.details?.categoryIcon ?? "mappin.and.ellipse"
                        )
                        .padding(.horizontal, DesignSystem.Spacing.medium)

                        if let details = viewModel.details {
                            StatusRowSection(
                                isOpenNow: details.isOpenNow,
                                nextOpenTime: details.nextOpenTime,
                                nextCloseTime: details.nextCloseTime,
                                openingHours: details.openingHours,
                                rating: details.rating,
                                reviewsCount: details.reviewsCount,
                                durationText: viewModel.estimatedVisitDurationText(),
                                priceLevel: details.priceLevel
                            )
                            .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        DescriptionSection(
                            text: descriptionText,
                            chips: viewModel.highlightChips()
                        )
                        .padding(.horizontal, DesignSystem.Spacing.medium)

                        if let details = viewModel.details {
                            LocationSection(
                                address: details.address,
                                coordinate: details.coordinate,
                                placeName: details.name
                            )
                        }

                        if let distanceKm = viewModel.distanceKm, let etaMinutes = viewModel.etaMinutes {
                            TravelInfoSection(distanceKm: distanceKm, etaMinutes: etaMinutes)
                                .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        ActionsSection(
                            isSaved: $viewModel.isSaved,
                            isInRoute: $viewModel.isInRoute,
                            isMustVisit: $viewModel.isMustVisit,
                            noteText: viewModel.noteText,
                            shareURL: viewModel.details?.googleMapsURL,
                            onNoteTap: { showingNoteEditor = true }
                        )
                        .padding(.horizontal, DesignSystem.Spacing.medium)

                        if let details = viewModel.details, details.isRestaurant {
                            RestaurantInfoSection(
                                website: details.website,
                                phone: details.phone,
                                reservable: details.reservable,
                                googleMapsURL: details.googleMapsURL,
                                priceLevel: details.priceLevel,
                                cuisineLabel: details.categoryLabel
                            )
                            .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        if let details = viewModel.details, !details.amenities.isEmpty {
                            AmenitiesSection(amenities: details.amenities)
                                .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        if let details = viewModel.details, !details.reviews.isEmpty {
                            ReviewsSection(reviews: details.reviews)
                                .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        if viewModel.isLoading {
                            LoadingSection()
                                .padding(.horizontal, DesignSystem.Spacing.medium)
                        }

                        if let error = viewModel.errorMessage {
                            ErrorSection(message: error, retry: viewModel.retry)
                                .padding(.horizontal, DesignSystem.Spacing.medium)
                        }
                    }
                    .padding(.vertical, DesignSystem.Spacing.medium)
                }
            }
            .background(Color(UIColor.systemGroupedBackground))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title2)
                            .foregroundColor(.gray.opacity(0.6))
                    }
                }
            }
            .task {
                viewModel.loadDetails()
                locationManager.start()
            }
            .onReceive(locationManager.$lastLocation) { location in
                viewModel.updateDistance(from: location)
            }
            .sheet(isPresented: $showingNoteEditor) {
                NoteEditorSheet(noteText: $viewModel.noteText)
            }
        }
    }

    private var descriptionText: String {
        if let editorial = viewModel.details?.editorialSummary, !editorial.isEmpty {
            return editorial
        }
        let category = viewModel.details?.categoryLabel
        let types = viewModel.details?.types ?? []
        let address = viewModel.details?.address
        let rating = viewModel.details?.rating
        let reviewsCount = viewModel.details?.reviewsCount
        let priceLevel = viewModel.details?.priceLevel?.displayText

        let template = descriptionTemplate(types: types, category: category)
        var sentence1 = template
        if let address, !address.isEmpty {
            sentence1 += " Адрес: \(address)."
        }

        var sentence2Parts: [String] = []
        if let rating {
            let ratingText = String(format: "%.1f", rating)
            if let reviewsCount {
                sentence2Parts.append("Средний рейтинг \(ratingText) по \(reviewsCount) отзывам")
            } else {
                sentence2Parts.append("Средний рейтинг \(ratingText)")
            }
        }
        if let priceLevel, !priceLevel.isEmpty {
            sentence2Parts.append("уровень цен \(priceLevel)")
        }

        if !sentence2Parts.isEmpty {
            let sentence2 = sentence2Parts.joined(separator: ", ") + "."
            return "\(sentence1) \(sentence2)"
        }

        return sentence1
    }

    private func descriptionTemplate(types: [String], category: String?) -> String {
        let typeSet = Set(types)

        if typeSet.contains("cafe") || typeSet.contains("coffee_shop") {
            return "Уютное место, чтобы выпить кофе и перекусить. Подходит для короткой остановки или встречи."
        }
        if typeSet.contains("restaurant") || typeSet.contains("food") {
            return "Заведение с кухней и атмосферой для спокойного обеда или ужина. Подходит для приятного отдыха в городе."
        }
        if typeSet.contains("bar") || typeSet.contains("night_club") {
            return "Место для вечернего отдыха и общения. Хороший вариант для завершения насыщенного дня."
        }
        if typeSet.contains("museum") || typeSet.contains("art_gallery") {
            return "Музейное пространство для знакомства с культурой и экспозициями. Подходит для спокойного визита и впечатлений."
        }
        if typeSet.contains("park") || typeSet.contains("tourist_attraction") {
            return "Пространство для прогулки и отдыха. Хорошее место, чтобы сделать паузу и насладиться атмосферой."
        }
        if typeSet.contains("shopping_mall") || typeSet.contains("store") {
            return "Место для покупок и короткого перерыва. Удобно, если хотите совместить прогулку и шопинг."
        }

        if let category, !category.isEmpty {
            return "Место категории «\(category)» — хороший выбор для знакомства с районом и атмосферы города."
        }

        return "Информация о месте пока недоступна."
    }
}

struct MissingPlaceIdView: View {
    let placeName: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 36))
                .foregroundColor(.orange)
            Text(placeName)
                .font(.headline)
            Text("Не удалось загрузить детали места. В маршруте нет Google Place ID.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }
}
