//
//  RouteMapView.swift
//  Travell Buddy
//
//  Map view displaying POI annotations and route polylines for a trip day.
//  Uses MKMapView via UIViewRepresentable to support overlay rendering.
//
//  Discovery note: Existing LiveGuideView uses SwiftUI Map for user location tracking.
//  This is a different use case requiring polyline overlays, so we use MKMapView directly.
//

import SwiftUI
import MapKit

/// A map view that displays POI pins and route polylines for trip activities.
struct RouteMapView: UIViewRepresentable {
    let activities: [TripActivity]

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = false
        mapView.mapType = .standard
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Clear existing annotations and overlays
        mapView.removeAnnotations(mapView.annotations)
        mapView.removeOverlays(mapView.overlays)

        // Add POI annotations
        var coordinates: [CLLocationCoordinate2D] = []
        for (index, activity) in activities.enumerated() {
            guard let coordinate = activity.coordinate else { continue }

            let annotation = POIAnnotation(
                coordinate: coordinate,
                title: activity.title,
                subtitle: activity.time,
                index: index
            )
            mapView.addAnnotation(annotation)
            coordinates.append(coordinate)

            // Add polyline from previous activity if available
            if let polylineString = activity.travelPolyline,
               !polylineString.isEmpty {
                let polylineCoords = PolylineDecoder.decode(polylineString)
                if polylineCoords.count >= 2 {
                    let polyline = MKPolyline(coordinates: polylineCoords, count: polylineCoords.count)
                    mapView.addOverlay(polyline)
                }
            }
        }

        // Fit map to show all annotations and overlays
        fitMapToContent(mapView, coordinates: coordinates)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    /// Adjusts the map region to fit all coordinates with padding.
    private func fitMapToContent(_ mapView: MKMapView, coordinates: [CLLocationCoordinate2D]) {
        guard !coordinates.isEmpty else { return }

        if coordinates.count == 1 {
            // Single point - center with reasonable zoom
            let region = MKCoordinateRegion(
                center: coordinates[0],
                span: MKCoordinateSpan(latitudeDelta: 0.02, longitudeDelta: 0.02)
            )
            mapView.setRegion(region, animated: false)
            return
        }

        // Calculate bounding box for all coordinates
        var minLat = coordinates[0].latitude
        var maxLat = coordinates[0].latitude
        var minLon = coordinates[0].longitude
        var maxLon = coordinates[0].longitude

        for coord in coordinates {
            minLat = min(minLat, coord.latitude)
            maxLat = max(maxLat, coord.latitude)
            minLon = min(minLon, coord.longitude)
            maxLon = max(maxLon, coord.longitude)
        }

        // Also include polyline coordinates
        for overlay in mapView.overlays {
            if let polyline = overlay as? MKPolyline {
                let rect = polyline.boundingMapRect
                let topLeft = MKMapPoint(x: rect.minX, y: rect.minY)
                let bottomRight = MKMapPoint(x: rect.maxX, y: rect.maxY)
                let topLeftCoord = topLeft.coordinate
                let bottomRightCoord = bottomRight.coordinate

                minLat = min(minLat, topLeftCoord.latitude, bottomRightCoord.latitude)
                maxLat = max(maxLat, topLeftCoord.latitude, bottomRightCoord.latitude)
                minLon = min(minLon, topLeftCoord.longitude, bottomRightCoord.longitude)
                maxLon = max(maxLon, topLeftCoord.longitude, bottomRightCoord.longitude)
            }
        }

        // Add padding
        let latPadding = (maxLat - minLat) * 0.2
        let lonPadding = (maxLon - minLon) * 0.2

        let region = MKCoordinateRegion(
            center: CLLocationCoordinate2D(
                latitude: (minLat + maxLat) / 2,
                longitude: (minLon + maxLon) / 2
            ),
            span: MKCoordinateSpan(
                latitudeDelta: max((maxLat - minLat) + latPadding, 0.01),
                longitudeDelta: max((maxLon - minLon) + lonPadding, 0.01)
            )
        )
        mapView.setRegion(region, animated: false)
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, MKMapViewDelegate {

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let polyline = overlay as? MKPolyline {
                let renderer = MKPolylineRenderer(polyline: polyline)
                renderer.strokeColor = UIColor(Color.travelBuddyOrange)
                renderer.lineWidth = 4
                renderer.lineCap = .round
                renderer.lineJoin = .round
                return renderer
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            // Don't customize user location
            if annotation is MKUserLocation { return nil }

            guard let poiAnnotation = annotation as? POIAnnotation else { return nil }

            let identifier = "POIAnnotation"
            var annotationView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier) as? MKMarkerAnnotationView

            if annotationView == nil {
                annotationView = MKMarkerAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                annotationView?.canShowCallout = true
            } else {
                annotationView?.annotation = annotation
            }

            // Customize marker appearance
            annotationView?.markerTintColor = UIColor(Color.travelBuddyOrange)
            annotationView?.glyphText = "\(poiAnnotation.index + 1)"

            return annotationView
        }
    }
}

// MARK: - POI Annotation

/// Custom annotation for POI markers.
class POIAnnotation: NSObject, MKAnnotation {
    let coordinate: CLLocationCoordinate2D
    let title: String?
    let subtitle: String?
    let index: Int

    init(coordinate: CLLocationCoordinate2D, title: String?, subtitle: String?, index: Int) {
        self.coordinate = coordinate
        self.title = title
        self.subtitle = subtitle
        self.index = index
    }
}

// MARK: - Empty State View

/// Placeholder view shown when no map data is available.
struct NoMapDataView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "map")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text("Нет данных для карты")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemGroupedBackground))
    }
}
