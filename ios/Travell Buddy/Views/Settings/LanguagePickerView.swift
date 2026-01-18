//
//  LanguagePickerView.swift
//  Travell Buddy
//
//  View for selecting app language.
//

import SwiftUI

struct LanguagePickerView: View {
    @ObservedObject private var localeManager = LocaleManager.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            // System language option
            Section {
                Button {
                    localeManager.useSystemLanguage()
                    dismiss()
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("settings.language.system".localized)
                                .foregroundColor(.primary)
                            Text(systemLanguageDescription)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        if !localeManager.hasManualOverride {
                            Image(systemName: "checkmark")
                                .foregroundColor(.accentColor)
                        }
                    }
                }
            }

            // Manual language selection
            Section {
                ForEach(LocaleManager.SupportedLanguage.allCases) { language in
                    Button {
                        localeManager.setLanguage(language)
                        dismiss()
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(language.nativeName)
                                    .foregroundColor(.primary)
                                if language.nativeName != language.displayName {
                                    Text(language.displayName)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                            Spacer()
                            if localeManager.hasManualOverride &&
                               localeManager.currentLanguage == language {
                                Image(systemName: "checkmark")
                                    .foregroundColor(.accentColor)
                            }
                        }
                    }
                }
            } header: {
                Text("settings.language.manual".localized)
            }
        }
        .navigationTitle("settings.language".localized)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var systemLanguageDescription: String {
        let systemLang = LocaleManager.SupportedLanguage.from(
            code: Locale.preferredLanguages.first ?? "en"
        )
        return systemLang.nativeName
    }
}

// MARK: - Compact Language Picker (for inline use)

struct CompactLanguagePicker: View {
    @ObservedObject private var localeManager = LocaleManager.shared

    var body: some View {
        Menu {
            // System language
            Button {
                localeManager.useSystemLanguage()
            } label: {
                HStack {
                    Text("settings.language.system".localized)
                    if !localeManager.hasManualOverride {
                        Image(systemName: "checkmark")
                    }
                }
            }

            Divider()

            // All languages
            ForEach(LocaleManager.SupportedLanguage.allCases) { language in
                Button {
                    localeManager.setLanguage(language)
                } label: {
                    HStack {
                        Text(language.nativeName)
                        if localeManager.hasManualOverride &&
                           localeManager.currentLanguage == language {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "globe")
                Text(localeManager.currentLanguage.nativeName)
                    .lineLimit(1)
            }
            .font(.subheadline)
            .foregroundColor(.secondary)
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        LanguagePickerView()
    }
}
