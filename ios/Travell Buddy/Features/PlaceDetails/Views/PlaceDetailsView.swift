//
//  PlaceDetailsView.swift
//  Travell Buddy
//

import SwiftUI
import MapKit

struct PlaceDetailsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @StateObject private var viewModel: PlaceDetailsViewModel
    @StateObject private var locationManager = LocationManager()
    @State private var selectedPhotoIndex: Int = 0
    @State private var showingNoteEditor: Bool = false
    @State private var isShowingAllDescription: Bool = false

    private let ctaHeight: CGFloat = 72

    init(placeId: String, fallbackPlace: Place? = nil) {
        _viewModel = StateObject(wrappedValue: PlaceDetailsViewModel(placeId: placeId, fallbackPlace: fallbackPlace))
    }

    var body: some View {
        NavigationView {
            ZStack {
                backgroundLayer
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 18) {
                        heroSection
                        contentSection
                    }
                    .padding(.bottom, ctaHeight + 24)
                }
            }
            .safeAreaInset(edge: .bottom) {
                bottomBar
            }
            .navigationBarHidden(true)
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

    private var backgroundLayer: some View {
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

    private var heroSection: some View {
        let photos = viewModel.details?.photos ?? []
        let heroImageURL = photos.first?.url

        return ZStack(alignment: .top) {
            ZStack(alignment: .bottomLeading) {
                AsyncImage(url: heroImageURL) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        Color.black.opacity(0.2)
                    case .empty:
                        Color.black.opacity(0.15)
                            .overlay(ProgressView())
                    @unknown default:
                        Color.black.opacity(0.2)
                    }
                }
                .frame(height: 440)
                .frame(maxWidth: .infinity)
                .clipped()

                LinearGradient(
                    colors: [
                        Color.black.opacity(0.45),
                        Color.black.opacity(0.1),
                        Color(red: 0.14, green: 0.08, blue: 0.06)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )

                VStack(alignment: .leading, spacing: 12) {
                    heroChips
                    heroTitle
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
            .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))

            heroTopNav
        }
        .frame(height: 440)
        .padding(.horizontal, 12)
        .padding(.top, 8)
    }

    private var heroTopNav: some View {
        HStack(spacing: 12) {
            glassIconButton(systemName: "arrow.backward") {
                dismiss()
            }
            Spacer()
            if let shareURL = viewModel.details?.googleMapsURL {
                ShareLink(item: shareURL) {
                    glassIcon(systemName: "square.and.arrow.up")
                }
            } else {
                glassIconButton(systemName: "square.and.arrow.up") {}
            }
            glassIconButton(systemName: viewModel.isSaved ? "heart.fill" : "heart") {
                viewModel.isSaved.toggle()
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 20)
    }

    private var heroChips: some View {
        let chips = [viewModel.details?.categoryLabel]
            .compactMap { $0 }
            + viewModel.highlightChips()

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Array(chips.enumerated()), id: \.offset) { index, chip in
                    Text(chip)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(index == 0 ? .white : Color.white.opacity(0.9))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(
                            Capsule()
                                .fill(index == 0 ? Color.travelBuddyOrange.opacity(0.9) : Color.white.opacity(0.12))
                                .background(.ultraThinMaterial, in: Capsule())
                        )
                }
            }
            .padding(.vertical, 2)
        }
    }

    private var heroTitle: some View {
        let details = viewModel.details
        let ratingText = details?.rating.map { String(format: "%.1f", $0) }
        let reviewsCount = details?.reviewsCount
        let price = details?.priceLevel?.displayText
        let distanceText = viewModel.distanceKm.map { String(format: "%.1f км от вас", $0) }

        return VStack(alignment: .leading, spacing: 6) {
            Text(details?.name ?? viewModel.fallbackPlace?.name ?? "Место")
                .font(.system(size: 32, weight: .bold))
                .foregroundColor(.white)
                .lineLimit(2)

            HStack(spacing: 10) {
                if let ratingText {
                    HStack(spacing: 6) {
                        Image(systemName: "star.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Color.travelBuddyOrange)
                        Text(ratingText)
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color.white.opacity(0.12))
                    )
                }

                if let reviewsCount {
                    Text("(\(reviewsCount) отзывов)")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Color.white.opacity(0.7))
                }

                if let price {
                    Text(price)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                }

                if let distanceText {
                    Text(distanceText)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
            }
        }
    }

    private var contentSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            quickStats
            descriptionCard
            gallerySection
            amenitiesSection
            locationSection
            reviewsSection
            if viewModel.isLoading {
                loadingCard
            }
            if let error = viewModel.errorMessage {
                errorCard(message: error)
            }
        }
        .padding(.horizontal, 16)
    }

    private var quickStats: some View {
        let details = viewModel.details
        let stats: [QuickStat] = [
            QuickStat(
                title: details?.isOpenNow == true ? "Открыто" : "Закрыто",
                subtitle: details?.nextCloseTime ?? "до 23:00",
                icon: "clock",
                isPrimary: details?.isOpenNow == true
            ),
            QuickStat(
                title: "Маршрут",
                subtitle: viewModel.etaMinutes.map { "\($0) мин" } ?? "—",
                icon: "location.north.line",
                isPrimary: false
            ),
            QuickStat(
                title: "Телефон",
                subtitle: details?.phone == nil ? "Недоступно" : "Позвонить",
                icon: "phone",
                isPrimary: false
            )
        ]

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(stats) { stat in
                    VStack(spacing: 8) {
                        Circle()
                            .fill(Color.white.opacity(0.08))
                            .frame(width: 32, height: 32)
                            .overlay(
                                Image(systemName: stat.icon)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(Color.travelBuddyOrange)
                            )
                        VStack(spacing: 2) {
                            Text(stat.title.uppercased())
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(Color.white.opacity(0.6))
                            Text(stat.subtitle)
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.white)
                        }
                    }
                    .frame(width: 110, height: 92)
                    .background(glassCard)
                }
            }
        }
    }

    private var descriptionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("О месте")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(.white)
            Text(descriptionText)
                .font(.system(size: 15))
                .foregroundColor(Color.white.opacity(0.7))
                .lineLimit(isShowingAllDescription ? nil : 4)
            Button {
                isShowingAllDescription.toggle()
            } label: {
                HStack(spacing: 4) {
                    Text("Читать далее")
                        .font(.system(size: 13, weight: .bold))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundColor(Color.travelBuddyOrange)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(Color.travelBuddyOrange.opacity(0.15))
                )
            }
        }
        .padding(20)
        .background(glassCard)
    }

    private var gallerySection: some View {
        guard let photos = viewModel.details?.photos, !photos.isEmpty else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Фотографии")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)
                    Spacer()
                    Text("Все (\(photos.count))")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(Color.travelBuddyOrange)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(photos) { photo in
                            AsyncImage(url: photo.url) { phase in
                                switch phase {
                                case .success(let image):
                                    image
                                        .resizable()
                                        .scaledToFill()
                                case .failure:
                                    Color.white.opacity(0.1)
                                case .empty:
                                    Color.white.opacity(0.08)
                                @unknown default:
                                    Color.white.opacity(0.08)
                                }
                            }
                            .frame(width: 140, height: 190)
                            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 20, style: .continuous)
                                    .stroke(Color.white.opacity(0.1), lineWidth: 1)
                            )
                        }
                    }
                }
            }
        )
    }

    private var amenitiesSection: some View {
        guard let amenities = viewModel.details?.amenities, !amenities.isEmpty else {
            return AnyView(EmptyView())
        }

        let shownAmenities = Array(amenities.prefix(4))

        return AnyView(
            VStack(alignment: .leading, spacing: 16) {
                Text("Удобства")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.white)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 2), spacing: 16) {
                    ForEach(shownAmenities, id: \.self) { amenity in
                        HStack(spacing: 12) {
                            Circle()
                                .fill(Color.white.opacity(0.08))
                                .frame(width: 40, height: 40)
                                .overlay(
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 16, weight: .bold))
                                        .foregroundColor(Color.travelBuddyOrange)
                                )
                            Text(amenity)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Color.white.opacity(0.85))
                            Spacer()
                        }
                    }
                }
            }
            .padding(20)
            .background(glassCard)
        )
    }

    private var locationSection: some View {
        guard let details = viewModel.details else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(spacing: 12) {
                Map(coordinateRegion: .constant(MKCoordinateRegion(
                    center: details.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                )), annotationItems: [details]) { place in
                    MapAnnotation(coordinate: place.coordinate) {
                        VStack(spacing: 0) {
                            Circle()
                                .fill(Color.travelBuddyOrange)
                                .frame(width: 44, height: 44)
                                .overlay(
                                    Image(systemName: "fork.knife")
                                        .font(.system(size: 18, weight: .bold))
                                        .foregroundColor(.white)
                                )
                            Rectangle()
                                .fill(Color.travelBuddyOrange)
                                .frame(width: 10, height: 10)
                                .rotationEffect(.degrees(45))
                                .offset(y: -4)
                        }
                    }
                }
                .frame(height: 180)
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .stroke(Color.white.opacity(0.1), lineWidth: 1)
                )

                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(details.address ?? "Адрес не указан")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                        Text("Москва, Россия")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(Color.white.opacity(0.6))
                    }
                    Spacer()
                    Button {
                        if let url = details.googleMapsURL {
                            openURL(url)
                        }
                    } label: {
                        Circle()
                            .fill(Color.travelBuddyOrange.opacity(0.2))
                            .frame(width: 44, height: 44)
                            .overlay(
                                Image(systemName: "paperplane.fill")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(Color.travelBuddyOrange)
                            )
                    }
                }
                .padding(.horizontal, 6)
                .padding(.bottom, 4)
            }
            .padding(14)
            .background(glassCard)
        )
    }

    private var reviewsSection: some View {
        guard let details = viewModel.details, !details.reviews.isEmpty else {
            return AnyView(EmptyView())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Отзывы")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(.white)
                    Spacer()
                    Text("Смотреть все")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(Color.travelBuddyOrange)
                }

                if let rating = details.rating, let reviewsCount = details.reviewsCount {
                    HStack(spacing: 16) {
                        VStack(spacing: 6) {
                            Text(String(format: "%.1f", rating))
                                .font(.system(size: 40, weight: .bold))
                                .foregroundColor(.white)
                            HStack(spacing: 2) {
                                ForEach(0..<5) { index in
                                    Image(systemName: index < 4 ? "star.fill" : "star.leadinghalf.filled")
                                        .font(.system(size: 12))
                                        .foregroundColor(Color.travelBuddyOrange)
                                }
                            }
                            Text("\(reviewsCount) оценок")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(Color.white.opacity(0.6))
                        }

                        VStack(spacing: 8) {
                            ratingBar(label: "5", value: 0.85)
                            ratingBar(label: "4", value: 0.1)
                            ratingBar(label: "3", value: 0.03)
                            ratingBar(label: "2", value: 0.01, dimmed: true)
                            ratingBar(label: "1", value: 0.01, dimmed: true)
                        }
                    }
                }

                if let review = details.reviews.first {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 12) {
                            Circle()
                                .fill(Color.white.opacity(0.2))
                                .frame(width: 40, height: 40)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(review.authorName)
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundColor(.white)
                                Text(review.relativeTime)
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundColor(Color.white.opacity(0.6))
                            }
                            Spacer()
                            HStack(spacing: 4) {
                                Image(systemName: "star.fill")
                                    .font(.system(size: 12))
                                    .foregroundColor(Color.travelBuddyOrange)
                                Text(String(format: "%.1f", review.rating))
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Color.white.opacity(0.1))
                            )
                        }
                        Text(review.text)
                            .font(.system(size: 14))
                            .foregroundColor(Color.white.opacity(0.8))
                    }
                }
            }
            .padding(20)
            .background(glassCard)
        )
    }

    private var loadingCard: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text("Загружаем детали места…")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.7))
        }
        .padding(16)
        .background(glassCard)
    }

    private func errorCard(message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ошибка")
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.white)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.7))
            Button("Повторить") {
                viewModel.retry()
            }
            .font(.system(size: 13, weight: .bold))
            .foregroundColor(Color.travelBuddyOrange)
        }
        .padding(16)
        .background(glassCard)
    }

    private var bottomBar: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.14, green: 0.08, blue: 0.06).opacity(0.0),
                    Color(red: 0.14, green: 0.08, blue: 0.06)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            HStack(spacing: 12) {
                Button {
                    if let url = viewModel.details?.website ?? viewModel.details?.googleMapsURL {
                        openURL(url)
                    }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "calendar")
                            .font(.system(size: 16, weight: .semibold))
                        Text("Забронировать")
                            .font(.system(size: 16, weight: .bold))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: ctaHeight)
                    .background(
                        Capsule()
                            .fill(Color.travelBuddyOrange)
                    )
                }

                Button {
                    showingNoteEditor = true
                } label: {
                    Circle()
                        .fill(Color.white.opacity(0.12))
                        .frame(width: ctaHeight, height: ctaHeight)
                        .overlay(
                            Image(systemName: "message.fill")
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundColor(.white)
                        )
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 12)
        }
        .frame(height: ctaHeight + 28)
    }

    private var glassCard: some View {
        RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(Color(red: 0.14, green: 0.10, blue: 0.08).opacity(0.6))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }

    private func ratingBar(label: String, value: CGFloat, dimmed: Bool = false) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(dimmed ? Color.white.opacity(0.4) : .white)
                .frame(width: 10)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(Color.travelBuddyOrange.opacity(dimmed ? 0.4 : 1.0))
                        .frame(width: proxy.size.width * value)
                }
            }
            .frame(height: 6)
        }
        .frame(height: 8)
    }

    private func glassIcon(systemName: String) -> some View {
        Image(systemName: systemName)
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.white)
            .frame(width: 48, height: 48)
            .background(Color.black.opacity(0.25), in: Circle())
            .overlay(
                Circle()
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }

    private func glassIconButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            glassIcon(systemName: systemName)
        }
        .buttonStyle(.plain)
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

private struct QuickStat: Identifiable {
    let id = UUID()
    let title: String
    let subtitle: String
    let icon: String
    let isPrimary: Bool
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
