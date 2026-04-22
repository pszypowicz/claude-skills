# Actors

> **Use this when:** You need to protect shared mutable state, understand @MainActor, work with actor isolation, or choose between actors and locks.
>
> **Skip this file if:** You need basic async/await syntax (-> [async-await-basics.md](async-await-basics.md)) or Sendable conformance rules (-> [sendable.md](sendable.md)).
>
> **Jump to:** [@MainActor](#global-actors--mainactor) | [Isolated vs Nonisolated](#isolated-vs-nonisolated) | [Reentrancy](#actor-reentrancy) | [#isolation Macro](#isolation-macro) | [Custom Executors](#custom-actor-executors) | [Mutex vs Actor](#mutex-ios-18-vs-actor) | [Decision Tree](#decision-tree)

---

## Actor Isolation Basics

Actors protect their mutable state by ensuring only one task accesses it at a time.

### Defining an actor

```swift
actor BankAccount {
    let accountNumber: String  // let properties are safe to access from outside
    var balance: Double        // var properties are isolated

    init(accountNumber: String, balance: Double) {
        self.accountNumber = accountNumber
        self.balance = balance
    }

    // Methods are isolated by default -- can access balance directly
    func deposit(_ amount: Double) {
        balance += amount
    }

    func withdraw(_ amount: Double) throws {
        guard balance >= amount else {
            throw BankError.insufficientFunds
        }
        balance -= amount
    }
}
```

### Accessing actor-isolated state

```swift
let account = BankAccount(accountNumber: "123", balance: 1000)

// Accessing isolated members requires await
await account.deposit(500)

// let properties don't need await
print(account.accountNumber)  // OK, no await needed

// Accessing var properties from outside requires await
let currentBalance = await account.balance
```

### How actor isolation works

- Each actor has a **serial executor** - a queue that runs one task at a time
- When you `await` an actor method, your task **suspends** until the actor is available
- Inside the actor, code runs synchronously - no data races possible
- Cross-actor calls are always async (require `await`)

---

## Global Actors / @MainActor

A global actor provides a single shared instance that isolates code to a specific executor.

### @MainActor basics

`@MainActor` ensures code runs on the main thread - essential for UI updates.

```swift
// Apply to a class -- all members are main-actor-isolated
@MainActor
class ViewModel: ObservableObject {
    @Published var users: [User] = []
    @Published var isLoading = false

    func loadUsers() async {
        isLoading = true  // safe -- we're on the main actor
        let fetched = await UserService.fetchAll()
        users = fetched   // safe -- still on the main actor
        isLoading = false
    }
}
```

```swift
// Apply to individual members
class DataManager {
    @MainActor var displayName: String = ""

    @MainActor
    func updateUI() {
        // Runs on the main thread
    }

    func fetchData() async -> Data {
        // Not main-actor-isolated -- can run anywhere
        let data = try await URLSession.shared.data(from: url).0
        return data
    }
}
```

### @MainActor replaces DispatchQueue.main

```swift
// BEFORE (GCD)
DispatchQueue.main.async {
    self.label.text = "Updated"
}

// AFTER (Swift Concurrency)
@MainActor
func updateLabel() {
    label.text = "Updated"
}

// Or from an async context:
await MainActor.run {
    label.text = "Updated"
}
```

### MainActor.run

When you need to hop to the main actor from a non-isolated context:

```swift
func processInBackground() async {
    let result = await heavyComputation()

    // Hop to main actor for UI update
    await MainActor.run {
        self.displayResult = result
    }
}
```

### MainActor.assumeIsolated

When you know you're on the main actor but the compiler doesn't:

```swift
// Use when bridging from callback APIs that guarantee main thread
func legacyCallback() {
    // We know this is called on the main thread by the framework
    MainActor.assumeIsolated {
        viewModel.update()  // access @MainActor state without await
    }
}
```

**Warning:** `assumeIsolated` traps at runtime if you're NOT actually on the expected actor. Only use when you have a guarantee from the calling framework.

---

## Isolated vs Nonisolated

### Default isolation

- Inside an `actor`: all stored properties and methods are **isolated** by default
- Inside a `@MainActor class`: all members are **main-actor-isolated** by default

### nonisolated

Opt out of isolation for members that don't access mutable state:

```swift
actor UserCache {
    let maxSize: Int
    var entries: [String: User] = [:]

    // No need for isolation -- only accesses let property
    nonisolated var description: String {
        "UserCache(maxSize: \(maxSize))"
    }

    // Conforming to Hashable -- nonisolated required
    nonisolated func hash(into hasher: inout Hasher) {
        hasher.combine(maxSize)
    }
}
```

### nonisolated for protocol conformance

```swift
actor Player: CustomStringConvertible {
    let id: UUID
    var score: Int

    // CustomStringConvertible requires synchronous access
    // nonisolated means this can't read `score` (isolated var)
    nonisolated var description: String {
        "Player(\(id))"  // OK -- id is let
    }
}
```

---

## Isolated Parameters and Closures

### Isolated parameters (SE-0313)

A function parameter can be marked `isolated` to indicate the function runs on that actor's executor:

```swift
func updateAccount(
    _ account: isolated BankAccount,
    amount: Double
) {
    // No await needed -- we're isolated to this account
    account.balance += amount
}

// Caller must await since it crosses isolation boundary
await updateAccount(account, amount: 100)
```

### Isolated closures

```swift
actor DataStore {
    var items: [Item] = []

    func modify(_ closure: (isolated DataStore) -> Void) {
        closure(self)
    }
}

let store = DataStore()
await store.modify { isolatedStore in
    // Direct access to isolated state
    isolatedStore.items.append(Item())
}
```

---

## Isolated Deinit (Swift 6.2+)

In Swift 6.2+, actor deinits are isolated by default, allowing safe access to the actor's mutable state during deinitialization.

```swift
// Swift 6.2+
actor ResourceManager {
    var handles: [FileHandle] = []

    deinit {
        // Safe -- deinit is isolated to this actor in Swift 6.2+
        for handle in handles {
            handle.closeFile()
        }
        handles.removeAll()
    }
}
```

For `@MainActor` classes:

```swift
@MainActor
class ViewController {
    var observer: NSObjectProtocol?

    deinit {
        // Swift 6.2+: isolated deinit runs on the main actor
        if let observer {
            NotificationCenter.default.removeObserver(observer)
        }
    }
}
```

**Before Swift 6.2**, actor deinits were nonisolated, so accessing mutable state required workarounds.

---

## Global Actor Isolated Conformance (Swift 6.2+)

Swift 6.2 with the `InferIsolatedConformances` upcoming feature flag allows protocol conformances to be implicitly isolated to a global actor.

```swift
// Enable with: -enable-upcoming-feature InferIsolatedConformances

protocol DataSource {
    func numberOfItems() -> Int
    func item(at index: Int) -> Item
}

@MainActor
class MyDataSource: DataSource {
    // These conformances are implicitly @MainActor-isolated
    // No need for nonisolated or async wrappers
    func numberOfItems() -> Int {
        items.count
    }

    func item(at index: Int) -> Item {
        items[index]
    }

    private var items: [Item] = []
}
```

Without `InferIsolatedConformances`, conforming a `@MainActor` class to a synchronous protocol requires marking methods as `nonisolated`, which prevents access to isolated state.

### How it works

The conformance itself becomes isolated:

```swift
@MainActor
class MyVC: UITableViewDataSource {
    // The UITableViewDataSource conformance is @MainActor-isolated
    // These methods can freely access @MainActor state
    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        dataItems.count  // OK -- @MainActor isolated conformance
    }
}
```

---

## Actor Reentrancy

Actors are **reentrant**: when a method suspends at an `await`, other messages can be processed by the actor.

### The problem

```swift
actor ImageCache {
    var cache: [URL: UIImage] = [:]

    func image(for url: URL) async throws -> UIImage {
        if let cached = cache[url] {
            return cached
        }

        // SUSPENSION POINT: another call to image(for:) with the same URL
        // can start executing here, leading to duplicate downloads
        let (data, _) = try await URLSession.shared.data(from: url)
        let image = UIImage(data: data)!

        cache[url] = image
        return image
    }
}
```

### The solution: track in-flight operations

```swift
actor ImageCache {
    var cache: [URL: UIImage] = [:]
    var inFlight: [URL: Task<UIImage, Error>] = [:]

    func image(for url: URL) async throws -> UIImage {
        if let cached = cache[url] {
            return cached
        }

        // If already downloading, wait for the existing task
        if let existing = inFlight[url] {
            return try await existing.value
        }

        // Start a new download task
        let task = Task {
            let (data, _) = try await URLSession.shared.data(from: url)
            return UIImage(data: data)!
        }

        inFlight[url] = task

        do {
            let image = try await task.value
            cache[url] = image
            inFlight[url] = nil
            return image
        } catch {
            inFlight[url] = nil
            throw error
        }
    }
}
```

### Key reentrancy rules

1. **Always check state after an `await`** - it may have changed
2. **Don't assume sequential execution** across suspension points
3. **Track in-flight work** to avoid duplicate operations

---

## #isolation Macro

The `#isolation` macro (SE-0420) captures the current isolation context, enabling you to propagate isolation information into closures and task boundaries.

### Basic usage

```swift
func doWork(isolation: isolated (any Actor)? = #isolation) async {
    // This function inherits the caller's isolation context
    print("Running on: \(String(describing: isolation))")
}

// When called from @MainActor context, runs on MainActor
// When called from another actor, runs on that actor
```

### Task closure capture pattern for non-Sendable types

This is the key pattern from SE-0420 - capturing the caller's isolation in a Task to avoid Sendable requirements:

```swift
@MainActor
class ViewModel {
    var data: [String] = []  // non-Sendable state

    func refresh(isolation: isolated (any Actor)? = #isolation) async {
        // By capturing isolation, the Task inherits the caller's
        // isolation domain, so non-Sendable captures are safe
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in
                // Safe to access self.data here because we're
                // on the same isolation domain
                self.data = await self.fetchData()
            }
        }
    }
}
```

### Propagating isolation through generic functions

```swift
func runOnCallerActor<T>(
    isolation: isolated (any Actor)? = #isolation,
    _ operation: () async throws -> T
) async rethrows -> T {
    try await operation()
}

// Usage from @MainActor context:
@MainActor func updateUI() async {
    await runOnCallerActor {
        // This runs on @MainActor because #isolation captured it
        self.label.text = "Updated"
    }
}
```

### When to use #isolation

- When writing generic utility functions that should run on the caller's actor
- When you need to create Tasks that access non-Sendable state from the caller's context
- When building actor-agnostic APIs that respect the caller's isolation

---

## Custom Actor Executors

Custom executors let you control which thread/queue an actor uses.

### Using a specific dispatch queue

```swift
actor DatabaseActor {
    private let queue = DispatchQueue(label: "database")

    nonisolated var unownedExecutor: UnownedSerialExecutor {
        queue.asUnownedSerialExecutor()
    }

    var connection: DatabaseConnection?

    func query(_ sql: String) async throws -> [Row] {
        // Guaranteed to run on `queue`
        try connection!.execute(sql)
    }
}
```

### Use cases for custom executors

- **Database access**: Pin all DB operations to a single queue
- **Hardware interaction**: Ensure operations run on a specific thread
- **Interop with legacy code**: Match the threading expectations of existing libraries

---

## Mutex (iOS 18+) vs Actor

Starting in iOS 18 / macOS 15, the standard library provides `Mutex` for synchronous mutual exclusion.

### Mutex basics

```swift
import Synchronization

struct Counter: Sendable {
    let value = Mutex(0)

    func increment() {
        value.withLock { $0 += 1 }
    }

    func current() -> Int {
        value.withLock { $0 }
    }
}
```

### When to use Mutex vs Actor

| | Mutex | Actor |
|---|---|---|
| Access pattern | Synchronous only | Async (can suspend) |
| Overhead | Minimal - OS-level lock | Higher - task scheduling |
| Can call async code inside | No | Yes |
| Sendable | Yes (with Sendable contents) | Yes (automatically) |
| Reentrancy | No (deadlock risk) | Yes (by design) |
| Best for | Simple counters, flags, caches | Complex state with async operations |

### Mutex example: thread-safe cache

```swift
final class SimpleCache<Key: Hashable & Sendable, Value: Sendable>: Sendable {
    private let storage = Mutex<[Key: Value]>([:])

    func get(_ key: Key) -> Value? {
        storage.withLock { $0[key] }
    }

    func set(_ key: Key, value: Value) {
        storage.withLock { $0[key] = value }
    }
}
```

### Actor example: cache with async loading

```swift
actor LoadingCache<Key: Hashable & Sendable, Value: Sendable> {
    private var cache: [Key: Value] = [:]
    private var inFlight: [Key: Task<Value, Error>] = [:]

    func get(_ key: Key, loader: @escaping () async throws -> Value) async throws -> Value {
        if let cached = cache[key] { return cached }
        if let task = inFlight[key] { return try await task.value }

        let task = Task { try await loader() }
        inFlight[key] = task

        do {
            let value = try await task.value
            cache[key] = value
            inFlight[key] = nil
            return value
        } catch {
            inFlight[key] = nil
            throw error
        }
    }
}
```

---

## Best Practices

1. **Use @MainActor on ViewModels and UI-related classes** - it replaces `DispatchQueue.main.async`.
2. **Mark entire classes/structs with @MainActor** rather than individual properties when most members need it.
3. **Use `nonisolated`** for computed properties that only access `let` constants.
4. **Be aware of reentrancy** - always check state after suspension points.
5. **Use `assumeIsolated`** carefully - only when the calling framework guarantees the thread.
6. **Prefer Mutex over actors** for simple synchronous state protection (iOS 18+).
7. **Use actors for complex state** that involves async operations.
8. **Track in-flight tasks** to prevent duplicate work in reentrant actors.
9. **Use `#isolation`** in generic utility functions to respect the caller's isolation context.

---

## Decision Tree

```
Need to protect shared mutable state?
|
+-- Only synchronous access needed?
|   +-- iOS 18+ available?
|   |   +-- YES -> Use Mutex
|   |   +-- NO -> Use NSLock / os_unfair_lock wrapped in a Sendable type
|   +-- Need async operations on the state?
|       +-- YES -> Use an actor
|
+-- State is UI-related?
|   +-- YES -> Use @MainActor
|
+-- Need to replace DispatchQueue.main.async?
|   +-- YES -> Use @MainActor or MainActor.run { }
|
+-- Need custom threading (specific queue)?
|   +-- YES -> Use a custom actor executor
|
+-- Global singleton with mutable state?
|   +-- YES -> Use a global actor or actor instance
|
+-- Protocol conformance on @MainActor class? (Swift 6.2+)
|   +-- YES -> Enable InferIsolatedConformances
|
+-- Writing a generic function that should respect caller's isolation?
|   +-- YES -> Use #isolation parameter
```

---

## Further Learning

- [The Swift Programming Language: Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [SE-0306: Actors](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0306-actors.md)
- [SE-0316: Global Actors](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0316-global-actors.md)
- [SE-0313: Improved control over actor isolation](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0313-actor-isolation-control.md)
- [SE-0420: Inheritance of actor isolation](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0420-inheritance-of-actor-isolation.md)
- [SE-0424: Custom actor executors](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0424-custom-isolation-checking-for-serialexecutor.md)
- [Swift Documentation: Mutex](https://developer.apple.com/documentation/synchronization/mutex)
