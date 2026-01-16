//
//  RemoteImageView.swift
//  Travell Buddy
//
//  Lightweight remote image loader with in-memory cache.
//

import SwiftUI

private final class RemoteImageCache {
    static let shared = RemoteImageCache()
    private let cache = NSCache<NSURL, UIImage>()

    func image(for url: NSURL) -> UIImage? {
        cache.object(forKey: url)
    }

    func store(_ image: UIImage, for url: NSURL) {
        cache.setObject(image, forKey: url)
    }
}

private final class RemoteImageLoader: ObservableObject {
    @Published var image: UIImage?
    @Published var isLoading: Bool = false
    private var task: URLSessionDataTask?
    private var currentURL: URL?

    func load(from url: URL?) {
        // Skip if already loading the same URL
        guard url != currentURL else { return }

        task?.cancel()
        image = nil
        currentURL = url
        isLoading = false

        guard let url else { return }
        let nsURL = url as NSURL

        if let cached = RemoteImageCache.shared.image(for: nsURL) {
            image = cached
            return
        }

        isLoading = true

        var request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 30)
        request.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")

        task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.isLoading = false
            }

            if let error {
                print("[RemoteImageView] Error loading \(url): \(error.localizedDescription)")
                return
            }

            guard let httpResponse = response as? HTTPURLResponse else {
                print("[RemoteImageView] No HTTP response for \(url)")
                return
            }

            guard 200..<300 ~= httpResponse.statusCode else {
                print("[RemoteImageView] HTTP \(httpResponse.statusCode) for \(url)")
                return
            }

            guard let data, !data.isEmpty else {
                print("[RemoteImageView] Empty data for \(url)")
                return
            }

            guard let uiImage = UIImage(data: data) else {
                print("[RemoteImageView] Failed to decode image for \(url)")
                return
            }

            RemoteImageCache.shared.store(uiImage, for: nsURL)
            DispatchQueue.main.async {
                guard let self, self.currentURL == url else { return }
                self.image = uiImage
            }
        }
        task?.resume()
    }
}

struct RemoteImageView: View {
    let url: URL?

    @StateObject private var loader = RemoteImageLoader()

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                if let image = loader.image {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .clipped()
                } else {
                    Color.black.opacity(0.2)

                    if loader.isLoading {
                        ProgressView()
                            .tint(.white.opacity(0.5))
                    }
                }
            }
        }
        .onAppear {
            loader.load(from: url)
        }
        .onChange(of: url) { _, newValue in
            loader.load(from: newValue)
        }
    }
}
