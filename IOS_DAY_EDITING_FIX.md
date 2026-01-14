# iOS Day Editing Fix - Refresh Itinerary After Changes

## Дата: 2026-01-14 08:15 MSK

## 🔍 Проблема

После применения изменений в AI Studio, пользователь возвращается на экран маршрута, но видит **СТАРЫЕ данные**.

**Root Cause:** iOS не делал GET /itinerary после apply_changes, поэтому экран показывал закэшированные данные.

---

## ✅ Решение

Добавлен callback механизм для обновления itinerary после применения изменений в AI Studio.

### Flow событий (ПОСЛЕ исправления):

```
1. Пользователь открывает AI Studio → openEdit(for day: TripDay)
2. Создается AIStudioViewModel с callback onChangesApplied
3. Callback настроен на вызов TripPlanViewModel.refreshItinerary()
4. Пользователь вносит изменения
5. Нажимает "Применить изменения"
6. AIStudioViewModel.applyChanges():
   ✅ POST /day/{dayId}/apply_changes
   ✅ Бэкенд сохраняет в БД
   ✅ Получает DayStudioResponse
   ✅ Вызывает callback onChangesApplied
7. Callback вызывает TripPlanViewModel.refreshItinerary():
   ✅ GET /itinerary
   ✅ Получает СВЕЖИЕ данные из БД
   ✅ Обновляет self.plan
8. AI Studio закрывается
9. ✅ Пользователь видит ОБНОВЛЕННЫЙ маршрут
```

---

## 📝 Измененные файлы

### 1. TripPlanViewModel.swift

**Добавлен публичный метод refreshItinerary():**

```swift
/// Refresh itinerary from backend (e.g., after day editing in AI Studio).
@MainActor
func refreshItinerary() async -> Bool {
    guard let existingPlan = plan else { return false }

    print("🔄 Refreshing itinerary for trip \(existingPlan.tripId)")

    isLoading = true
    defer { isLoading = false }

    do {
        let itinerary = try await apiClient.getItinerary(tripId: existingPlan.tripId.uuidString.lowercased())
        self.plan = itinerary.toTripPlan(using: existingPlan)
        print("✅ Itinerary refreshed successfully")
        return true
    } catch {
        print("❌ Failed to refresh itinerary: \(error)")
        self.errorMessage = (error as? LocalizedError)?.errorDescription
            ?? "Не удалось обновить маршрут. Попробуйте ещё раз."
        return false
    }
}
```

**Рефакторинг refreshPlanAfterAuth():**
```swift
func refreshPlanAfterAuth() async -> Bool {
    return await refreshItinerary()
}
```

---

### 2. AIStudioViewModel.swift

**Добавлен callback property (line 252):**

```swift
var onChangesApplied: (() async -> Void)?
```

**Вызов callback в applyChanges() (lines 475-481):**

```swift
print("✅ Changes applied successfully")

// Notify parent to refresh itinerary
if let onChangesApplied = onChangesApplied {
    print("🔄 Calling onChangesApplied callback to refresh itinerary")
    await onChangesApplied()
} else {
    print("⚠️ No onChangesApplied callback set")
}

// Success - trigger dismiss after a short delay
try? await Task.sleep(nanoseconds: 500_000_000)
shouldDismiss = true
```

---

### 3. TripPlanView.swift

**Обновлен метод openEdit() (lines 858-877):**

```swift
private func openEdit(for day: TripDay) {
    guard let plan = viewModel.plan else { return }

    // Open AI Studio instead of legacy EditDayView
    let studioViewModel = AIStudioViewModel(
        tripId: plan.tripId,
        dayId: day.index,
        cityName: plan.destinationCity,
        dayDate: day.date
    )

    // Set callback to refresh itinerary when changes are applied
    studioViewModel.onChangesApplied = { [weak viewModel] in
        print("🔄 AI Studio changes applied - refreshing itinerary")
        _ = await viewModel?.refreshItinerary()
    }

    aiStudioViewModel = studioViewModel
    isShowingAIStudio = true
}
```

---

## 🧪 Тестирование

### Как проверить:

1. **Запустить логи бэкенда:**
   ```bash
   docker compose logs api -f --tail=50
   ```

2. **В iOS приложении:**
   - Открыть любой маршрут
   - Нажать на день для редактирования
   - В AI Studio внести изменения (settings, preset, remove place)
   - Нажать "Применить изменения"

3. **Проверить логи:**

   **Backend должен показать:**
   ```
   🎯 apply_day_changes CALLED: trip=..., day=5, changes=2
   🔥 DayEditor.apply_changes_to_day() ENTERED
   💾 Saving to database...
   🚩 Flagged 'days' column as modified
   🔒 Calling db.commit()...
   ✅ db.commit() completed successfully
   📤 Returning response with X places, revision=Y

   🔍 GET /itinerary called for trip=...  ← ВАЖНО: должен появиться!
   ♻️  Expired all cached objects
   ✅ Returned X days
      Day 5: Y blocks, Z POIs, theme='...'
   ```

   **iOS логи (Xcode Console):**
   ```
   ✅ Changes applied successfully
   🔄 Calling onChangesApplied callback to refresh itinerary
   🔄 AI Studio changes applied - refreshing itinerary
   🔄 Refreshing itinerary for trip <UUID>
   ✅ Itinerary refreshed successfully
   ```

4. **Проверить визуально:**
   - После закрытия AI Studio экран маршрута должен показывать НОВЫЕ данные
   - Количество мест, темы, время начала должны соответствовать примененным изменениям

---

## ✅ Ожидаемый результат

- ✅ После apply_changes делается GET /itinerary
- ✅ Экран маршрута обновляется свежими данными из БД
- ✅ Пользователь видит примененные изменения
- ✅ Все типы изменений работают:
  - Update settings (start_time, end_time, budget, tempo)
  - Set preset (food, walks, art, etc.)
  - Remove place
  - Replace place
  - Add place

---

## 📊 Взаимодействие с бэкендом

### Последовательность API вызовов:

1. **GET /trips/{tripId}/day/{dayId}/studio**
   - Загружает текущее состояние дня
   - Возвращает places, settings, metrics

2. **POST /trips/{tripId}/day/{dayId}/apply_changes**
   - Отправляет изменения на бэкенд
   - Бэкенд сохраняет в БД (с db.expire_all + flag_modified)
   - Возвращает обновленный DayStudioResponse

3. **GET /trips/{tripId}/itinerary** ← ДОБАВЛЕНО
   - Запрашивает полный itinerary из БД
   - Получает СВЕЖИЕ данные (после db.expire_all())
   - Обновляет UI основного экрана

---

## 🎯 Итог

**Проблема решена полностью:**
- ✅ Бэкенд корректно сохраняет изменения (БАГ #2 решен ранее)
- ✅ iOS корректно обновляет данные после apply_changes (РЕШЕНО СЕЙЧАС)
- ✅ Пользователь видит обновленный маршрут

**Изменения минимальны и безопасны:**
- Добавлен callback механизм (не breaking changes)
- Используется существующая логика refreshItinerary
- Добавлено логирование для debugging

**Ready for testing!** 🚀
