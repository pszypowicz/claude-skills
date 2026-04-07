# Tasks

> **Use this when:** You need to manage task lifecycle, handle cancellation, use task groups for dynamic concurrency, or understand structured vs unstructured concurrency.
>
> **Skip this file if:** You just need basic async/await syntax (-> [async-await-basics.md](async-await-basics.md)) or need to protect shared state (-> [actors.md](actors.md)).
>
> **Jump to:** [Cancellation](#cancellation) | [Task Groups](#task-groups) | [Structured vs Unstructured](#structured-vs-unstructured-tasks) | [SwiftUI .task](#swiftui-task-modifier) | [Priorities](#task-priorities-and-escalation) | [Timeout Pattern](#timeout-pattern-with-task-groups)

---

## Task Lifecycle and References

A `Task` is the basic unit of concurrency. Every piece of async code runs inside a task.

### Creating a task

```swift
// Unstructured task -- inherits actor context and priority
let task = Task {
    try await fetchData()
}

// Access the result later
let data = try await task.value

// Cancel the task
task.cancel()
```

### Task states

```
Created -> Running -> Suspended -> Running -> ... -> Completed
                                                  -> Cancelled (cooperative)
```

Tasks are **cooperatively cancelled** -- cancelling a task sets a flag, but the task must check for cancellation and respond.

---

## Cancellation

### Checking for cancellation

```swift
func processItems(_ items: [Item]) async throws {
    for item in items {
        // Option 1: Throws CancellationError if cancelled
        try Task.checkCancellation()

        // Option 2: Check the flag manually
        if Task.isCancelled {
            // Clean up resources
            cleanup()
            return
        }

        await process(item)
    }
}
```

### When to use which

| Method | Use when |
|--------|----------|
| `try Task.checkCancellation()` | You want to bail out immediately with CancellationError |
| `Task.isCancelled` | You need to do cleanup before returning, or return a partial result |

### Cancellation propagates to child tasks

```swift
func loadDashboard() async throws -> Dashboard {
    // If this parent task is cancelled, all async let children
    // are automatically cancelled too
    async let user = fetchUser()
    async let posts = fetchPosts()
    async let stats = fetchStats()

    return try await Dashboard(user: user, posts: posts, stats: stats)
}
```

### Cancellation in URLSession

URLSession automatically checks for task cancellation. If the task is cancelled, the network request is cancelled and throws `CancellationError`.

```swift
func fetchData() async throws -> Data {
    // If the enclosing Task is cancelled, this throws CancellationError
    let (data, _) = try await URLSession.shared.data(from: url)
    return data
}
```

### Handling cancellation gracefully

```swift
func fetchWithFallback() async -> User {
    do {
        return try await fetchUser()
    } catch is CancellationError {
        // Task was cancelled -- return cached data instead of propagating
        return cachedUser ?? .guest
    } catch {
        return .guest
    }
}
```

---

## Error Handling

### Errors in tasks

```swift
let task = Task {
    try await riskyOperation()
}

// Option 1: try await -- propagates the error
do {
    let result = try await task.value
} catch {
    print("Task failed: \(error)")
}

// Option 2: task.result gives you a Result<Success, Failure>
let result = await task.result
switch result {
case .success(let value):
    print("Got \(value)")
case .failure(let error):
    print("Failed: \(error)")
}
```

### Error handling in task groups

```swift
// If any child throws, the group cancels remaining children
// and the error propagates
func fetchAll(urls: [URL]) async throws -> [Data] {
    try await withThrowingTaskGroup(of: Data.self) { group in
        for url in urls {
            group.addTask {
                let (data, _) = try await URLSession.shared.data(from: url)
                return data
            }
        }
        var results: [Data] = []
        for try await data in group {
            results.append(data)
        }
        return results
    }
}
```

### Collecting errors instead of failing fast

```swift
func fetchAll(urls: [URL]) async -> [Result<Data, Error>] {
    await withTaskGroup(of: Result<Data, Error>.self) { group in
        for url in urls {
            group.addTask {
                do {
                    let (data, _) = try await URLSession.shared.data(from: url)
                    return .success(data)
                } catch {
                    return .failure(error)
                }
            }
        }
        var results: [Result<Data, Error>] = []
        for await result in group {
            results.append(result)
        }
        return results
    }
}
```

---

## SwiftUI .task Modifier

The `.task` modifier creates a structured task tied to the view's lifetime. When the view disappears, the task is automatically cancelled.

### Basic usage

```swift
struct UserView: View {
    @State private var user: User?

    var body: some View {
        VStack {
            if let user {
                Text(user.name)
            } else {
                ProgressView()
            }
        }
        .task {
            // Automatically cancelled when view disappears
            user = try? await fetchUser()
        }
    }
}
```

### Reacting to value changes with .task(id:)

```swift
struct UserDetailView: View {
    let userID: Int
    @State private var user: User?

    var body: some View {
        VStack {
            // ...
        }
        .task(id: userID) {
            // Cancelled and restarted whenever userID changes
            user = nil
            user = try? await fetchUser(id: userID)
        }
    }
}
```

### Key behaviors

- **Runs on appear**: the task starts when the view appears
- **Cancelled on disappear**: automatic cancellation when the view is removed
- **Inherits @MainActor**: the `.task` closure runs on the main actor by default
- **`.task(id:)`**: restarts the task when the id value changes (cancels the previous run first)

### Anti-pattern: Task { } inside onAppear

```swift
// BAD -- task is NOT cancelled when view disappears
.onAppear {
    Task {
        await loadData()
    }
}

// GOOD -- task is automatically cancelled
.task {
    await loadData()
}
```

---

## Task Groups

### withTaskGroup (non-throwing)

```swift
func generateThumbnails(for images: [UIImage]) async -> [UIImage] {
    await withTaskGroup(of: UIImage.self) { group in
        for image in images {
            group.addTask {
                await image.generateThumbnail()
            }
        }

        var thumbnails: [UIImage] = []
        for await thumbnail in group {
            thumbnails.append(thumbnail)
        }
        return thumbnails
    }
}
```

### withThrowingTaskGroup

```swift
func downloadAll(urls: [URL]) async throws -> [Data] {
    try await withThrowingTaskGroup(of: (Int, Data).self) { group in
        for (index, url) in urls.enumerated() {
            group.addTask {
                let (data, _) = try await URLSession.shared.data(from: url)
                return (index, data)
            }
        }

        var results = Array<Data?>(repeating: nil, count: urls.count)
        for try await (index, data) in group {
            results[index] = data
        }
        return results.compactMap { $0 }
    }
}
```

### Preserving order

Task group results arrive in completion order, not submission order. To preserve order, tag each result with its index:

```swift
try await withThrowingTaskGroup(of: (Int, User).self) { group in
    for (i, id) in userIDs.enumerated() {
        group.addTask {
            let user = try await fetchUser(id: id)
            return (i, user)
        }
    }

    var ordered = Array<User?>(repeating: nil, count: userIDs.count)
    for try await (index, user) in group {
        ordered[index] = user
    }
    return ordered.compactMap { $0 }
}
```

### Limiting concurrency

```swift
func downloadImages(urls: [URL], maxConcurrent: Int = 4) async throws -> [UIImage] {
    try await withThrowingTaskGroup(of: UIImage.self) { group in
        var results: [UIImage] = []
        var iterator = urls.makeIterator()

        // Start initial batch
        for _ in 0..<min(maxConcurrent, urls.count) {
            if let url = iterator.next() {
                group.addTask { try await self.downloadImage(from: url) }
            }
        }

        // As each finishes, start the next
        for try await image in group {
            results.append(image)
            if let url = iterator.next() {
                group.addTask { try await self.downloadImage(from: url) }
            }
        }

        return results
    }
}
```

---

## Discarding Task Groups

When you don't need to collect results from child tasks, use a discarding task group. This avoids memory growth from unconsumed child task results.

```swift
// Available in Swift 5.9+
func startServices() async throws {
    try await withThrowingDiscardingTaskGroup { group in
        group.addTask { try await runWebServer() }
        group.addTask { try await runMetricsCollector() }
        group.addTask { try await runHealthCheck() }
        // Results are discarded -- no need to iterate
        // If any child throws, all others are cancelled
    }
}
```

### When to use discarding task groups

- Long-running services that don't return values
- Fire-and-forget operations where you still want structured cancellation
- Avoiding unbounded memory growth from unconsumed results

---

## Structured vs Unstructured Tasks

### Structured tasks

Structured tasks form a **tree**. Parent tasks wait for child tasks. Cancellation flows down.

```swift
func processOrder() async throws {
    // async let creates structured child tasks
    async let validation = validateOrder()
    async let payment = processPayment()

    let (isValid, receipt) = try await (validation, payment)
    // Both child tasks complete before this scope exits
}

// Task groups are also structured
try await withTaskGroup(of: Void.self) { group in
    group.addTask { await doA() }
    group.addTask { await doB() }
    // Group waits for all children
}
```

**Benefits of structured tasks:**
- Automatic cancellation propagation
- Parent always outlives children
- No task leaks
- Clear ownership hierarchy

### Unstructured tasks

```swift
// Task { } -- unstructured, inherits actor context + priority
let task = Task {
    await doWork()
}
// You must manage cancellation yourself
// task.cancel()
```

### Detached tasks

```swift
// Task.detached -- unstructured, does NOT inherit context or priority
Task.detached(priority: .background) {
    await doExpensiveWork()
}
```

### Comparison table

| Property | Structured (async let, TaskGroup) | Unstructured (Task { }) | Detached (Task.detached) |
|----------|----------------------------------|------------------------|-------------------------|
| Inherits actor isolation | Yes | Yes | **No** |
| Inherits priority | Yes | Yes | **No** (must specify) |
| Cancellation propagation | Automatic (parent -> child) | Manual (you call .cancel()) | Manual |
| Lifetime | Bound to parent scope | Independent | Independent |
| Use case | Default choice | Bridging sync -> async | Background work, no context |

### When to use each

```
Need concurrency?
|
+-- Can you express it with async let or TaskGroup?
|   +-- YES -> Use structured concurrency (preferred)
|   +-- NO -> Do you need to inherit the current actor context?
|       +-- YES -> Use Task { }
|       +-- NO -> Use Task.detached { }
```

---

## Task Priorities and Escalation

### Available priorities

```swift
Task(priority: .high) { ... }
Task(priority: .medium) { ... }      // default
Task(priority: .low) { ... }
Task(priority: .userInitiated) { ... }
Task(priority: .utility) { ... }
Task(priority: .background) { ... }
```

### Priority escalation

When a high-priority task awaits the result of a lower-priority task, the system **escalates** the lower task's priority.

```swift
let backgroundTask = Task(priority: .background) {
    await heavyComputation() // starts at .background
}

Task(priority: .userInitiated) {
    // This await causes backgroundTask to be escalated to .userInitiated
    let result = await backgroundTask.value
}
```

### Priority inheritance in structured concurrency

Child tasks inherit the priority of their parent:

```swift
Task(priority: .high) {
    async let a = work() // inherits .high
    async let b = work() // inherits .high
    return try await (a, b)
}
```

---

## Task.sleep vs Task.yield

### Task.sleep

Suspends the current task for a specified duration. The task does not consume CPU while sleeping. Supports cancellation.

```swift
// Duration-based (preferred, Swift 5.7+)
try await Task.sleep(for: .seconds(2))
try await Task.sleep(for: .milliseconds(500))

// Nanosecond-based (older API)
try await Task.sleep(nanoseconds: 2_000_000_000)

// Sleep checks for cancellation -- throws CancellationError if cancelled
func poll() async throws {
    while !Task.isCancelled {
        try await checkStatus()
        try await Task.sleep(for: .seconds(5))
    }
}
```

### Task.yield

Gives up the current CPU time slice so other tasks can run. Does not wait -- returns immediately if no other tasks need the CPU.

```swift
func processLargeArray(_ items: [Item]) async {
    for (index, item) in items.enumerated() {
        process(item)

        // Periodically yield to avoid hogging the thread
        if index.isMultiple(of: 100) {
            await Task.yield()
        }
    }
}
```

| | `Task.sleep` | `Task.yield` |
|---|---|---|
| Duration | Specified wait time | Returns immediately (or near-immediately) |
| Purpose | Delay execution | Give other tasks a chance to run |
| Cancellation | Throws if cancelled | Does not check cancellation |
| CPU usage | None during sleep | Minimal |

---

## async let vs TaskGroup Comparison

### Use async let when:

- You have a **fixed, small number** of concurrent operations
- Operations return **different types**
- You want **clean, readable syntax**

```swift
async let profile = fetchProfile()
async let friends = fetchFriends()
async let feed = fetchFeed()
let screen = try await HomeScreen(profile: profile, friends: friends, feed: feed)
```

### Use TaskGroup when:

- You have a **dynamic number** of operations (e.g., iterating a collection)
- All operations return the **same type**
- You need to **limit concurrency**
- You need to **process results as they complete**

```swift
try await withThrowingTaskGroup(of: Image.self) { group in
    for url in urls {
        group.addTask { try await downloadImage(url) }
    }
    for try await image in group {
        display(image)  // Process as each completes
    }
}
```

---

## Timeout Pattern with Task Groups

Implement a timeout using a task group with a competing sleep task.

```swift
func withTimeout<T: Sendable>(
    seconds: Double,
    operation: @escaping @Sendable () async throws -> T
) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        // Start the actual operation
        group.addTask {
            try await operation()
        }

        // Start a timeout task
        group.addTask {
            try await Task.sleep(for: .seconds(seconds))
            throw TimeoutError()
        }

        // Return whichever finishes first
        let result = try await group.next()!
        // Cancel the remaining task
        group.cancelAll()
        return result
    }
}

struct TimeoutError: Error {}

// Usage
do {
    let data = try await withTimeout(seconds: 10) {
        try await fetchLargeFile()
    }
} catch is TimeoutError {
    print("Request timed out")
}
```

### Timeout with a fallback value

```swift
func withTimeoutOrDefault<T: Sendable>(
    seconds: Double,
    defaultValue: T,
    operation: @escaping @Sendable () async -> T
) async -> T {
    await withTaskGroup(of: T.self) { group in
        group.addTask {
            await operation()
        }
        group.addTask {
            try? await Task.sleep(for: .seconds(seconds))
            return defaultValue
        }
        let result = await group.next()!
        group.cancelAll()
        return result
    }
}
```

---

## Best Practices

1. **Prefer structured concurrency** (`async let`, `TaskGroup`) over unstructured (`Task { }`).
2. **Always handle cancellation** in long-running tasks.
3. **Use `.task` in SwiftUI** instead of `Task { }` in `onAppear`.
4. **Use `.task(id:)` for reactive data loading** that depends on changing parameters.
5. **Use discarding task groups** for long-running services that don't return values.
6. **Limit concurrency** in task groups when making many network requests.
7. **Tag results with indices** to preserve order in task groups.
8. **Avoid Task.detached** unless you specifically need to drop actor context.
9. **Use `Task.sleep(for:)`** (Duration-based) instead of nanosecond-based sleep.

---

## Decision Tree

```
What kind of concurrent work do you need?
|
+-- One-shot async operation from sync context?
|   +-- Use Task { }
|
+-- Fixed number of parallel operations?
|   +-- Use async let
|
+-- Dynamic number of parallel operations?
|   +-- Need results? -> withTaskGroup / withThrowingTaskGroup
|   +-- No results needed? -> withDiscardingTaskGroup
|
+-- Background work that shouldn't inherit actor context?
|   +-- Use Task.detached { }
|
+-- Need to cancel previous work when input changes? (SwiftUI)
|   +-- Use .task(id: input)
|
+-- Need a timeout on an async operation?
|   +-- Use the task group timeout pattern
|
+-- Need to delay execution?
|   +-- Use Task.sleep(for:)
|
+-- Need to be a good citizen on a shared thread?
|   +-- Use Task.yield() periodically
```

---

## Further Learning

- [The Swift Programming Language: Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [SE-0304: Structured Concurrency](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0304-structured-concurrency.md)
- [SE-0381: DiscardingTaskGroups](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0381-task-group-discard-results.md)
- [Swift Migration Guide: Concurrency](https://www.swift.org/migration/documentation/migrationguide/)
