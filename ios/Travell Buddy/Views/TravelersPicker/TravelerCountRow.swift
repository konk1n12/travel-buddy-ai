//
//  TravelerCountRow.swift
//  Travell Buddy
//
//  Counter row for travelers picker.
//

import SwiftUI

struct TravelerCountRow: View {
    let title: String
    let subtitle: String
    let icon: String
    let iconColor: Color
    @Binding var count: Int
    let minValue: Int
    
    var body: some View {
        HStack(spacing: 16) {
            HStack(spacing: 12) {
                // Иконка
                ZStack {
                    Circle()
                        .fill(TravelersPickerStyle.Colors.badgeFillBase)
                        .frame(width: TravelersPickerStyle.Layout.iconSize, height: TravelersPickerStyle.Layout.iconSize)
                        .overlay(
                            Circle()
                                .stroke(TravelersPickerStyle.Colors.badgeStroke, lineWidth: 1)
                        )

                    Image(systemName: icon)
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundColor(iconColor)
                }

                // Текст
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 17, weight: .semibold, design: .rounded))
                        .foregroundColor(TravelersPickerStyle.Colors.primaryText)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)

                    Text(subtitle)
                        .font(.system(size: 14))
                        .foregroundColor(TravelersPickerStyle.Colors.secondaryText)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Кнопки +/-
            HStack(spacing: 12) {
                Button(action: {
                    if count > minValue {
                        withAnimation {
                            count -= 1
                        }
                    }
                }) {
                    ZStack {
                        Circle()
                            .fill(count > minValue ? TravelersPickerStyle.Colors.controlFill : TravelersPickerStyle.Colors.controlDisabled)
                            .frame(width: TravelersPickerStyle.Layout.controlSize, height: TravelersPickerStyle.Layout.controlSize)
                            .overlay(
                                Circle()
                                    .stroke(TravelersPickerStyle.Colors.controlStroke, lineWidth: 1)
                            )

                        Image(systemName: "minus")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(count > minValue ? TravelersPickerStyle.Colors.primaryText : TravelersPickerStyle.Colors.secondaryText.opacity(0.45))
                    }
                }
                .buttonStyle(.plain)
                .disabled(count <= minValue)

                Text("\(count)")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundColor(TravelersPickerStyle.Colors.primaryText)
                    .frame(minWidth: 32, alignment: .center)

                Button(action: {
                    withAnimation {
                        count += 1
                    }
                }) {
                    ZStack {
                        Circle()
                            .fill(LinearGradient.travelBuddyPrimary)
                            .frame(width: TravelersPickerStyle.Layout.controlSize, height: TravelersPickerStyle.Layout.controlSize)
                            .shadow(color: Color.black.opacity(0.25), radius: 8, x: 0, y: 6)

                        Image(systemName: "plus")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }
                .buttonStyle(.plain)
            }
            .frame(width: 152, alignment: .center)
        }
        .padding(TravelersPickerStyle.Layout.cardPadding)
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
        .shadow(color: TravelersPickerStyle.Colors.cardShadow, radius: 12, x: 0, y: 8)
    }
}
