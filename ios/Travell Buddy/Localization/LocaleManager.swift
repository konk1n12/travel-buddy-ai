//
//  LocaleManager.swift
//  Travell Buddy
//
//  Manages app localization and language preferences.
//

import SwiftUI
import Combine

/// Singleton manager for handling app language and localization
final class LocaleManager: ObservableObject {
    static let shared = LocaleManager()

    // MARK: - Supported Languages

    enum SupportedLanguage: String, CaseIterable, Identifiable {
        case english = "en"
        case russian = "ru"
        case chinese = "zh-Hans"
        case french = "fr"
        case spanish = "es"
        case arabic = "ar"
        case german = "de"

        var id: String { rawValue }

        /// Display name in the language itself (native name)
        var nativeName: String {
            switch self {
            case .english: return "English"
            case .russian: return "Русский"
            case .chinese: return "简体中文"
            case .french: return "Français"
            case .spanish: return "Español"
            case .arabic: return "العربية"
            case .german: return "Deutsch"
            }
        }

        /// Display name in current app language
        var displayName: String {
            let locale = Locale(identifier: LocaleManager.shared.currentLanguage.rawValue)
            return locale.localizedString(forLanguageCode: rawValue) ?? nativeName
        }

        /// Whether this language uses RTL layout
        var isRTL: Bool {
            return self == .arabic
        }

        /// Locale for date/number formatting
        var locale: Locale {
            Locale(identifier: rawValue)
        }

        /// BCP-47 language code for API requests
        var apiCode: String {
            switch self {
            case .chinese: return "zh"  // Simplified for API
            default: return rawValue
            }
        }

        /// Full language name in English (for LLM prompts)
        var englishName: String {
            switch self {
            case .english: return "English"
            case .russian: return "Russian"
            case .chinese: return "Simplified Chinese"
            case .french: return "French"
            case .spanish: return "Spanish"
            case .arabic: return "Arabic"
            case .german: return "German"
            }
        }

        /// Parse language code from various formats (en-US, zh-Hans-CN, etc.)
        static func from(code: String) -> SupportedLanguage {
            let normalized = code.lowercased()

            // Check exact match first
            if let exact = SupportedLanguage(rawValue: normalized) {
                return exact
            }

            // Handle variants
            if normalized.hasPrefix("zh") {
                return .chinese
            }

            // Extract base language code
            let baseCode = normalized.components(separatedBy: "-").first ?? normalized
            return SupportedLanguage(rawValue: baseCode) ?? .english
        }
    }

    // MARK: - Properties

    private let userDefaultsKey = "app_preferred_language"

    /// Current active language
    @Published private(set) var currentLanguage: SupportedLanguage

    /// Whether user has manually set a language preference
    @Published private(set) var hasManualOverride: Bool

    /// Current layout direction based on language
    var layoutDirection: LayoutDirection {
        currentLanguage.isRTL ? .rightToLeft : .leftToRight
    }

    /// Current locale for formatting
    var currentLocale: Locale {
        currentLanguage.locale
    }

    /// Language code for API requests (X-Language header)
    var apiLanguageCode: String {
        currentLanguage.apiCode
    }

    // MARK: - Initialization

    private init() {
        // Check for manual override
        if let storedCode = UserDefaults.standard.string(forKey: userDefaultsKey),
           let stored = SupportedLanguage(rawValue: storedCode) {
            self.currentLanguage = stored
            self.hasManualOverride = true
        } else {
            // Use system language
            self.currentLanguage = Self.detectSystemLanguage()
            self.hasManualOverride = false
        }
    }

    // MARK: - Public Methods

    /// Set language manually (persists to UserDefaults)
    func setLanguage(_ language: SupportedLanguage) {
        guard language != currentLanguage else { return }

        UserDefaults.standard.set(language.rawValue, forKey: userDefaultsKey)
        hasManualOverride = true
        currentLanguage = language

        // Post notification for components that need to refresh
        NotificationCenter.default.post(
            name: .appLanguageDidChange,
            object: nil,
            userInfo: ["language": language]
        )
    }

    /// Clear manual override and revert to system language
    func useSystemLanguage() {
        UserDefaults.standard.removeObject(forKey: userDefaultsKey)
        hasManualOverride = false
        currentLanguage = Self.detectSystemLanguage()

        NotificationCenter.default.post(
            name: .appLanguageDidChange,
            object: nil,
            userInfo: ["language": currentLanguage]
        )
    }

    /// Refresh language from system (call on app foreground if needed)
    func refreshSystemLanguage() {
        guard !hasManualOverride else { return }

        let systemLang = Self.detectSystemLanguage()
        if systemLang != currentLanguage {
            currentLanguage = systemLang
            NotificationCenter.default.post(
                name: .appLanguageDidChange,
                object: nil,
                userInfo: ["language": currentLanguage]
            )
        }
    }

    // MARK: - Private Methods

    private static func detectSystemLanguage() -> SupportedLanguage {
        // Get preferred languages from system
        let preferredLanguages = Locale.preferredLanguages

        for langCode in preferredLanguages {
            let language = SupportedLanguage.from(code: langCode)
            // Return first supported language found
            if SupportedLanguage.allCases.contains(language) {
                return language
            }
        }

        return .english // Default fallback
    }
}

// MARK: - Notification Extension

extension Notification.Name {
    static let appLanguageDidChange = Notification.Name("appLanguageDidChange")
}

// MARK: - String Extension for Localization

extension String {
    /// Returns localized string using String Catalogs
    var localized: String {
        String(localized: LocalizationValue(self))
    }

    /// Returns localized string with interpolated arguments
    func localized(_ arguments: CVarArg...) -> String {
        String(format: self.localized, arguments: arguments)
    }
}

// MARK: - DateFormatter Extension

extension DateFormatter {
    /// Returns formatter configured for current app locale
    static func appLocalized(
        dateStyle: DateFormatter.Style = .medium,
        timeStyle: DateFormatter.Style = .none
    ) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = LocaleManager.shared.currentLocale
        formatter.dateStyle = dateStyle
        formatter.timeStyle = timeStyle
        return formatter
    }

    /// Formatter for display dates (respects app language)
    static var localizedDate: DateFormatter {
        appLocalized(dateStyle: .long)
    }

    /// Formatter for short dates
    static var localizedShortDate: DateFormatter {
        appLocalized(dateStyle: .short)
    }

    /// Formatter for medium dates
    static var localizedMediumDate: DateFormatter {
        appLocalized(dateStyle: .medium)
    }

    /// Formatter for time only
    static var localizedTime: DateFormatter {
        appLocalized(dateStyle: .none, timeStyle: .short)
    }
}

// MARK: - View Modifier for RTL Support

struct LocalizedLayoutModifier: ViewModifier {
    @ObservedObject private var localeManager = LocaleManager.shared

    func body(content: Content) -> some View {
        content
            .environment(\.layoutDirection, localeManager.layoutDirection)
    }
}

extension View {
    /// Apply localized layout direction based on current language
    func localizedLayout() -> some View {
        modifier(LocalizedLayoutModifier())
    }
}
