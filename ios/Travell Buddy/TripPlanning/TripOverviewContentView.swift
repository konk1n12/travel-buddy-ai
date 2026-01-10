//
//  TripOverviewContentView.swift
//  Travell Buddy
//
//  Overview content for the trip plan tabs.
//

import SwiftUI
import CoreLocation
import MapKit

struct TripOverviewContentView: View {
    let trip: TripPlan
    @ObservedObject var viewModel: TripPlanViewModel
    @StateObject private var summaryViewModel: TripSummaryViewModel
    private let coordinate: CLLocationCoordinate2D?

    init(trip: TripPlan, viewModel: TripPlanViewModel) {
        self.trip = trip
        self.viewModel = viewModel
        self.coordinate = trip.cityCoordinate
        _summaryViewModel = StateObject(
            wrappedValue: TripSummaryViewModel(summary: trip.summary, coordinate: trip.cityCoordinate)
        )
    }

    private var summary: TripSummary { summaryViewModel.summary }
    private var primaryText: Color { .white.opacity(0.94) }
    private var secondaryText: Color { .white.opacity(0.62) }
    private var tertiaryText: Color { .white.opacity(0.45) }

    var body: some View {
        VStack(spacing: 20) {
            aiInsights
            tipChips
            aboutTrip
            statsGrid
            weatherCard
            keyLocations
            miniMapCard
            budgetCard
        }
        .task {
            await summaryViewModel.loadWeather()
        }
    }

    private var aiInsights: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Circle()
                    .fill(LinearGradient(colors: [Color.travelBuddyOrange, Color.orange], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 24, height: 24)
                    .overlay(
                        Image(systemName: "sparkles")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(.white)
                    )
                Text("AI-инсайты")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(primaryText)
            }

            VStack(spacing: 10) {
                ForEach(insights) { insight in
                    HStack(spacing: 12) {
                        Circle()
                            .fill(Color.travelBuddyOrange.opacity(0.2))
                            .frame(width: 36, height: 36)
                            .overlay(
                                Image(systemName: insight.icon)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundColor(Color.travelBuddyOrange)
                            )
                        VStack(alignment: .leading, spacing: 4) {
                            Text(insight.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(primaryText)
                            Text(insight.subtitle)
                                .font(.system(size: 12))
                                .foregroundColor(secondaryText)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(tertiaryText)
                    }
                    .padding(12)
                    .background(innerGlassCard)
                }
            }
        }
        .padding(16)
        .background(primaryGlassCard)
    }

    private var tipChips: some View {
        let tips = [
            ("Что взять", "backpack"),
            ("Как сэкономить", "banknote"),
            ("Разговорник", "globe"),
            ("Безопасность", "shield")
        ]

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(tips, id: \.0) { tip in
                    HStack(spacing: 8) {
                        Image(systemName: tip.1)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Color.travelBuddyOrange)
                        Text(tip.0)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(primaryText)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .frame(height: 34)
                    .background(chipGlass)
                }
            }
            .contentMargins(.horizontal, 16, for: .scrollContent)
        }
    }

    private var aboutTrip: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("О поездке")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(primaryText)
                Spacer()
                Button(action: {}) {
                    HStack(spacing: 6) {
                        Text("Читать далее")
                        Image(systemName: "arrow.right")
                    }
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Color.travelBuddyOrange)
            }
            Text(summary.tripDescription ?? "План составлен так, чтобы успеть основные точки и оставить время для отдыха.")
                .font(.system(size: 13))
                .foregroundColor(secondaryText)
                .lineLimit(4)
        }
        .padding(16)
        .background(primaryGlassCard)
    }

    private var statsGrid: some View {
        let avgSteps = formattedNumber(summary.averageStepsPerDay)
        let stats: [StatCard] = [
            StatCard(title: "Шагов в день", value: avgSteps, icon: "figure.walk"),
            StatCard(title: "Бюджет", value: summary.formattedTotalCostRange, icon: "creditcard"),
            StatCard(title: "Дней", value: "\(summary.daysCount)", icon: "calendar"),
            StatCard(title: "Активностей", value: "\(summary.totalActivities)", icon: "sparkles")
        ]

        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            ForEach(stats) { stat in
                VStack(alignment: .leading, spacing: 10) {
                    Circle()
                        .fill(Color.white.opacity(0.08))
                        .frame(width: 32, height: 32)
                        .overlay(
                            Image(systemName: stat.icon)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(secondaryText)
                        )
                    Text(stat.value)
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundColor(primaryText)
                    Text(stat.title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.55))
                }
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .background(secondaryGlassCard)
            }
        }
    }

    private var weatherCard: some View {
        let dayWeather = summaryViewModel.daySummaries.compactMap { $0.weather }.first

        return HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text("Погода сейчас")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(secondaryText)
                if let dayWeather {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(Int(dayWeather.temperatureHigh))°")
                            .font(.system(size: 30, weight: .semibold))
                            .foregroundColor(primaryText)
                        Text(dayWeather.condition.description)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(secondaryText)
                    }
                    Text("Ощущается как \(Int(dayWeather.temperatureLow))° • Ветер \(Int(dayWeather.windSpeed)) м/с")
                        .font(.system(size: 11))
                        .foregroundColor(tertiaryText)
                } else {
                    Text("Загрузка прогноза…")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(secondaryText)
                }
            }
            Spacer()
            Image(systemName: "sun.max.fill")
                .font(.system(size: 40))
                .foregroundColor(.yellow)
        }
        .padding(16)
        .background(primaryGlassCard)
    }

    private var keyLocations: some View {
        let items = summaryViewModel.daySummaries.prefix(3)

        return VStack(alignment: .leading, spacing: 12) {
            Text("Главные локации")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(primaryText)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(items) { day in
                        ZStack(alignment: .bottomLeading) {
                            LinearGradient(
                                colors: [Color.black.opacity(0.6), Color.black.opacity(0.2)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                            VStack(alignment: .leading, spacing: 4) {
                                Text(day.title ?? "День \(day.dayIndex)")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundColor(primaryText)
                                Text("День \(day.dayIndex)")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(secondaryText)
                            }
                            .padding(12)
                        }
                        .frame(width: 150, height: 200)
                        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .stroke(Color.white.opacity(0.1), lineWidth: 1)
                        )
                    }
                }
            }
        }
    }

    private var miniMapCard: some View {
        Group {
            if let coordinate {
                ZStack(alignment: .bottomTrailing) {
                    Map(coordinateRegion: .constant(MKCoordinateRegion(
                        center: coordinate,
                        span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                    )), annotationItems: [MapPinItem(coordinate: coordinate)]) { item in
                        MapAnnotation(coordinate: item.coordinate) {
                            Circle()
                                .fill(Color.travelBuddyOrange)
                                .frame(width: 26, height: 26)
                                .overlay(
                                    Image(systemName: "mappin")
                                        .font(.system(size: 12, weight: .bold))
                                        .foregroundColor(.white)
                                )
                        }
                    }
                    .frame(height: 180)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))

                    Button(action: {}) {
                        HStack(spacing: 6) {
                            Image(systemName: "map")
                                .font(.system(size: 12, weight: .semibold))
                            Text("Открыть карту")
                                .font(.system(size: 11, weight: .bold))
                        }
                        .foregroundColor(primaryText)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.black.opacity(0.7))
                        )
                    }
                    .padding(12)
                }
                .background(primaryGlassCard)
            }
        }
    }

    private var budgetCard: some View {
        let total = summary.totalEstimatedCostHigh == 0 ? 1 : summary.totalEstimatedCostHigh
        let spent = summary.totalEstimatedCostLow
        let progress = min(max(spent / total, 0), 1)

        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color.green.opacity(0.2))
                        .frame(width: 28, height: 28)
                        .overlay(
                            Image(systemName: "dollarsign")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.green)
                        )
                    Text("Бюджет")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(primaryText)
                }
                Spacer()
                Text("\(formattedCurrency(spent)) из \(formattedCurrency(total))")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(secondaryText)
            }

            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(LinearGradient(colors: [Color.travelBuddyOrange, Color.orange], startPoint: .leading, endPoint: .trailing))
                        .frame(width: proxy.size.width * progress)
                }
            }
            .frame(height: 8)

            HStack {
                Text("Потрачено")
                Spacer()
                Text("Осталось")
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(tertiaryText)
        }
        .padding(16)
        .background(primaryGlassCard)
    }

    private var primaryGlassCard: some View {
        let shape = RoundedRectangle(cornerRadius: 22, style: .continuous)
        return shape
            .fill(Color.black.opacity(0.20))
            .overlay(
                shape.fill(Color(red: 0.36, green: 0.22, blue: 0.14).opacity(0.06))
            )
            .background(.ultraThinMaterial, in: shape)
            .overlay(
                shape.stroke(
                    LinearGradient(
                        colors: [Color.white.opacity(0.14), Color.white.opacity(0.06)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
            )
            .shadow(color: Color.black.opacity(0.35), radius: 28, x: 0, y: 14)
    }

    private var secondaryGlassCard: some View {
        RoundedRectangle(cornerRadius: 22, style: .continuous)
            .fill(Color.white.opacity(0.06))
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
            )
    }

    private var innerGlassCard: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        return shape
            .fill(Color.black.opacity(0.32))
            .background(.ultraThinMaterial, in: shape)
            .overlay(
                shape.stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
            .overlay(
                LinearGradient(
                    colors: [Color.white.opacity(0.06), Color.clear],
                    startPoint: .top,
                    endPoint: .center
                )
                .clipShape(shape)
            )
    }

    private var chipGlass: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(Color.black.opacity(0.22))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.10), lineWidth: 1)
            )
    }

    private var insights: [Insight] {
        var result: [Insight] = []
        if let first = summaryViewModel.daySummaries.first?.firstActivityTime {
            result.append(Insight(icon: "sun.max", title: "Лучший старт дня — \(first)", subtitle: "Начните день без очередей"))
        }
        result.append(Insight(icon: "figure.walk", title: "Темп поездки: \(summary.overallIntensity.displayName)", subtitle: summary.overallIntensity.description))
        result.append(Insight(icon: "fork.knife", title: "Всего мест с едой: \(summary.totalMeals)", subtitle: "Запланировано на поездку"))
        return Array(result.prefix(3))
    }

    private func formattedNumber(_ number: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: number)) ?? "\(number)"
    }

    private func formattedCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = summary.currency
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value))"
    }
}

private struct Insight: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    let subtitle: String
}

private struct StatCard: Identifiable {
    let id = UUID()
    let title: String
    let value: String
    let icon: String
}

private struct MapPinItem: Identifiable {
    let id = UUID()
    let coordinate: CLLocationCoordinate2D
}

private extension WeatherCondition {
    var description: String {
        switch self {
        case .sunny: return "Ясно"
        case .partlyCloudy: return "Переменная облачность"
        case .cloudy: return "Облачно"
        case .rain: return "Дождь"
        case .heavyRain: return "Ливень"
        case .thunderstorm: return "Гроза"
        case .snow: return "Снег"
        case .fog: return "Туман"
        }
    }
}
