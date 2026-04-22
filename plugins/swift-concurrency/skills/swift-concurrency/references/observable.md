# @Observable + @MainActor Interaction

Use this when:

- You are using the `@Observable` macro and need to understand how it interacts with actor isolation.
- You are migrating from `ObservableObject` to `@Observable` and hitting concurrency errors.
- You need to access `@Observable` properties from async contexts safely.
- You are combining `@Observable` with `@MainActor` in SwiftUI view models.

Skip this file if:

- You need general actor isolation guidance without Observation. Use `actors.md`.
- You need to understand Sendable conformance. Use `sendable.md`.
- You need migration steps for Swift 6 in general. Use `migration.md`.

Jump to:

- Why @Observable Does NOT Imply @MainActor
- The Correct Pattern for View Models
- SwiftUI Data Flow with Observation
- Accessing Observed Properties from Async Contexts
- Avoiding Data Races with @Observable + Actors
- Migrating from ObservableObject to @Observable
- Common Diagnostics and Fixes
- Decision Tree

---

## Why @Observable Does NOT Imply @MainActor

The `@Observable` macro adds observation tracking to your class - it synthesizes property accessors that notify SwiftUI when values change. But it does **not** add any actor isolation. This is a critical distinction:

```swift
// @Observable adds observation tracking only - no isolation
@Observable
final class ViewModel {
    var items: [Item] = []  // No actor isolation - accessible from any context
}
```

SwiftUI views read `@Observable` properties during `body` evaluation, which happens on the main actor. If a background task mutates an observed property concurrently, you get a data race.

**The fix**: Explicitly add `@MainActor` when the class drives UI:

```swift
@MainActor @Observable
final class ViewModel {
    var items: [Item] = []  // Now protected by main actor isolation
}
```

This is different from `ObservableObject`, where `@Published` properties were often (but not always) used with `@MainActor` view models. With `@Observable`, you must be explicit.

---

## The Correct Pattern for View Models

### Basic view model

```swift
@MainActor @Observable
final class ContentViewModel {
    var items: [Item] = []
    var isLoading = false
    var errorMessage: String?

    func loadItems() async {
        isLoading = true
        defer { isLoading = false }

        do {
            items = try await APIClient.fetchItems()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

Why this works:
- `@MainActor` ensures all property access is serialized on the main actor
- `async` methods can `await` background work, then update properties back on the main actor
- SwiftUI reads properties during `body` - guaranteed to be on main actor

### View model with background processing

When you need heavy computation off the main actor:

```swift
@MainActor @Observable
final class ImageProcessor {
    var processedImage: UIImage?
    var isProcessing = false

    func processImage(_ source: UIImage) async {
        isProcessing = true

        // Heavy work runs off main actor via nonisolated async function
        let result = await Self.applyFilters(to: source)

        processedImage = result
        isProcessing = false
    }

    // nonisolated + async = runs on cooperative thread pool, not main actor
    private nonisolated static func applyFilters(to image: UIImage) async -> UIImage {
        // CPU-intensive work here
        return image
    }
}
```

### View model with a dedicated actor for state

For complex state that isn't purely UI:

```swift
actor DataStore {
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? { cache[key] }
    func set(_ key: String, value: Data) { cache[key] = value }
}

@MainActor @Observable
final class CachedContentViewModel {
    var items: [Item] = []
    private let store = DataStore()

    func loadItem(_ id: String) async {
        if let cached = await store.get(id) {
            items.append(Item(data: cached))
        } else {
            let data = try? await APIClient.fetch(id)
            if let data {
                await store.set(id, value: data)
                items.append(Item(data: data))
            }
        }
    }
}
```

---

## SwiftUI Data Flow with Observation

The Observation framework (iOS 17+, macOS 14+) changes how SwiftUI tracks changes. Key differences from `ObservableObject`:

| Aspect | ObservableObject | @Observable |
|--------|-----------------|-------------|
| View updates | Any `@Published` change triggers update | Only properties read in `body` trigger update |
| Ownership | `@StateObject` | `@State` |
| Injection | `@EnvironmentObject` | `@Environment` |
| Binding | `$object.property` via `@Published` | `@Bindable` wrapper |
| Protocol | `ObservableObject` | `Observable` (via macro) |

### Storing observable objects

```swift
struct ContentView: View {
    @State private var viewModel = ContentViewModel()

    var body: some View {
        List(viewModel.items) { item in
            ItemRow(item: item)
        }
        .task { await viewModel.loadItems() }
    }
}
```

`@State` instantiates the object once per view lifetime - the same guarantee `@StateObject` provided, but now for `@Observable` types. Do NOT use `@StateObject` with `@Observable`.

### Passing via environment

```swift
// App-level setup
@main
struct MyApp: App {
    @State private var library = Library()

    var body: some Scene {
        WindowGroup {
            LibraryView()
                .environment(library)  // Not .environmentObject()
        }
    }
}

// Consuming view
struct LibraryView: View {
    @Environment(Library.self) private var library

    var body: some View {
        List(library.books) { book in
            BookView(book: book)
        }
    }
}
```

### Two-way bindings with @Bindable

For views that need to write back to `@Observable` properties:

```swift
struct EditBookView: View {
    @Bindable var book: Book  // @Bindable, not @ObservedObject

    var body: some View {
        Form {
            TextField("Title", text: $book.title)
            Toggle("Available", isOn: $book.isAvailable)
        }
    }
}
```

### Optional environment objects

```swift
// Returns nil instead of crashing if not set
@Environment(Library.self) private var library: Library?
```

### Performance advantage

With `ObservableObject`, a view re-evaluates whenever **any** `@Published` property changes. With `@Observable`, SwiftUI tracks which properties `body` actually reads and only updates when those specific properties change. This is automatic - no opt-in needed.

---

## Accessing Observed Properties from Async Contexts

### The problem

```swift
@Observable
final class ViewModel {
    var items: [Item] = []

    func loadItems() async {
        // Which thread does this run on? It depends on the caller's context.
        // If called from a nonisolated context, this could be a background thread.
        items = await APIClient.fetchItems()  // ⚠️ Potential data race
    }
}
```

Without `@MainActor`, there's no guarantee about which isolation domain `loadItems` executes in. If SwiftUI is simultaneously reading `items` in `body` (on the main actor), you have a data race.

### Solution 1: Isolate the whole class (preferred for view models)

```swift
@MainActor @Observable
final class ViewModel {
    var items: [Item] = []

    func loadItems() async {
        items = await APIClient.fetchItems()  // ✅ Runs on main actor
    }
}
```

### Solution 2: Isolate specific mutations

When only some properties are UI-bound:

```swift
@Observable
final class DataProcessor {
    @MainActor var results: [Result] = []  // UI-bound
    var internalState: ProcessingState = .idle  // Not UI-bound

    func process() async {
        internalState = .processing
        let processed = await heavyComputation()
        await MainActor.run {
            results = processed  // ✅ Mutation on main actor
        }
        internalState = .idle
    }
}
```

### Solution 3: nonisolated(nonsending) for inherited isolation (Swift 6.2+)

```swift
@Observable
final class ViewModel {
    var items: [Item] = []

    // Inherits caller's isolation - if called from @MainActor view, runs on main actor
    nonisolated(nonsending) func loadItems() async {
        items = await APIClient.fetchItems()
    }
}
```

With `NonisolatedNonsendingByDefault` enabled, this is the default behavior for nonisolated async functions.

---

## Avoiding Data Races with @Observable + Actors

### Pattern: Actor-backed observable

Separate the observation layer (main actor) from the data layer (custom actor):

```swift
actor ArticleStore {
    private var articles: [Article] = []

    func fetchAll() async -> [Article] {
        // Network call, database read, etc.
        return articles
    }

    func add(_ article: Article) {
        articles.append(article)
    }
}

@MainActor @Observable
final class ArticleListViewModel {
    var articles: [Article] = []
    var isLoading = false
    private let store = ArticleStore()

    func refresh() async {
        isLoading = true
        articles = await store.fetchAll()
        isLoading = false
    }
}
```

### Pattern: Sending values across isolation

When transferring non-Sendable data from an actor to an `@Observable` view model:

```swift
@MainActor @Observable
final class ViewModel {
    var items: [Item] = []

    func loadFromActor(_ store: DataStore) async {
        // Values crossing actor boundary must be Sendable
        let fetchedItems = await store.fetchItems()  // [Item] must be Sendable
        items = fetchedItems
    }
}
```

Make your data types `Sendable`:

```swift
struct Item: Sendable, Identifiable {
    let id: UUID
    let name: String
    let value: Int
}
```

---

## Migrating from ObservableObject to @Observable

### Step-by-step

1. Replace `ObservableObject` conformance with `@Observable` macro
2. Remove all `@Published` property wrappers
3. Add `@MainActor` if the class is UI-bound
4. Update views: `@StateObject` → `@State`, `@EnvironmentObject` → `@Environment`
5. Update bindings: `@ObservedObject` → `@Bindable` where bindings are needed
6. Remove `objectWillChange` publishers if used

### Before

```swift
class Library: ObservableObject {
    @Published var books: [Book] = []
    @Published var isLoading = false
}

struct LibraryView: View {
    @StateObject private var library = Library()

    var body: some View {
        List(library.books) { book in
            BookView(book: book)
        }
    }
}

struct BookEditor: View {
    @ObservedObject var library: Library

    var body: some View {
        // Uses $library.books for binding
    }
}
```

### After

```swift
@MainActor @Observable
final class Library {
    var books: [Book] = []
    var isLoading = false
}

struct LibraryView: View {
    @State private var library = Library()

    var body: some View {
        List(library.books) { book in
            BookView(book: book)
        }
    }
}

struct BookEditor: View {
    @Bindable var library: Library

    var body: some View {
        // Uses $library.books for binding
    }
}
```

### Incremental migration

You can mix `ObservableObject` and `@Observable` types in the same app. SwiftUI tracks changes differently:
- `@Observable`: updates only when properties read by `body` change
- `ObservableObject`: updates when any `@Published` property changes

This means migrating one type at a time is safe, but you may notice slightly different update behavior.

### When NOT to use @Observable

- **Value types**: `@Observable` only works with classes. Use regular structs with `@State`.
- **Types that must be Sendable without actor isolation**: `@Observable` classes are reference types - they need actor isolation or `@unchecked Sendable`.
- **Backward compatibility below iOS 17/macOS 14**: `@Observable` requires the Observation framework.

---

## Common Diagnostics and Fixes

### "Main actor-isolated property cannot be mutated from a nonisolated context"

```swift
@MainActor @Observable
final class ViewModel {
    var items: [Item] = []
}

// ❌ Calling from nonisolated async context
func loadItems(vm: ViewModel) async {
    vm.items = await fetch()  // Error
}

// ✅ Fix: await MainActor.run or make the function @MainActor
@MainActor
func loadItems(vm: ViewModel) async {
    vm.items = await fetch()
}
```

### "@Observable class conforms to ObservableObject"

Don't conform to both protocols:

```swift
// ❌ Conflicting observation systems
@Observable
final class ViewModel: ObservableObject { ... }

// ✅ Pick one - prefer @Observable for new code
@Observable
final class ViewModel { ... }
```

### "Cannot use @StateObject with @Observable"

```swift
// ❌ Wrong wrapper for @Observable
@StateObject var vm = ViewModel()

// ✅ Use @State for @Observable
@State var vm = ViewModel()
```

### "Expression requires @MainActor isolation" inside .task { }

SwiftUI's `.task` modifier inherits the view's isolation (which is `@MainActor`). But if you call a method on a non-isolated `@Observable` object, you may see isolation errors:

```swift
@Observable
final class ViewModel {
    var items: [Item] = []
    func load() async { items = await fetch() }
}

struct MyView: View {
    @State var vm = ViewModel()
    var body: some View {
        List(vm.items) { ... }
            .task { await vm.load() }  // ⚠️ May warn about isolation
    }
}

// ✅ Fix: Add @MainActor to the ViewModel
@MainActor @Observable
final class ViewModel { ... }
```

---

## Decision Tree

```
Using @Observable macro?
├─ Class drives SwiftUI UI?
│  ├─ Yes → Add @MainActor to the class
│  │  ├─ Need bindings? → Use @Bindable in subviews
│  │  ├─ Need environment? → Use .environment() and @Environment
│  │  └─ Need heavy background work? → Extract to nonisolated static func or separate actor
│  └─ No (pure data/logic)
│     ├─ Needs thread safety? → Make it an actor instead
│     └─ Single-threaded use? → @Observable without @MainActor is fine
│
├─ Migrating from ObservableObject?
│  ├─ Replace @Published with plain var
│  ├─ Replace @StateObject with @State
│  ├─ Replace @EnvironmentObject with @Environment
│  ├─ Replace @ObservedObject with @Bindable (if bindings needed)
│  └─ Add @MainActor if UI-bound
│
└─ Seeing concurrency errors?
   ├─ "cannot be mutated from nonisolated context" → Add @MainActor to class or method
   ├─ "non-Sendable type" crossing boundaries → Make data types Sendable or keep in one isolation domain
   └─ Race condition at runtime → Verify all UI-bound mutations happen on @MainActor
```

## Best Practices

1. **Always pair `@Observable` with `@MainActor` for view models** - the macro does not add isolation.
2. **Use `@State` for ownership, `@Environment` for injection, `@Bindable` for bindings** - never use the old `ObservableObject` wrappers with `@Observable`.
3. **Prefer whole-class `@MainActor` over per-property isolation** - simpler to reason about and maintain.
4. **Extract heavy computation to nonisolated functions or separate actors** - keep the view model thin.
5. **Make data types Sendable** - especially types that flow between actors and observable view models.
6. **Don't conform to both `ObservableObject` and `Observable`** - pick one per type.
7. **Test with Thread Sanitizer** - catches runtime data races that the compiler may miss in Swift 5 mode.
