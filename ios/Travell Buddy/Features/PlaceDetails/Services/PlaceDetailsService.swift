//
//  PlaceDetailsService.swift
//  Travell Buddy
//
//  Service for fetching place details with in-memory caching.
//

import Foundation

// MARK: - Protocol

protocol PlaceDetailsServiceProtocol {
    func fetchDetails(for placeId: String) async throws -> GooglePlaceDetailsDTO
    func clearCache()
}

// MARK: - Implementation

final class PlaceDetailsService: PlaceDetailsServiceProtocol {

    // MARK: - Singleton

    static let shared = PlaceDetailsService()

    // MARK: - Cache

    private struct CacheEntry {
        let details: GooglePlaceDetailsDTO
        let timestamp: Date

        var isExpired: Bool {
            Date().timeIntervalSince(timestamp) > PlaceDetailsService.cacheTTL
        }
    }

    private var cache: [String: CacheEntry] = [:]
    private let cacheLock = NSLock()
    private static let cacheTTL: TimeInterval = 30 * 60 // 30 minutes

    // MARK: - Dependencies

    private let session: URLSession
    private let baseURL: URL

    // MARK: - Init

    init(
        session: URLSession = .shared,
        baseURL: URL = AppConfig.baseURL
    ) {
        self.session = session
        self.baseURL = baseURL
    }

    // MARK: - Public Methods

    func fetchDetails(for placeId: String) async throws -> GooglePlaceDetailsDTO {
        // Check cache first
        if let cached = getCached(for: placeId) {
            return cached
        }

        // Fetch from API
        let details = try await fetchFromAPI(placeId: placeId)

        // Cache the result
        cacheDetails(details, for: placeId)

        return details
    }

    func clearCache() {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        cache.removeAll()
    }

    // MARK: - Private Methods

    private func getCached(for placeId: String) -> GooglePlaceDetailsDTO? {
        cacheLock.lock()
        defer { cacheLock.unlock() }

        guard let entry = cache[placeId], !entry.isExpired else {
            cache.removeValue(forKey: placeId)
            return nil
        }

        return entry.details
    }

    private func cacheDetails(_ details: GooglePlaceDetailsDTO, for placeId: String) {
        cacheLock.lock()
        defer { cacheLock.unlock() }

        cache[placeId] = CacheEntry(details: details, timestamp: Date())

        // Clean up expired entries periodically
        if cache.count > 50 {
            cleanupExpiredEntries()
        }
    }

    private func cleanupExpiredEntries() {
        cache = cache.filter { !$0.value.isExpired }
    }

    private func fetchFromAPI(placeId: String) async throws -> GooglePlaceDetailsDTO {
        let url = baseURL.appendingPathComponent("places/\(placeId)/details")

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 15

        do {
            let (data, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw PlaceDetailsError.invalidResponse
            }

            switch httpResponse.statusCode {
            case 200:
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                return try decoder.decode(GooglePlaceDetailsDTO.self, from: data)

            case 404:
                throw PlaceDetailsError.notFound

            case 401:
                throw PlaceDetailsError.unauthorized

            default:
                throw PlaceDetailsError.serverError(statusCode: httpResponse.statusCode)
            }
        } catch let error as PlaceDetailsError {
            throw error
        } catch is DecodingError {
            throw PlaceDetailsError.decodingError
        } catch {
            throw PlaceDetailsError.networkError(error)
        }
    }
}

// MARK: - Errors

enum PlaceDetailsError: LocalizedError {
    case notFound
    case unauthorized
    case serverError(statusCode: Int)
    case networkError(Error)
    case decodingError
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .notFound:
            return "Место не найдено"
        case .unauthorized:
            return "Ошибка авторизации"
        case .serverError(let code):
            return "Ошибка сервера (\(code))"
        case .networkError:
            return "Ошибка сети. Проверьте подключение."
        case .decodingError:
            return "Ошибка обработки данных"
        case .invalidResponse:
            return "Некорректный ответ сервера"
        }
    }
}

// DTO is defined in PlacesDTO+Mapping.swift
