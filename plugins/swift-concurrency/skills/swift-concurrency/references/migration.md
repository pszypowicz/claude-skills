# Swift 6 Migration

Use this when:

- You are migrating a project from Swift 5 to Swift 6 language mode.
- You need to enable strict concurrency checking incrementally.
- You are converting closure-based or Combine/RxSwift code to async/await.
- You need to understand `@preconcurrency` and when to use it.
- You are adopting Swift 6.2 Approachable Concurrency features.

Skip this file if:

- You need to understand the threading model. Use `threading.md`.
- You need actor isolation patterns. Use `actors.md`.
- You need Sendable conformance details. Use `sendable.md`.
- You need `@Observable` migration from `ObservableObject`. Use `observable.md`.

Jump to:

- Why Migrate to Swift 6
- Project Settings Matrix
- The Concurrency Rabbit Hole
- Six Migration Habits
- Step-by-Step Migration
- Migration Tooling
- Rewriting Closures to Async/Await
- @preconcurrency Usage
- Migrating from Combine/RxSwift
- When to Use AsyncAlgorithms
- Real-World Migration Examples
- Concurrency-Safe Notifications (iOS 26+)
- Anti-Patterns
- Common Challenges
- Common Agent Mistakes

---

## Why Migrate to Swift 6

Swift 6 enforces **complete data-race safety at compile time**. In Swift 5, data races are runtime bugs — silent until they crash. In Swift 6, they are compile errors.

Benefits:

- **Eliminates a class of bugs** — data races cannot ship.
- **Compiler-guided migration** — diagnostics tell you exactly what is wrong.
- **Incremental adoption** — enable strict checking as warnings first, then errors.
- **Future-proof** — Swift 6 mode is the long-term direction; Swift 5 mode will eventually be deprecated.

Costs:

- **Initial migration effort** — existing code will produce many new diagnostics.
- **Dependency readiness** — some libraries may not be Sendable-annotated yet.
- **Learning curve** — the isolation model requires a mindset shift from GCD.

The question is not whether to migrate, but when and how fast.

---

## Project Settings Matrix

These settings control concurrency behavior. Check them before making any migration decision.

| Setting | Values | Effect |
|---|---|---|
| **Language mode** | Swift 5, Swift 6 | Swift 6 makes concurrency errors into compile errors |
| **Strict concurrency** | `minimal`, `targeted`, `complete` | Level of concurrency checking (Swift 5 mode only; Swift 6 is always `complete`) |
| **Default isolation** | `nonisolated`, `MainActor` | SE-466: what isolation unannotated code gets |
| **NonisolatedNonsendingByDefault** | enabled/disabled | SE-461: nonisolated async inherits caller isolation |
| **Approachable Concurrency** | combination of above | Umbrella term for SE-461 + SE-466 together |

### Where to set them

| Setting | SwiftPM (`Package.swift`) | Xcode (Build Settings) |
|---|---|---|
| Language mode | `swiftLanguageVersions: [.v6]` or per-target `-swift-version 6` | `SWIFT_VERSION = 6` |
| Strict concurrency | `.enableExperimentalFeature("StrictConcurrency=targeted")` | `SWIFT_STRICT_CONCURRENCY = targeted` |
| Default isolation | `.defaultIsolation(MainActor.self)` | `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` |
| NonisolatedNonsendingByDefault | `.enableUpcomingFeature("NonisolatedNonsendingByDefault")` | `SWIFT_UPCOMING_FEATURE_NONISOLATEDNONSENDINGBYDEFAULT = YES` |

### Recommended progression

```
Phase 1: Swift 5 + StrictConcurrency=targeted  (warnings for obvious issues)
Phase 2: Swift 5 + StrictConcurrency=complete   (warnings for all issues)
Phase 3: Swift 6 language mode                   (all warnings become errors)
Phase 4: Swift 6.2 + Approachable Concurrency    (fewer annotations needed)
```

### Approachable Concurrency (Swift 6.2)

"Approachable Concurrency" is the umbrella term for combining:

- **SE-461** (`NonisolatedNonsendingByDefault`): nonisolated async functions inherit caller isolation.
- **SE-466** (default isolation = `MainActor`): all unannotated code is `@MainActor` by default.

Together, these dramatically reduce the number of annotations needed and the number of Sendable errors in typical app code. They are the recommended end state for app targets.

---

## The Concurrency Rabbit Hole

A common migration failure mode: you fix one diagnostic, which reveals three more. Those three each reveal five more. You are now refactoring half the codebase.

This happens because concurrency safety is **transitive**. Making one type Sendable forces all its stored properties to be Sendable, which forces their types to be Sendable, and so on.

### How to avoid it

1. **Migrate leaf modules first.** Start with modules that have no internal dependencies — utilities, models, networking layers.
2. **Use `@preconcurrency` as a boundary.** When a dependency is not yet migrated, mark the import `@preconcurrency` to suppress diagnostics at that boundary.
3. **Fix one category at a time.** Do all Sendable conformances first, then all actor isolation issues, then all async boundary issues.
4. **Set a time box.** If a fix cascades into more than 2-3 files, stop and reassess the approach.
5. **Accept temporary escape hatches.** `@unchecked Sendable`, `nonisolated(unsafe)`, and `@preconcurrency` are legitimate migration tools — document them and plan follow-up removal.

---

## Six Migration Habits

These habits prevent the most common migration mistakes:

### 1. Read the diagnostic, not just the fix-it

Xcode fix-its for concurrency diagnostics are often wrong. They may suggest `@Sendable` when the real fix is actor isolation, or suggest `nonisolated` when the code genuinely needs main actor access.

### 2. One category of change per commit

Mix Sendable fixes with actor isolation changes and you will never be able to bisect regressions. Keep commits focused:
- Commit 1: Add Sendable conformances to model types
- Commit 2: Isolate view models to @MainActor
- Commit 3: Update async boundaries

### 3. Build after every change

Do not batch fixes. The compiler's diagnostics change as you fix issues — a fix in file A may resolve or create diagnostics in file B.

### 4. Test after every category

Run your test suite after completing each category of fix. Concurrency changes can subtly alter timing behavior.

### 5. Prefer the smallest safe change

Do not refactor to actors when `@MainActor` suffices. Do not make types Sendable when `@preconcurrency` on the import is the right interim fix. Minimize blast radius.

### 6. Document every escape hatch

Every `@unchecked Sendable`, `nonisolated(unsafe)`, and `@preconcurrency` should have a comment explaining why it is safe and when it can be removed.

---

## Step-by-Step Migration

### Step 1: Find isolated code

Audit your codebase for code that is already implicitly main-thread-bound:

- UIViewController subclasses and their methods
- SwiftUI view bodies and view models
- Delegate callbacks that assume main thread
- NotificationCenter observers updating UI

These should be explicitly annotated `@MainActor`.

### Step 2: Update dependencies

Check each dependency for Swift 6 readiness:

```bash
# Check if a package compiles with strict concurrency
swift build -Xswiftc -strict-concurrency=complete
```

For dependencies not yet migrated, plan to use `@preconcurrency import`.

### Step 3: Add async alternatives

For callback-based APIs that you own, add async overloads:

```swift
// Existing callback API
func fetchUser(id: String, completion: @escaping (Result<User, Error>) -> Void)

// Add async alternative
func fetchUser(id: String) async throws -> User {
    try await withCheckedThrowingContinuation { continuation in
        fetchUser(id: id) { result in
            continuation.resume(with: result)
        }
    }
}
```

### Step 4: Change default isolation (Swift 6.2+)

For app targets (not libraries), set `MainActor` as default isolation:

```swift
// Package.swift
.target(
    name: "MyApp",
    swiftSettings: [
        .defaultIsolation(MainActor.self)
    ]
)
```

This makes all unannotated code `@MainActor`, reducing the number of explicit annotations needed.

**Do not set default isolation for library targets** — it forces isolation on consumers.

### Step 5: Enable strict concurrency checking

Progress through three levels:

**Level 1: Targeted** — checks only code that uses concurrency features.

```swift
// SwiftPM
.enableExperimentalFeature("StrictConcurrency=targeted")
// Xcode
// SWIFT_STRICT_CONCURRENCY = targeted
```

**Level 2: Complete** — checks all code, but as warnings.

```swift
// SwiftPM
.enableExperimentalFeature("StrictConcurrency=complete")
// Xcode
// SWIFT_STRICT_CONCURRENCY = complete
```

**Level 3: Swift 6 mode** — all concurrency warnings become errors.

```swift
// SwiftPM
swiftLanguageVersions: [.v6]
// or per-target:
.swiftLanguageMode(.v6)
// Xcode
// SWIFT_VERSION = 6
```

### Step 6: Add Sendable conformances

Make value types that cross isolation boundaries Sendable:

```swift
// Structs with Sendable stored properties are straightforward
struct User: Sendable {
    let id: String
    let name: String
}

// Enums with Sendable associated values
enum AppError: Error, Sendable {
    case network(String)
    case validation(String)
}

// Classes require more care
final class Configuration: Sendable {
    let apiKey: String  // All stored properties must be let + Sendable
    let baseURL: URL

    init(apiKey: String, baseURL: URL) {
        self.apiKey = apiKey
        self.baseURL = baseURL
    }
}
```

### Step 7: Enable Approachable Concurrency

Once on Swift 6.2, enable both features:

```swift
// Package.swift
.target(
    name: "MyApp",
    swiftSettings: [
        .defaultIsolation(MainActor.self),
        .enableUpcomingFeature("NonisolatedNonsendingByDefault")
    ]
)
```

This combination eliminates many remaining annotations and Sendable errors.

### Step 8: Enable upcoming features

Additional upcoming features to consider:

```swift
.enableUpcomingFeature("InternalImportsByDefault")  // Reduces accidental public API
.enableUpcomingFeature("GlobalActorIsolatedTypesUsability")  // Smoother actor-isolated types
```

### Step 9: Switch to Swift 6 language mode

Once all diagnostics are resolved at `StrictConcurrency=complete`:

```swift
// SwiftPM
.swiftLanguageMode(.v6)
// Xcode
// SWIFT_VERSION = 6
```

All concurrency warnings become errors. You now have compile-time data-race safety.

---

## Migration Tooling

### Xcode Migrate Mode

Xcode provides a migration assistant:

1. **Edit > Convert > To Current Swift Syntax** — handles some concurrency annotations.
2. **Build with strict concurrency** — surfaces all diagnostics in the Issue Navigator.
3. **Fix-it suggestions** — available for many concurrency diagnostics (but verify them manually).

Review every fix-it. Xcode may suggest adding `@Sendable` where actor isolation is the better fix, or suggest `nonisolated` where `@MainActor` is correct.

### swift package migrate

For SwiftPM packages, use the migration command:

```bash
# Dry run — shows what would change
swift package migrate --targets MyTarget --to-language-mode 6 --dry-run

# Apply changes
swift package migrate --targets MyTarget --to-language-mode 6
```

This command:
- Enables Swift 6 language mode for the specified targets.
- Applies compiler-suggested fix-its automatically.
- Reports diagnostics that require manual intervention.

**Always review the diff after running `swift package migrate`.** The automated fixes are not always the best solution — they tend toward escape hatches like `@preconcurrency` rather than proper isolation.

---

## Rewriting Closures to Async/Await

### Basic callback to async

```swift
// Before: Callback-based
func loadData(completion: @escaping (Data?) -> Void) {
    URLSession.shared.dataTask(with: url) { data, _, _ in
        completion(data)
    }.resume()
}

// After: Async
func loadData() async throws -> Data {
    let (data, _) = try await URLSession.shared.data(from: url)
    return data
}
```

### withCheckedContinuation for APIs you don't control

```swift
func geocode(address: String) async throws -> CLPlacemark {
    try await withCheckedThrowingContinuation { continuation in
        CLGeocoder().geocodeAddressString(address) { placemarks, error in
            if let error {
                continuation.resume(throwing: error)
            } else if let placemark = placemarks?.first {
                continuation.resume(returning: placemark)
            } else {
                continuation.resume(throwing: GeocodingError.noResult)
            }
        }
    }
}
```

### Critical rules for continuations

- **Resume exactly once.** Missing a resume leaks the task forever. Resuming twice crashes.
- **Handle all paths.** Every code path in the callback must call `continuation.resume`.
- **Use `withCheckedContinuation` during development** — it crashes on misuse. Switch to `withUnsafeContinuation` only if profiling shows overhead.

### Delegate pattern to AsyncStream

```swift
// Before: Delegate
class LocationTracker: NSObject, CLLocationManagerDelegate {
    var onLocationUpdate: ((CLLocation) -> Void)?

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        locations.forEach { onLocationUpdate?($0) }
    }
}

// After: AsyncStream
class LocationTracker: NSObject, CLLocationManagerDelegate {
    private var continuation: AsyncStream<CLLocation>.Continuation?

    var locations: AsyncStream<CLLocation> {
        AsyncStream { continuation in
            self.continuation = continuation
            continuation.onTermination = { _ in
                self.locationManager.stopUpdatingLocation()
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        locations.forEach { continuation?.yield($0) }
    }
}

// Usage
for await location in tracker.locations {
    updateMap(with: location)
}
```

---

## @preconcurrency Usage

`@preconcurrency` suppresses concurrency diagnostics at module boundaries. It is a migration tool, not a permanent solution.

### @preconcurrency import

Suppresses Sendable warnings for types from the imported module:

```swift
@preconcurrency import SomeLibrary

// SomeLibrary.SomeType used across isolation boundaries
// without Sendable warnings — until SomeLibrary adds Sendable conformances
```

When the library adds proper Sendable conformances, the compiler warns that `@preconcurrency` is unnecessary. Remove it then.

### @preconcurrency on protocol conformances

When conforming to a protocol that has not been updated for concurrency:

```swift
// The protocol requires a method that is not isolated
protocol LegacyDelegate {
    func didReceiveData(_ data: Data)
}

// Your implementation needs @MainActor
@MainActor
class Handler: @preconcurrency LegacyDelegate {
    func didReceiveData(_ data: Data) {
        // This is @MainActor, but the protocol doesn't know that
        updateUI(with: data)
    }
}
```

### When to use @preconcurrency

- **Import**: The dependency has not added Sendable conformances yet.
- **Protocol conformance**: The protocol has not been annotated with isolation requirements yet.
- **Typealias**: To suppress warnings on type aliases crossing boundaries.

### When NOT to use @preconcurrency

- As a blanket silencer for all concurrency warnings in your own code.
- On your own protocols — fix the protocol instead.
- When a proper Sendable conformance or actor isolation is straightforward.

---

## Migrating from Combine/RxSwift

### The Observation alternative

For the most common Combine use case — observable state driving SwiftUI — the Observation framework is the replacement:

```swift
// Before: Combine
class ViewModel: ObservableObject {
    @Published var items: [Item] = []
    @Published var isLoading = false
    private var cancellables = Set<AnyCancellable>()

    func load() {
        isLoading = true
        APIClient.fetchItems()
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] _ in self?.isLoading = false },
                receiveValue: { [weak self] in self?.items = $0 }
            )
            .store(in: &cancellables)
    }
}

// After: Observation + async/await
@MainActor @Observable
final class ViewModel {
    var items: [Item] = []
    var isLoading = false

    func load() async {
        isLoading = true
        defer { isLoading = false }
        items = (try? await APIClient.fetchItems()) ?? []
    }
}
```

### Debouncing

Combine's `.debounce()` is commonly used for search fields:

```swift
// Before: Combine debounce
$searchText
    .debounce(for: .milliseconds(300), scheduler: RunLoop.main)
    .removeDuplicates()
    .sink { [weak self] query in
        self?.performSearch(query)
    }
    .store(in: &cancellables)

// After: AsyncAlgorithms debounce (if you need it)
// Or the simpler task-cancellation pattern:
@MainActor @Observable
final class SearchViewModel {
    var searchText = "" {
        didSet { restartSearch() }
    }
    var results: [SearchResult] = []
    private var searchTask: Task<Void, Never>?

    private func restartSearch() {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            results = await SearchService.search(searchText)
        }
    }
}
```

### Mindset shift: Reactive streams to structured concurrency

| Combine/RxSwift | Swift Concurrency |
|---|---|
| Publisher chain | `async` function |
| `.sink` / `.subscribe` | `for await` loop or `.task` modifier |
| `.receive(on: DispatchQueue.main)` | `@MainActor` isolation |
| `AnyCancellable` | `Task` cancellation |
| `PassthroughSubject` | `AsyncStream` with continuation |
| `CurrentValueSubject` | `@Observable` property |
| `.combineLatest` | `AsyncAlgorithms.combineLatest` or task group |
| `.debounce` | `Task.sleep` + cancellation, or `AsyncAlgorithms.debounce` |
| `.map` / `.filter` | `.map` / `.filter` on `AsyncSequence` |
| Error handling in chain | `try`/`catch` around `await` |

### Actor isolation with Combine sink

If you must keep Combine during migration, fix isolation issues in `.sink`:

```swift
// ❌ Potential isolation violation
publisher
    .sink { [weak self] value in
        self?.updateUI(value)  // Which isolation domain is this?
    }

// ✅ Explicit isolation
publisher
    .receive(on: DispatchQueue.main)
    .sink { [weak self] value in
        // Guaranteed main thread, but not compiler-checked
        self?.updateUI(value)
    }

// ✅ Better: Use MainActor.assumeIsolated inside the closure
publisher
    .receive(on: DispatchQueue.main)
    .sink { [weak self] value in
        MainActor.assumeIsolated {
            self?.updateUI(value)  // Compiler knows this is @MainActor
        }
    }
```

### What NOT to migrate

Not all Combine usage needs migration:

- **Framework APIs that return publishers** (e.g., `NotificationCenter.Publisher`) — keep using them if they work; async alternatives will come.
- **Complex reactive pipelines** with many operators — migrate only when you have test coverage.
- **Shared publishers with multiple subscribers** — `AsyncStream` is single-consumer; you need `AsyncBroadcastSequence` (Async Algorithms) or a custom solution.

---

## When to Use AsyncAlgorithms

The Swift Async Algorithms package provides Combine-like operators for `AsyncSequence`. Use it when:

- You need `debounce`, `throttle`, `combineLatest`, or `merge` on async sequences.
- You are migrating complex Combine pipelines that combine multiple streams.
- You need `AsyncChannel` for multi-producer/multi-consumer patterns.
- You need `AsyncTimerSequence` for recurring timer events.

```swift
import AsyncAlgorithms

// Debounce an async sequence
for await value in searchTerms.debounce(for: .milliseconds(300)) {
    await performSearch(value)
}

// Combine two async sequences
for await (location, heading) in combineLatest(locationStream, headingStream) {
    updateMap(location: location, heading: heading)
}

// Merge multiple streams
for await event in merge(networkEvents, localEvents) {
    handle(event)
}
```

Do NOT use AsyncAlgorithms when:

- Simple `Task.sleep` + cancellation achieves the same result (e.g., basic debounce).
- You have a single async operation, not a stream.
- Adding a dependency is not justified by the complexity of your stream processing.

---

## Real-World Migration Examples

### Example 1: Networking layer

```swift
// Before: Callback-based with GCD
class APIClient {
    func fetchUser(id: String, completion: @escaping (Result<User, APIError>) -> Void) {
        let request = buildRequest(for: id)
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                DispatchQueue.main.async { completion(.failure(.network(error))) }
                return
            }
            guard let data = data else {
                DispatchQueue.main.async { completion(.failure(.noData)) }
                return
            }
            do {
                let user = try JSONDecoder().decode(User.self, from: data)
                DispatchQueue.main.async { completion(.success(user)) }
            } catch {
                DispatchQueue.main.async { completion(.failure(.decode(error))) }
            }
        }.resume()
    }
}

// After: Async/await
struct APIClient {
    func fetchUser(id: String) async throws -> User {
        let request = buildRequest(for: id)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw APIError.badResponse
        }
        return try JSONDecoder().decode(User.self, from: data)
    }
}
```

### Example 2: DispatchQueue-protected state to actor

```swift
// Before: Queue-based thread safety
class ImageCache {
    private let queue = DispatchQueue(label: "image-cache", attributes: .concurrent)
    private var cache: [URL: UIImage] = [:]

    func image(for url: URL) -> UIImage? {
        queue.sync { cache[url] }
    }

    func store(_ image: UIImage, for url: URL) {
        queue.async(flags: .barrier) { self.cache[url] = image }
    }
}

// After: Actor
actor ImageCache {
    private var cache: [URL: UIImage] = [:]

    func image(for url: URL) -> UIImage? {
        cache[url]
    }

    func store(_ image: UIImage, for url: URL) {
        cache[url] = image
    }
}
```

### Example 3: Delegate to AsyncStream

```swift
// Before: Delegate callbacks
protocol DownloadDelegate: AnyObject {
    func downloadDidProgress(_ progress: Double)
    func downloadDidComplete(with data: Data)
    func downloadDidFail(with error: Error)
}

// After: AsyncStream
struct DownloadEvent: Sendable {
    enum Kind: Sendable {
        case progress(Double)
        case complete(Data)
        case failed(Error)
    }
    let kind: Kind
}

func download(url: URL) -> AsyncStream<DownloadEvent> {
    AsyncStream { continuation in
        let task = URLSession.shared.downloadTask(with: url)
        // Set up observation for progress, completion, failure
        // Yield events via continuation
        continuation.onTermination = { _ in task.cancel() }
        task.resume()
    }
}
```

---

## Concurrency-Safe Notifications (iOS 26+)

iOS 26 / macOS 26 introduces concurrency-safe notification patterns to replace `NotificationCenter.addObserver` callback-based APIs.

### MainActorMessage

For notifications that must be received on the main actor (common for UI updates):

```swift
// Define a notification type
struct DataDidChange: MainActorMessage {
    let updatedIDs: [String]
}

// Post from anywhere
MessageCenter.default.post(DataDidChange(updatedIDs: ["1", "2"]))

// Observe — guaranteed @MainActor delivery
func observeChanges() {
    MessageCenter.default.addObserver(of: DataDidChange.self) { message in
        // Runs on @MainActor — safe to update UI
        refreshUI(for: message.updatedIDs)
    }
}
```

### AsyncMessage

For notifications consumed in async contexts without specific actor isolation:

```swift
struct SyncCompleted: AsyncMessage {
    let itemCount: Int
}

// Consume with for-await
func monitorSync() async {
    for await message in MessageCenter.default.messages(of: SyncCompleted.self) {
        log("Synced \(message.itemCount) items")
    }
}
```

### Key differences from NotificationCenter

| NotificationCenter | MessageCenter |
|---|---|
| Stringly-typed names | Protocol-typed messages |
| `userInfo: [AnyHashable: Any]?` | Strongly-typed message struct |
| No isolation guarantees | `MainActorMessage` or `AsyncMessage` |
| Must manually `removeObserver` | Structured lifetime with `for await` |
| Bridged from Objective-C | Swift-native, Sendable by design |

### Migration from NotificationCenter

```swift
// Before
NotificationCenter.default.addObserver(
    self,
    selector: #selector(handleDidSave),
    name: .NSManagedObjectContextDidSave,
    object: nil
)

// After (iOS 26+): Define a typed message and post from save logic
// Or use the async sequence API on NotificationCenter as a bridge:
for await notification in NotificationCenter.default.notifications(named: .NSManagedObjectContextDidSave) {
    await handleDidSave(notification)
}
```

---

## Anti-Patterns

### Wrapping everything in Task { }

```swift
// ❌ Creating unnecessary tasks
@MainActor
func setupUI() {
    Task {
        label.text = "Hello"  // This is already on @MainActor — no Task needed
    }
}

// ✅ Just do it directly
@MainActor
func setupUI() {
    label.text = "Hello"
}
```

### Using @unchecked Sendable as a first resort

```swift
// ❌ Hiding the problem
class MyManager: @unchecked Sendable {
    var state: [String: Any] = [:]  // ← Still a data race!
}

// ✅ Fix the actual problem
actor MyManager {
    var state: [String: Any] = [:]  // Protected by actor isolation
}
```

### Semaphores in async contexts

```swift
// ❌ Blocks a cooperative thread — can deadlock
func fetchSync() -> Data {
    let semaphore = DispatchSemaphore(value: 0)
    var result: Data?
    Task {
        result = await fetchData()
        semaphore.signal()
    }
    semaphore.wait()  // NEVER do this in async context
    return result!
}
```

### Making everything nonisolated to silence warnings

```swift
// ❌ Removing safety to silence the compiler
@MainActor
class ViewModel {
    nonisolated var items: [Item] {
        get { _items }  // ← Data race! Removed main actor protection
        set { _items = newValue }
    }
}
```

### Detached tasks to avoid Sendable errors

```swift
// ❌ Using Task.detached to avoid sending values across isolation
Task.detached {
    // Now nothing is inherited — but you lost actor context and priority
    await self.doWork()
}

// ✅ Fix the Sendable conformance or use proper isolation
Task {
    await self.doWork()  // Fix the type to be Sendable instead
}
```

---

## Common Challenges

### Challenge: Third-party SDK not Sendable-annotated

**Symptom**: Sendable warnings when using types from a library you don't control.

**Solution**: `@preconcurrency import` and file a request with the library maintainer.

```swift
@preconcurrency import ThirdPartySDK
// TODO: Remove @preconcurrency when ThirdPartySDK adds Sendable conformances
```

### Challenge: UIKit delegate methods and actor isolation

**Symptom**: `@MainActor` class conforming to delegate protocols gets isolation errors.

**Solution**: Use `@preconcurrency` conformance or check if the protocol has been updated.

```swift
@MainActor
class MyController: UIViewController, @preconcurrency UITableViewDelegate {
    func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        // Safe — UIKit calls this on main thread
    }
}
```

### Challenge: Thousands of warnings after enabling strict concurrency

**Symptom**: `StrictConcurrency=complete` produces overwhelming diagnostics.

**Solution**: Do NOT try to fix them all at once.

1. Start with `targeted` instead of `complete`.
2. Fix one module at a time, leaf modules first.
3. Use `@preconcurrency import` at module boundaries.
4. Track progress: `swift build 2>&1 | grep -c 'warning:'`

### Challenge: Tests fail after adding actor isolation

**Symptom**: Tests that passed before now fail or deadlock.

**Solution**: Ensure test methods are `async` and properly `await` actor-isolated calls. In XCTest, mark test methods `@MainActor` if they test main-actor-isolated code.

```swift
// XCTest
@MainActor
func testViewModel() async {
    let vm = ViewModel()
    await vm.load()
    XCTAssertFalse(vm.items.isEmpty)
}

// Swift Testing
@Test @MainActor
func viewModelLoads() async {
    let vm = ViewModel()
    await vm.load()
    #expect(!vm.items.isEmpty)
}
```

### Challenge: Bridging sync and async code

**Symptom**: You need to call an async function from a synchronous context.

**Solution**: Use `Task { }` as the bridge, but understand you cannot get the result synchronously.

```swift
// ✅ Fire-and-forget from sync context
@MainActor
func viewDidLoad() {
    super.viewDidLoad()
    Task {
        await loadData()
    }
}

// ❌ There is no safe way to synchronously wait for an async result
// Do not use semaphores, RunLoop spinning, or other blocking mechanisms
```

---

## Common Agent Mistakes

These are mistakes that AI assistants (including this one) frequently make when helping with Swift Concurrency migration. Be aware of them:

### 1. Suggesting @MainActor for everything

Not all code is UI-bound. Adding `@MainActor` to a data processing layer or networking module is wrong — it forces all work onto the main thread.

**Correct approach**: Only use `@MainActor` for code that genuinely owns or updates UI state.

### 2. Recommending @unchecked Sendable without justification

`@unchecked Sendable` silences the compiler but does not fix the data race. It should only be used when you can prove thread safety through other means (e.g., internal locking, immutability after initialization).

**Correct approach**: Fix the underlying issue — make properties immutable, use an actor, or restructure the type.

### 3. Adding nonisolated to silence isolation errors

Marking something `nonisolated` removes its actor protection. If the property or method actually needs to be accessed from a specific actor, removing isolation creates a data race.

**Correct approach**: Determine whether the code is correctly isolated. If it is, fix the caller instead.

### 4. Ignoring project settings

Giving Swift 6 advice to a project in Swift 5 mode with no strict concurrency checking produces confusion. The diagnostics and available fixes differ based on language mode and strict concurrency level.

**Correct approach**: Always check `Package.swift` or build settings first.

### 5. Using Task.detached when Task { } suffices

`Task.detached` discards actor isolation, priority, and task-local values. It is rarely needed.

**Correct approach**: Use `Task { }` which inherits context. Use `Task { @concurrent in }` for background work. Reserve `Task.detached` for when you explicitly need no inherited context.

### 6. Suggesting semaphores or blocking waits in async contexts

Blocking a cooperative thread can deadlock the entire concurrency runtime.

**Correct approach**: Restructure the code to be fully async, or use continuations to bridge callback APIs.

### 7. Not recognizing Swift 6.2 features

Suggesting `nonisolated(nonsending)` annotations when `NonisolatedNonsendingByDefault` is already enabled (redundant), or not suggesting `@concurrent` when it is the correct tool.

**Correct approach**: Check for upcoming feature flags and language version before suggesting annotations.

### 8. Over-migrating stable Combine code

Working Combine pipelines do not need to be rewritten just because async/await exists. Migrate when there is a concrete benefit (simplification, fixing concurrency warnings, or removing a dependency).

**Correct approach**: Migrate Combine code when it is causing concurrency diagnostics or when you are already modifying that code for other reasons.
