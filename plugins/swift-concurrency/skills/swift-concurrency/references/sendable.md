# Sendable

> **Use this when:** You're getting Sendable compiler warnings, need to pass data across isolation domains, or need to understand how Swift's concurrency safety model works.
>
> **Skip this file if:** You need to understand actor isolation itself (-> [actors.md](actors.md)) or basic async/await (-> [async-await-basics.md](async-await-basics.md)).
>
> **Jump to:** [Value Types](#value-types) | [Reference Types](#reference-types) | [@Sendable Closures](#sendable-closures) | [@unchecked Sendable](#unchecked-sendable) | [Region-Based Isolation](#region-based-isolation-and-the-sending-keyword) | [Global Variables](#global-variables) | [Decision Tree](#decision-tree)

---

## Isolation Domains

Swift Concurrency divides your program into **isolation domains**. Each domain has exclusive access to its mutable state:

- Each **actor instance** is its own isolation domain
- **@MainActor** is a single global isolation domain (the main thread)
- **Nonisolated async code** is another domain (the concurrent thread pool)

When data crosses a boundary between isolation domains, it must be **Sendable** -- safe to transfer between concurrent contexts without data races.

```
┌─────────────────┐         ┌─────────────────┐
│  @MainActor     │         │  actor MyActor   │
│  (main thread)  │ ──────> │  (serial queue)  │
│                 │ Sendable │                  │
│  UI state       │ required │  business logic  │
└─────────────────┘         └─────────────────┘
         │
         │ Sendable required
         ▼
┌─────────────────┐
│  Nonisolated    │
│  async code     │
│  (thread pool)  │
└─────────────────┘
```

---

## Value Types

### Implicit Sendable conformance

Simple value types are **implicitly Sendable** when all their stored properties are Sendable:

```swift
// Implicitly Sendable -- all properties are Sendable
struct Point {
    var x: Double
    var y: Double
}

// Implicitly Sendable -- Int, String, Bool are all Sendable
struct UserProfile {
    let id: Int
    var name: String
    var isActive: Bool
}

// NOT Sendable -- contains a non-Sendable property
struct Container {
    var object: NSMutableArray  // NSMutableArray is not Sendable
}
```

### Explicit Sendable conformance

You can explicitly declare conformance for documentation or when the compiler can't infer it:

```swift
struct Config: Sendable {
    let apiKey: String
    let timeout: TimeInterval
    let retryCount: Int
}
```

### Enums

Enums are implicitly Sendable when all associated values are Sendable:

```swift
// Implicitly Sendable
enum NetworkResult {
    case success(Data)
    case failure(NetworkError)
    case cancelled
}

// NOT Sendable -- UIImage associated value might not be Sendable
enum ImageResult {
    case loaded(UIImage)  // Depends on platform
    case placeholder
}
```

### Frozen structs and enums

For library authors: `@frozen` types expose their layout to clients. Frozen value types with all-Sendable fields are implicitly Sendable across module boundaries.

```swift
@frozen
public struct APIVersion: Sendable {
    public let major: Int
    public let minor: Int
}
```

### Copy-on-write (COW) safety

Standard library collections (`Array`, `Dictionary`, `Set`) are Sendable when their elements are Sendable. They use COW, which is safe because:

- When you pass an array to another isolation domain, it gets its own copy
- If the original is mutated, COW triggers a copy -- no shared mutable state

```swift
// Sendable -- [String] elements are Sendable
let names: [String] = ["Alice", "Bob"]

// Sendable -- both key and value types are Sendable
let scores: [String: Int] = ["Alice": 100]

// NOT Sendable -- NSObject is not Sendable
let objects: [NSObject] = []
```

---

## Reference Types

Reference types are **not Sendable by default** because multiple isolation domains could hold references to the same instance and mutate it concurrently.

### Making a class Sendable

A class can be Sendable if it meets ALL of these requirements:

1. **`final`** -- no subclasses can break invariants
2. **All stored properties are `let`** -- immutable
3. **All stored properties are Sendable**

```swift
// Sendable -- final, all let, all Sendable property types
final class Endpoint: Sendable {
    let url: URL
    let method: String
    let headers: [String: String]

    init(url: URL, method: String, headers: [String: String]) {
        self.url = url
        self.method = method
        self.headers = headers
    }
}

// NOT Sendable -- has a var property
final class MutableEndpoint {
    let url: URL
    var retryCount: Int = 0  // mutable -- not Sendable
}

// NOT Sendable -- not final
class BaseEndpoint: Sendable {  // WARNING: non-final class
    let url: URL
}
```

### Actor isolation makes classes Sendable

Classes isolated to a global actor are implicitly Sendable because all access is serialized:

```swift
// Implicitly Sendable -- @MainActor serializes all access
@MainActor
class ViewModel: ObservableObject {
    @Published var items: [Item] = []  // var is OK -- protected by @MainActor
    @Published var isLoading = false
}
```

### Actors are always Sendable

```swift
actor DataStore {
    var cache: [String: Data] = [:]  // var is OK -- actor-isolated
}

// Actors are Sendable -- safe to pass references across boundaries
func process(store: DataStore) async {
    await store.save("key", data: someData)
}
```

---

## @Sendable Closures

Closures that cross isolation boundaries must be `@Sendable`. This means everything they capture must be Sendable.

### Where @Sendable is required

```swift
// Task closures are @Sendable
Task {
    // Everything captured here must be Sendable
}

// Task.detached closures are @Sendable
Task.detached {
    // Everything captured here must be Sendable
}

// TaskGroup.addTask closures are @Sendable
group.addTask {
    // Everything captured here must be Sendable
}

// AsyncStream builder is @Sendable
AsyncStream<Int> { continuation in
    // @Sendable closure
}
```

### Common error and fix

```swift
class MyViewController: UIViewController {
    var data: [String] = []

    func loadData() {
        // ERROR: Capture of non-sendable 'self' in @Sendable closure
        Task {
            let fetched = await fetchData()
            self.data = fetched
        }
    }
}

// FIX: Make the class @MainActor
@MainActor
class MyViewController: UIViewController {
    var data: [String] = []

    func loadData() {
        Task {
            let fetched = await fetchData()
            self.data = fetched  // OK -- @MainActor serializes access
        }
    }
}
```

### Explicitly marking closures as @Sendable

```swift
func performAsync(_ operation: @Sendable @escaping () async -> Void) {
    Task {
        await operation()
    }
}
```

---

## @unchecked Sendable

`@unchecked Sendable` tells the compiler "trust me, this is safe" without verifying it. **The compiler performs no checks** -- you are responsible for thread safety.

### Risks

```swift
// DANGEROUS -- compiler trusts you but this is NOT safe
final class BadCache: @unchecked Sendable {
    var items: [String: Any] = [:]  // UNSYNCHRONIZED mutable state

    func get(_ key: String) -> Any? {
        items[key]  // DATA RACE if another thread writes simultaneously
    }
}
```

### When to use @unchecked Sendable

1. **Types with internal synchronization** (locks, queues):

```swift
final class ThreadSafeCache<Key: Hashable, Value>: @unchecked Sendable {
    private var storage: [Key: Value] = [:]
    private let lock = NSLock()

    func get(_ key: Key) -> Value? {
        lock.withLock { storage[key] }
    }

    func set(_ key: Key, value: Value) {
        lock.withLock { storage[key] = value }
    }
}
```

2. **Immutable reference types you don't control** (third-party):

```swift
// Third-party type that is effectively immutable but not marked Sendable
extension ThirdPartyConfig: @unchecked Sendable {}
```

3. **Wrapper types around OS primitives**:

```swift
final class AtomicFlag: @unchecked Sendable {
    private let _value = OSAllocatedUnfairLock(initialState: false)

    var value: Bool {
        get { _value.withLock { $0 } }
        set { _value.withLock { $0 = newValue } }
    }
}
```

### Rules for safe @unchecked Sendable usage

- ALL mutable state must be protected by a lock, queue, or atomic
- Document WHY it's safe in a comment
- Prefer `Mutex` (iOS 18+) or proper actors when possible
- Treat every `@unchecked Sendable` as tech debt to be audited

---

## Region-Based Isolation and the `sending` Keyword

Swift 5.10+ and Swift 6 introduce **region-based isolation** and the `sending` keyword to allow non-Sendable values to cross isolation boundaries safely.

### The sending keyword

`sending` indicates that the caller **gives up access** to the value after passing it. The compiler verifies the value doesn't escape into the caller's isolation domain.

```swift
actor Processor {
    func process(_ item: sending DataBuffer) {
        // item is safely transferred -- caller no longer has access
    }
}

class DataBuffer {  // NOT Sendable
    var bytes: [UInt8] = []
}

@MainActor
func example() async {
    let buffer = DataBuffer()
    buffer.bytes = [1, 2, 3]
    await processor.process(buffer)
    // buffer is now invalid to use here -- it was "sent" away
    // buffer.bytes  // ERROR: use after send
}
```

### Region-based isolation

The compiler tracks which "region" a value belongs to. Values in disconnected regions can be sent across isolation boundaries even if they aren't Sendable.

```swift
// This works because result is in a disconnected region --
// it was created locally and never shared
func createBuffer() -> sending DataBuffer {
    let buffer = DataBuffer()  // created in a local region
    buffer.bytes = [1, 2, 3]
    return buffer  // safe to send -- no other references exist
}

@MainActor
func useBuffer() async {
    let buffer = createBuffer()  // received via sending
    await processor.process(buffer)  // can send it onward
}
```

### sending in function parameters

```swift
func storeInActor(_ value: sending [NSObject]) async {
    await myActor.store(value)
}
```

### Key rules for sending

1. After passing a value as `sending`, the caller cannot use it again
2. The value must be in a **disconnected region** -- no aliases in the caller's isolation domain
3. This enables safe transfer of non-Sendable types without `@unchecked Sendable`

---

## Global Variables

Global variables are problematic because they're accessible from any isolation domain.

### Actor isolation for globals

```swift
// Isolate to @MainActor -- only accessible from main actor
@MainActor
var currentTheme: Theme = .default

// Isolate to a custom global actor
@NetworkActor
var sessionToken: String?
```

### nonisolated(unsafe)

When you need a global variable that the compiler can't verify but you know is safe:

```swift
// nonisolated(unsafe) -- you guarantee thread safety
// Use when the value is set once before any concurrent access
nonisolated(unsafe) var appConfig: AppConfig!

// Set during app launch, before any concurrent access
func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
    appConfig = loadConfig()  // set once, read many times
    return true
}
```

### Common patterns for globals

```swift
// BEST: let constant -- always safe
let apiBaseURL = URL(string: "https://api.example.com")!

// GOOD: Actor-isolated -- compiler-verified safety
@MainActor
var selectedTab: Int = 0

// OK: nonisolated(unsafe) for set-once values
nonisolated(unsafe) var logger: Logger!

// AVOID: Unprotected global var
var cache: [String: Data] = [:]  // DATA RACE
```

---

## Custom Locks + Sendable

When you need synchronous thread-safe access without actors:

### OSAllocatedUnfairLock (iOS 16+)

```swift
final class Counter: Sendable {
    private let _count = OSAllocatedUnfairLock(initialState: 0)

    var count: Int {
        _count.withLock { $0 }
    }

    func increment() {
        _count.withLock { $0 += 1 }
    }
}
```

### Mutex (iOS 18+ / macOS 15+)

```swift
import Synchronization

final class AtomicCounter: Sendable {
    private let _value = Mutex(0)

    var value: Int {
        _value.withLock { $0 }
    }

    func increment() {
        _value.withLock { $0 += 1 }
    }
}
```

### NSLock with @unchecked Sendable

```swift
final class LegacyCounter: @unchecked Sendable {
    private var _count = 0
    private let lock = NSLock()

    var count: Int {
        lock.withLock { _count }
    }

    func increment() {
        lock.withLock { _count += 1 }
    }
}
```

### Comparison

| Mechanism | Sendable | Min OS | Async support | Notes |
|-----------|----------|--------|---------------|-------|
| `Mutex` | Yes (with Sendable content) | iOS 18 | No | Preferred for new code |
| `OSAllocatedUnfairLock` | Yes | iOS 16 | No | Good for iOS 16+ |
| `NSLock` | Requires @unchecked | Any | No | Legacy, but works everywhere |
| Actor | Yes | iOS 13 | Yes | Best for async state |

---

## Common Sendable Errors and Fixes

### "Capture of 'self' with non-sendable type in @Sendable closure"

```swift
// Problem
class NetworkManager {
    func fetch() {
        Task { await self.doWork() }  // ERROR
    }
}

// Fix 1: Make it @MainActor (if UI-related)
@MainActor class NetworkManager { ... }

// Fix 2: Make it an actor (if it has mutable shared state)
actor NetworkManager { ... }

// Fix 3: Make it final + immutable + Sendable
final class NetworkManager: Sendable {
    let session: URLSession
    ...
}
```

### "Static property is not concurrency-safe"

```swift
// Problem
class Theme {
    static var current: Theme = .default  // WARNING
}

// Fix 1: Actor-isolate
class Theme {
    @MainActor static var current: Theme = .default
}

// Fix 2: Make it a let
class Theme {
    static let defaultTheme: Theme = .init()
}
```

### "Conformance to Sendable must be in the same source file"

```swift
// Problem: trying to add Sendable to a type from another module
extension ExternalType: Sendable {}  // ERROR

// Fix: Use @unchecked Sendable if you know it's safe
extension ExternalType: @unchecked Sendable {}
```

---

## Best Practices

1. **Prefer value types** -- they're implicitly Sendable when their properties are.
2. **Use @MainActor for UI classes** -- it makes them implicitly Sendable.
3. **Use actors for complex shared state** -- they're always Sendable.
4. **Avoid @unchecked Sendable** unless you have internal synchronization and document why it's safe.
5. **Use `sending`** to transfer non-Sendable values across isolation boundaries (Swift 6).
6. **Use Mutex** (iOS 18+) for simple synchronous state protection.
7. **Make global variables `let`** whenever possible, or isolate them to a global actor.
8. **Use `nonisolated(unsafe)`** only for set-once globals with a clear initialization order.

---

## Decision Tree

```
Is your type Sendable?
|
+-- Value type (struct/enum)?
|   +-- All stored properties Sendable?
|   |   +-- YES -> Implicitly Sendable (nothing to do)
|   |   +-- NO -> Make non-Sendable properties Sendable, or redesign
|
+-- Reference type (class)?
|   +-- Is it final?
|   |   +-- NO -> Cannot be Sendable (make it final or use actor)
|   |   +-- YES -> Are all stored properties let + Sendable?
|   |       +-- YES -> Conform to Sendable
|   |       +-- NO -> Options:
|   |           +-- Use @MainActor (if UI-related)
|   |           +-- Convert to actor
|   |           +-- Add internal locking + @unchecked Sendable
|
+-- Actor?
|   +-- Always Sendable, nothing to do
|
+-- Need to pass a non-Sendable value across boundaries?
|   +-- Can you use `sending`? (Swift 6)
|   |   +-- YES -> Mark parameter/return as sending
|   |   +-- NO -> Redesign to use Sendable types
|
+-- Global variable?
|   +-- Can it be let?
|   |   +-- YES -> Make it let
|   |   +-- NO -> Isolate to @MainActor or another global actor
|   |       +-- Can't use actor isolation?
|   |           +-- Set once, then read-only? -> nonisolated(unsafe)
|   |           +-- Mutated from multiple contexts? -> Use actor/Mutex
|
+-- Closure crossing isolation boundary?
    +-- All captures Sendable?
    |   +-- YES -> @Sendable automatically satisfied
    |   +-- NO -> Make captured types Sendable, or restructure
    +-- Using Task { }?
        +-- Isolate the enclosing type to an actor
```

---

## Further Learning

- [The Swift Programming Language: Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [SE-0302: Sendable and @Sendable closures](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0302-concurrent-value-and-concurrent-closures.md)
- [SE-0414: Region-based isolation](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0414-region-based-isolation.md)
- [SE-0430: sending parameter and result values](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0430-transferring-parameters-and-results.md)
- [Swift Migration Guide: Data Race Safety](https://www.swift.org/migration/documentation/migrationguide/)
