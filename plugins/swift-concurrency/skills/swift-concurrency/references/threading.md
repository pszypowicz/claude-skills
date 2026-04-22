# Threading and Execution Model

Use this when:

- You need to understand how Swift Concurrency maps tasks to threads.
- You are debugging unexpected thread behavior or main thread hangs.
- You are migrating from GCD queues to isolation domains.
- You need to understand Swift 6.2 changes to nonisolated async functions.
- You see `Thread.current` errors in async contexts.

Skip this file if:

- You need actor isolation patterns. Use `actors.md`.
- You need Sendable conformance guidance. Use `sendable.md`.
- You need a full migration plan. Use `migration.md`.

Jump to:

- Core Concepts: Tasks vs Threads
- The Cooperative Thread Pool
- Threading Mindset to Isolation Mindset
- Suspension Points and Actor Reentrancy
- Thread Execution Patterns
- Swift 6.2 Changes: Nonisolated Async Functions
- Default Isolation Domain (SE-466)
- Debugging Thread Execution
- Common Misconceptions
- GCD to Isolation Domain Migration Map
- Decision Tree

---

## Core Concepts: Tasks vs Threads

A **task** is a unit of asynchronous work. A **thread** is an OS-level execution resource. Swift Concurrency decouples these:

```
┌──────────────────────────────────────────────┐
│ Tasks (logical work)                         │
│  Task A ─── Task B ─── Task C ─── Task D    │
└──────────┬───────────────────────────────────┘
           │  runtime schedules
┌──────────▼───────────────────────────────────┐
│ Cooperative Thread Pool (physical threads)   │
│  Thread 1 ── Thread 2 ── Thread 3 ── ...    │
│  (count ≈ CPU cores)                         │
└──────────────────────────────────────────────┘
```

Key distinctions:

- **Tasks are cheap** - you can create thousands. Threads are expensive - the pool is fixed.
- **Tasks suspend** at `await` points. The thread is returned to the pool, not blocked.
- **Tasks do not own threads**. A task may resume on a different thread than it suspended on.
- **The main actor has a dedicated thread** (the main thread). All other actors share the cooperative pool.

```swift
// This creates a task, not a thread
Task {
    let data = await fetchData()   // Task suspends here, thread returned to pool
    await process(data)            // May resume on a different thread
}
```

### What the runtime guarantees

- At most one thread per CPU core in the cooperative pool (excluding the main thread).
- Tasks on the same actor execute serially - never concurrently.
- Suspension points are the only places where another task can interleave on the same actor.

### What the runtime does NOT guarantee

- Which thread a task resumes on after `await`.
- That a nonisolated async function runs on any specific thread.
- That `Thread.current` is meaningful inside async functions.

---

## The Cooperative Thread Pool

The cooperative thread pool is sized to the number of CPU cores (typically). Unlike GCD, which can spin up hundreds of threads under contention, the cooperative pool has a hard cap.

```
GCD (unbounded):
  Queue 1 → Thread 1, Thread 2, Thread 3...
  Queue 2 → Thread 4, Thread 5, Thread 6...
  (thread explosion under contention)

Swift Concurrency (bounded):
  All tasks → Thread 1, Thread 2, ..., Thread N  (N ≈ core count)
  (tasks wait in queue, no thread explosion)
```

**Critical rule**: Never block a cooperative thread. Blocking one thread reduces the pool's capacity proportionally. Blocking all threads deadlocks the program.

Things that block a cooperative thread (never do these in async contexts):

- `DispatchSemaphore.wait()`
- `os_unfair_lock_lock()`
- `Thread.sleep(forTimeInterval:)`
- `DispatchQueue.sync` from an async context
- Any synchronous I/O that blocks the calling thread

Use instead:

- `await Task.sleep(for:)` - suspends the task without blocking the thread
- `actor` - serializes access without blocking
- `Mutex` (Swift 6.0+) - synchronous low-level lock that is safe for brief critical sections but must not be held across `await`
- `AsyncStream` - for producer/consumer patterns

---

## Threading Mindset to Isolation Mindset

The GCD mental model focuses on **which thread** code runs on. Swift Concurrency focuses on **which isolation domain** code belongs to.

| GCD Thinking | Isolation Thinking |
|---|---|
| "Run this on the main queue" | "This state is `@MainActor`-isolated" |
| "Dispatch to a background queue" | "This function is `nonisolated` (or `@concurrent`)" |
| "Sync to protect shared state" | "This state lives inside an `actor`" |
| "Which thread am I on?" | "Which isolation domain am I in?" |
| "Thread-safe" | "Sendable across isolation boundaries" |

The shift matters because:

1. **Isolation is checked at compile time.** Thread safety in GCD is a runtime hope.
2. **Isolation is declarative.** You annotate where state lives, not how to move between threads.
3. **The compiler enforces boundaries.** Sending non-Sendable values across isolation domains is a compile error in Swift 6.

```swift
// GCD thinking: "move to background, then back to main"
DispatchQueue.global().async {
    let data = self.processData()
    DispatchQueue.main.async {
        self.updateUI(with: data)  // Hope self is still alive, hope this is right
    }
}

// Isolation thinking: "state belongs to @MainActor, work can be nonisolated"
@MainActor
final class ViewModel {
    var data: [Item] = []

    func load() async {
        data = await Self.fetchAndProcess()  // Returns to main actor automatically
    }

    @concurrent
    private static func fetchAndProcess() async -> [Item] {
        // Runs on cooperative pool - no need to specify a queue
        return try await APIClient.fetch()
    }
}
```

---

## Suspension Points and Actor Reentrancy

Every `await` is a **suspension point** - the task may pause and resume later. Between suspension and resumption, other tasks can run on the same actor. This is actor reentrancy.

```swift
actor BankAccount {
    var balance: Int = 100

    func withdraw(_ amount: Int) async -> Bool {
        guard balance >= amount else { return false }  // Check
        // ⚠️ SUSPENSION POINT - another task could change balance here
        await authorizeTransaction()
        // balance may no longer be >= amount!
        balance -= amount  // ❌ Potential negative balance
        return true
    }
}
```

### Safe patterns for reentrancy

**Pattern 1: Capture state before suspension**

```swift
actor BankAccount {
    var balance: Int = 100

    func withdraw(_ amount: Int) async -> Bool {
        guard balance >= amount else { return false }
        let currentBalance = balance  // Snapshot
        await authorizeTransaction()
        // Re-check after suspension
        guard balance == currentBalance, balance >= amount else { return false }
        balance -= amount
        return true
    }
}
```

**Pattern 2: Perform all state changes before or after suspension, not across**

```swift
actor BankAccount {
    var balance: Int = 100
    private var pendingWithdrawals: Int = 0

    func withdraw(_ amount: Int) async -> Bool {
        guard balance - pendingWithdrawals >= amount else { return false }
        pendingWithdrawals += amount  // Reserve before suspension
        let approved = await authorizeTransaction()
        pendingWithdrawals -= amount
        if approved {
            balance -= amount
            return true
        }
        return false
    }
}
```

**Pattern 3: Use synchronous actor methods where possible**

```swift
actor Counter {
    var count = 0

    // No suspension point - no reentrancy risk
    func increment() {
        count += 1
    }
}
```

### Key rules

- Assume state can change at every `await` inside an actor.
- Minimize the number of `await` calls between state reads and state writes.
- Prefer synchronous actor methods when no suspension is needed.
- Never rely on state remaining unchanged across an `await`.

---

## Thread Execution Patterns

Understanding where code actually runs:

| Code | Runs on |
|---|---|
| `@MainActor` function | Main thread |
| `actor` method | Cooperative pool (serialized per actor instance) |
| `nonisolated` sync function | Caller's thread/isolation (no hop) |
| `nonisolated` async function (pre-6.2) | Cooperative pool (always hops) |
| `nonisolated` async function (6.2+, default) | Caller's isolation (no hop unless `@concurrent`) |
| `@concurrent` async function | Cooperative pool (always hops) |
| `Task { }` | Inherits enclosing isolation |
| `Task.detached { }` | Cooperative pool, no inherited isolation |
| `MainActor.run { }` | Main thread |

### Pre-Swift 6.2 behavior

Before Swift 6.2, nonisolated async functions always hopped to the cooperative thread pool, even when called from the main actor. This caused unnecessary thread hops:

```swift
// Pre-6.2: This function always runs on the cooperative pool
nonisolated func format(_ text: String) async -> String {
    return text.uppercased()
}

@MainActor
func updateUI() async {
    let formatted = await format("hello")
    // ↑ Hops to pool, then hops back to main actor
    // Two unnecessary context switches for a trivial operation
    label.text = formatted
}
```

---

## Swift 6.2 Changes: Nonisolated Async Functions

Swift 6.2 introduces a fundamental change to how nonisolated async functions execute, via SE-0461.

### The problem (pre-6.2)

Nonisolated async functions always ran on the cooperative thread pool. This meant:

1. Unnecessary thread hops when called from an actor.
2. Non-Sendable values could not be passed without compiler errors.
3. Simple helper functions required values to cross isolation boundaries.

### The solution: nonisolated(nonsending)

SE-0461 introduces a new default: nonisolated async functions **inherit the caller's isolation** instead of hopping to the pool.

```swift
// With NonisolatedNonsendingByDefault enabled:

// This function stays on whatever isolation domain the caller is in
nonisolated func format(_ text: String) async -> String {
    return text.uppercased()
}

@MainActor
func updateUI() async {
    let formatted = await format("hello")
    // ↑ No hop - format() runs on the main actor
    // No Sendable requirement for text or return value
    label.text = formatted
}
```

### Enabling the feature

**As an upcoming feature flag (Swift 6.1+):**

SwiftPM:
```swift
.enableUpcomingFeature("NonisolatedNonsendingByDefault")
```

Xcode:
```
SWIFT_UPCOMING_FEATURE_NONISOLATEDNONSENDINGBYDEFAULT = YES
```

**In Swift 6.2+**: This is enabled by default when using the Swift 6.2 language mode.

### @concurrent: Explicit background execution

When you actually need a function to run on the cooperative pool (CPU-heavy work, blocking operations), use `@concurrent`:

```swift
// Explicitly opts into running on the cooperative pool
@concurrent
func processImage(_ data: Data) async -> UIImage {
    // Heavy computation - should not block the main actor
    return UIImage(data: data)!
}

@MainActor
func handleImage() async {
    let image = await processImage(rawData)
    // ↑ Hops to pool for processing, then returns to main actor
    imageView.image = image
}
```

### nonisolated(nonsending): Explicit caller-isolation inheritance

When `NonisolatedNonsendingByDefault` is NOT enabled, you can opt individual functions into the new behavior:

```swift
// Explicitly inherits caller's isolation
nonisolated(nonsending) func validate(_ input: String) async -> Bool {
    // Runs on caller's isolation domain
    return !input.isEmpty
}
```

### When to use @concurrent vs default nonisolated

| Scenario | Use |
|---|---|
| Lightweight helper / formatting / validation | Default `nonisolated` (inherits caller) |
| CPU-intensive computation | `@concurrent` |
| File I/O or network calls (via async APIs) | Default `nonisolated` (the underlying API handles threading) |
| Image/video/audio processing | `@concurrent` |
| Data parsing of large payloads | `@concurrent` |
| Simple data transformation | Default `nonisolated` |

### Migration impact

With `NonisolatedNonsendingByDefault`, many Sendable errors disappear because values no longer cross isolation boundaries:

```swift
// Pre-6.2: Error - NonSendableType crosses isolation boundary
// Post-6.2 with NonisolatedNonsendingByDefault: OK - stays in caller's isolation
nonisolated func process(_ value: NonSendableType) async -> Result {
    return value.transform()
}
```

---

## Default Isolation Domain (SE-466)

SE-0466 allows you to set a **default actor isolation for an entire module**. The most common use: making `@MainActor` the default so that all code is main-actor-isolated unless explicitly opted out.

### Why default to MainActor?

Most app code is UI-related. With `@MainActor` as the default:

- All functions, types, and properties are main-actor-isolated by default.
- You only annotate the exceptions (background work) with `nonisolated` or `@concurrent`.
- Fewer annotations overall - the common case requires no annotation.
- Matches what most developers expect: code runs on the main thread unless told otherwise.

### Configuring in SwiftPM

```swift
// Package.swift
.target(
    name: "MyApp",
    dependencies: [],
    swiftSettings: [
        .defaultIsolation(MainActor.self)
    ]
)
```

### Configuring in Xcode

Build Settings:
```
SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor
```

Or in the Xcode UI: Build Settings > Swift Compiler - Upcoming Features > Default Actor Isolation > `MainActor`.

### How it works

With `@MainActor` default isolation:

```swift
// All of these are implicitly @MainActor:
func updateUI() { ... }
class ViewModel { ... }
struct Helper { ... }

// Opt out explicitly:
nonisolated func pureComputation() -> Int { ... }

@concurrent
func heavyWork() async -> Data { ... }

// Actors are unaffected - they define their own isolation
actor DataStore { ... }
```

### Interaction with NonisolatedNonsendingByDefault

These two features complement each other:

- **SE-466** (default isolation): Makes most code `@MainActor` by default.
- **SE-461** (nonisolated nonsending): Makes `nonisolated` async functions inherit caller isolation.

Together, they mean:
- Most code is `@MainActor` with no annotation.
- `nonisolated` helper functions stay on the caller's isolation (usually main actor).
- Only `@concurrent` functions hop to the background.
- The result: fewer annotations, fewer Sendable errors, and a predictable execution model.

---

## Debugging Thread Execution

### Thread.current is unavailable in Swift 6

In Swift 6 strict concurrency mode, `Thread.current` is unavailable from async contexts. This is intentional - tasks do not own threads, so asking "which thread am I on?" is the wrong question.

```swift
// ❌ Unavailable in async context under Swift 6
func doWork() async {
    print(Thread.current)  // Error: Thread.current is unavailable from async contexts
}
```

### What to use instead

**1. Check isolation, not threads:**

```swift
// Use #isolation to inspect the current isolation domain
func debugIsolation() async {
    MainActor.assertIsolated()  // Crashes if not on main actor
    // or
    MainActor.assumeIsolated { /* ... */ }  // Asserts and runs
}
```

**2. Use Instruments:**

- **Swift Concurrency** instrument: shows task creation, suspension, and resumption.
- **Thread State** trace: shows which tasks run on which threads over time.
- **Swift Actor** instrument: shows actor contention and queue depths.

**3. Use the debugger:**

```
(lldb) language swift task info    # Shows current task state
(lldb) language swift task backtrace  # Task-aware backtrace
```

**4. Dispatch assertions (transitional):**

```swift
// For code migrating from GCD, these still work in sync contexts
dispatchPrecondition(condition: .onQueue(.main))
```

### Diagnosing main thread hangs

If the main actor is blocked, common causes:

1. **Long synchronous work on @MainActor** - move to `@concurrent` async function.
2. **Blocking call in async context** - replace `DispatchSemaphore.wait()` with `await`.
3. **Actor deadlock** - an actor waiting on itself through a re-entrant call chain.
4. **Too many tasks on main actor** - check if work is unnecessarily `@MainActor`-isolated.

---

## Common Misconceptions

### "async means it runs in the background"

No. `async` means the function can suspend. Where it runs depends on its isolation:

```swift
@MainActor
func fetchAndDisplay() async {
    // This entire function runs on the main actor, not the background
    let data = await URLSession.shared.data(from: url)  // Suspends, but resumes on main
    display(data)
}
```

### "Task { } runs in the background"

No. `Task { }` inherits the enclosing isolation:

```swift
@MainActor
func setup() {
    Task {
        // This runs on the main actor - same isolation as setup()
        await loadData()
    }
}

// For actual background work:
@MainActor
func setup() {
    Task { @concurrent in
        // This runs on the cooperative pool
        await processData()
    }
}
```

### "nonisolated means it runs on a background thread"

Not necessarily. `nonisolated` means the function has no specific isolation requirement. In Swift 6.2+ with `NonisolatedNonsendingByDefault`, nonisolated async functions inherit the caller's isolation - they may run on the main actor if called from `@MainActor` code.

### "await always means a thread hop"

No. `await` marks a potential suspension point. The function may not actually suspend (e.g., if the result is already available), and even if it does, it may resume on the same isolation domain.

### "Actors run on dedicated threads"

No. Actors (other than `@MainActor`) share the cooperative thread pool. They guarantee serial access to their state, but they do not own a thread. Different actor methods may execute on different pool threads at different times.

### "Making everything @MainActor fixes all concurrency issues"

It fixes data races for UI state, but it can cause performance problems by running everything on the main thread. CPU-heavy work should use `@concurrent` to run on the pool.

---

## GCD to Isolation Domain Migration Map

| GCD Pattern | Swift Concurrency Equivalent |
|---|---|
| `DispatchQueue.main.async { }` | `Task { @MainActor in }` or `await MainActor.run { }` |
| `DispatchQueue.global().async { }` | `Task { @concurrent in }` or `Task.detached { }` |
| `DispatchQueue(label:).sync { }` | `actor` with synchronous method |
| `DispatchQueue(label:).async { }` | `actor` with method call via `await` |
| Serial queue for state protection | `actor` |
| Concurrent queue with barrier | `actor` (serial by default; for concurrent reads, consider `Mutex` for sync access) |
| `DispatchGroup` | `async let` or `withTaskGroup` |
| `DispatchSemaphore` | `AsyncStream` or actor-based coordination |
| `DispatchWorkItem` with cancel | `Task` with `Task.isCancelled` / `Task.checkCancellation()` |
| `DispatchQueue.concurrentPerform` | `withTaskGroup` |
| `DispatchSource.makeTimerSource` | `AsyncTimerSequence` (from Swift Async Algorithms) or `Task.sleep` in a loop |
| `DispatchQueue.asyncAfter` | `Task.sleep(for:)` then execute |
| `DispatchSpecificKey` | Actor isolation (the concept of "which queue am I on" becomes "which actor am I in") |
| `os_unfair_lock` | `Mutex` (Swift 6.0+) for sync-only critical sections; `actor` for async contexts |

### Patterns that have no direct equivalent

| GCD Pattern | Approach |
|---|---|
| Target queue hierarchy | Compose actors; no direct hierarchy |
| Quality of Service (QoS) classes | `TaskPriority` (`.high`, `.medium`, `.low`, `.background`) |
| `DispatchIO` | Use `FileHandle` async APIs or third-party async I/O |

---

## Decision Tree

```
Where should this code run?
│
├─ Must access UI (UIKit/SwiftUI views, properties)?
│  └─ @MainActor
│
├─ Protects shared mutable state?
│  └─ actor (or @MainActor if the state is UI-owned)
│
├─ Lightweight helper / transformation / validation?
│  ├─ Sync → nonisolated (no annotation needed)
│  └─ Async → nonisolated (inherits caller isolation with 6.2+)
│
├─ CPU-intensive or blocking work?
│  └─ @concurrent async function
│
├─ Need to bridge sync → async?
│  ├─ From @MainActor context → Task { } (inherits main actor)
│  ├─ From nonisolated context → Task { } (inherits nonisolated)
│  └─ Need no inherited context → Task.detached { }
│
└─ Migrating from DispatchQueue?
   ├─ Serial queue → actor
   ├─ Main queue → @MainActor
   ├─ Global/concurrent queue → @concurrent or Task.detached
   └─ Queue-specific sync protection → Mutex (brief) or actor (async)
```

### Choosing between isolation approaches

```
Is the state accessed from multiple isolation domains?
│
├─ No → No special handling needed
│
├─ Yes, and it's UI state
│  └─ @MainActor
│
├─ Yes, and it's non-UI shared state
│  ├─ Needs async access? → actor
│  └─ Sync-only, brief critical section? → Mutex
│
└─ Yes, but it's immutable or a value type
   └─ Make it Sendable (struct, enum, or final class with let properties)
```
