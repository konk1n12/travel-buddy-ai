//
//  TripInteractiveMapView.swift
//  Travell Buddy
//
//  Interactive map with zoom, locate, and fit controls for trip day POIs.
//

import SwiftUI
import MapKit
import CoreLocation

struct TripInteractiveMapView: View {
    let activities: [TripActivity]
    let fallbackCoordinate: CLLocationCoordinate2D?
    @Binding var isInteracting: Bool

    @State private var region: MKCoordinateRegion
    @State private var selectedPOI: MapPOI?
    @StateObject private var locationManager = MapLocationManager()

    init(
        activities: [TripActivity],
        fallbackCoordinate: CLLocationCoordinate2D?,
        isInteracting: Binding<Bool>
    ) {
        self.activities = activities
        self.fallbackCoordinate = fallbackCoordinate
        self._isInteracting = isInteracting

        let initialCenter = fallbackCoordinate ?? CLLocationCoordinate2D(latitude: 0, longitude: 0)
        _region = State(
            initialValue: MKCoordinateRegion(
                center: initialCenter,
                span: MKCoordinateSpan(latitudeDelta: 0.08, longitudeDelta: 0.08)
            )
        )
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Map(coordinateRegion: $region, interactionModes: [.pan, .zoom], annotationItems: mapPoints) { point in
                MapAnnotation(coordinate: point.coordinate) {
                    POIMarkerView(point: point, isSelected: point.id == selectedPOI?.id)
                        .onTapGesture {
                            selectedPOI = point
                        }
                }
            }
            .onAppear {
                if !mapPoints.isEmpty {
                    fitAllPoints(animated: false)
                }
            }
            .simultaneousGesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in isInteracting = true }
                    .onEnded { _ in isInteracting = false }
            )
            .simultaneousGesture(
                MagnificationGesture()
                    .onChanged { _ in isInteracting = true }
                    .onEnded { _ in isInteracting = false }
            )

            mapControls
                .padding(12)
        }
        .onChange(of: activities.map { $0.id }) { _ in
            selectedPOI = nil
            fitAllPoints(animated: true)
        }
    }

    private var mapPoints: [MapPOI] {
        activities.enumerated().compactMap { index, activity in
            guard let coordinate = activity.coordinate else { return nil }
            return MapPOI(
                id: activity.id,
                index: index + 1,
                title: activity.title,
                coordinate: coordinate
            )
        }
    }

    private var mapControls: some View {
        VStack(spacing: 10) {
            mapControlButton(systemName: "plus") {
                zoomIn()
            }
            mapControlButton(systemName: "minus") {
                zoomOut()
            }
            mapControlButton(systemName: "location") {
                centerOnUser()
            }
            mapControlButton(systemName: "arrow.up.left.and.arrow.down.right") {
                fitAllPoints(animated: true)
            }
        }
    }

    private func mapControlButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 44, height: 44)
                .background(
                    Circle()
                        .fill(Color.black.opacity(0.35))
                        .background(.ultraThinMaterial, in: Circle())
                )
                .overlay(
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }

    private func zoomIn() {
        region.span.latitudeDelta = max(region.span.latitudeDelta * 0.7, 0.002)
        region.span.longitudeDelta = max(region.span.longitudeDelta * 0.7, 0.002)
    }

    private func zoomOut() {
        region.span.latitudeDelta = min(region.span.latitudeDelta * 1.3, 60)
        region.span.longitudeDelta = min(region.span.longitudeDelta * 1.3, 60)
    }

    private func fitAllPoints(animated: Bool) {
        let coordinates = mapPoints.map { $0.coordinate }
        guard !coordinates.isEmpty else { return }

        var rect = MKMapRect.null
        coordinates.forEach { coordinate in
            let point = MKMapPoint(coordinate)
            rect = rect.union(MKMapRect(origin: point, size: MKMapSize(width: 0, height: 0)))
        }

        if rect.isNull || rect.isEmpty {
            return
        }

        let paddingFactor: CGFloat = 0.25
        let paddedRect = rect.insetBy(dx: -rect.size.width * paddingFactor, dy: -rect.size.height * paddingFactor)
        let fittedRegion = MKCoordinateRegion(paddedRect)

        if animated {
            withAnimation(.easeInOut(duration: 0.25)) {
                region = fittedRegion
            }
        } else {
            region = fittedRegion
        }
    }

    private func centerOnUser() {
        if locationManager.authorizationStatus == .notDetermined {
            locationManager.requestAuthorization()
        }

        if locationManager.isAuthorized, locationManager.lastLocation == nil {
            locationManager.requestLocation()
        }

        guard let location = locationManager.lastLocation else { return }
        let center = location.coordinate
        let newRegion = MKCoordinateRegion(
            center: center,
            span: MKCoordinateSpan(latitudeDelta: 0.02, longitudeDelta: 0.02)
        )
        withAnimation(.easeInOut(duration: 0.25)) {
            region = newRegion
        }
    }
}

private struct MapPOI: Identifiable {
    let id: UUID
    let index: Int
    let title: String
    let coordinate: CLLocationCoordinate2D
}

private struct POIMarkerView: View {
    let point: MapPOI
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 6) {
            if isSelected {
                Text(point.title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(Color.black.opacity(0.6))
                            .overlay(
                                Capsule()
                                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
                            )
                    )
            }
            ZStack {
                Circle()
                    .fill(isSelected ? Color.travelBuddyOrange : Color.black.opacity(0.55))
                    .frame(width: isSelected ? 34 : 30, height: isSelected ? 34 : 30)
                    .overlay(
                        Circle()
                            .stroke(Color.white.opacity(0.2), lineWidth: 1)
                    )
                Text("\(point.index)")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.white)
            }
            .shadow(color: Color.black.opacity(0.35), radius: 6, x: 0, y: 4)
        }
    }
}

final class MapLocationManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var lastLocation: CLLocation?

    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    func requestAuthorization() {
        manager.requestWhenInUseAuthorization()
        manager.requestLocation()
    }

    func requestLocation() {
        manager.requestLocation()
    }

    var isAuthorized: Bool {
        authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways
    }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        authorizationStatus = status
        if status == .authorizedWhenInUse || status == .authorizedAlways {
            manager.requestLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        lastLocation = locations.last
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("📍 Location error: \(error.localizedDescription)")
    }
}
