//
//  TravelersPickerSheet.swift
//  Travell Buddy
//
//  Modal sheet for selecting number of travelers.
//

import SwiftUI

struct TravelersPickerSheet: View {
    @Binding var adultsCount: Int
    @Binding var childrenCount: Int
    @Binding var isPresented: Bool
    
    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [
                        TravelersPickerStyle.Colors.backgroundTop,
                        TravelersPickerStyle.Colors.backgroundBottom
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                RadialGradient(
                    colors: [
                        TravelersPickerStyle.Colors.smoke.opacity(0.35),
                        Color.clear
                    ],
                    center: .top,
                    startRadius: 20,
                    endRadius: 420
                )
                .ignoresSafeArea()

                Image("noise")
                    .resizable(resizingMode: .tile)
                    .opacity(0.03)
                    .blendMode(.softLight)
                    .ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 16) {
                        // Заголовок
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Количество путешественников")
                                .font(.system(size: 24, weight: .bold, design: .rounded))
                                .foregroundColor(TravelersPickerStyle.Colors.primaryText)

                            Text("Выберите количество взрослых и детей")
                                .font(.system(size: 16))
                                .foregroundColor(TravelersPickerStyle.Colors.secondaryText)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 20)

                        Divider()
                            .overlay(Color.white.opacity(0.08))

                        // Взрослые
                        TravelerCountRow(
                            title: "Взрослые",
                            subtitle: "От 18 лет",
                            icon: "person.fill",
                            iconColor: Color.travelBuddyOrange,
                            count: $adultsCount,
                            minValue: 1
                        )

                        Divider()
                            .overlay(Color.white.opacity(0.08))

                        // Дети
                        TravelerCountRow(
                            title: "Дети",
                            subtitle: "До 18 лет",
                            icon: "figure.child",
                            iconColor: Color.travelBuddyOrangeLight,
                            count: $childrenCount,
                            minValue: 0
                        )
                    }
                    .padding(.horizontal, TravelersPickerStyle.Layout.horizontalPadding)
                    .padding(.vertical, 16)
                    .padding(.bottom, totalSummaryHeight + 12)
                }
                .safeAreaInset(edge: .bottom) {
                    totalSummary
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Отмена") {
                        isPresented = false
                    }
                    .foregroundColor(TravelersPickerStyle.Colors.primaryText)
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Готово") {
                        isPresented = false
                    }
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(TravelersPickerStyle.Colors.accent)
                }
            }
            .toolbarBackground(TravelersPickerStyle.Colors.backgroundTop, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    private var totalSummaryHeight: CGFloat {
        88
    }

    private var totalSummary: some View {
        VStack(spacing: 12) {
            Divider()
                .overlay(Color.white.opacity(0.08))

            HStack {
                Text("Всего путешественников")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundColor(TravelersPickerStyle.Colors.primaryText)

                Spacer()

                Text("\(adultsCount + childrenCount)")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundColor(TravelersPickerStyle.Colors.accent)
            }
            .padding(.horizontal, TravelersPickerStyle.Layout.horizontalPadding)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: TravelersPickerStyle.Radius.card, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: TravelersPickerStyle.Radius.card, style: .continuous)
                            .fill(TravelersPickerStyle.Colors.cardTint)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: TravelersPickerStyle.Radius.card, style: .continuous)
                            .stroke(TravelersPickerStyle.Colors.cardStroke, lineWidth: 1)
                    )
            )
        }
        .padding(.horizontal, TravelersPickerStyle.Layout.horizontalPadding)
        .padding(.top, 8)
        .padding(.bottom, 12)
        .background(
            LinearGradient(
                colors: [
                    TravelersPickerStyle.Colors.backgroundBottom.opacity(0.0),
                    TravelersPickerStyle.Colors.backgroundBottom.opacity(0.9)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }
}
