# Memory Management in Swift Concurrency

## Retain Cycles in Tasks

### Self Capture

Tasks capture references to `self` just like closures. Unstructured tasks (`Task { }`) are the primary risk area because their lifetime is not tied to the enclosing scope.

```swift
class NetworkMonitor {
    var status: ConnectionStatus = .unknown

    func startMonitoring() {
        // This captures a strong reference to self
        Task {
            for await path in NWPathMonitor().paths {
                self.status = path.status // strong capture
            }
        }
    }
}
```

If `NetworkMonitor` is deallocated but the task keeps running, `self` is retained indefinitely by the task.

### Weak Self Patterns

Use `[weak self]` to break the cycle, with a guard to exit early if the object is gone:

```swift
class NetworkMonitor {
    var status: ConnectionStatus = .unknown

    func startMonitoring() {
        Task { [weak self] in
            for await path in NWPathMonitor().paths {
                guard let self else { return }
                self.status = path.status
            }
        }
    }
}
```

### When You Do NOT Need Weak Self

- **Structured tasks** (within `withTaskGroup`, `async let`) - their lifetime is scoped to the enclosing function, so they cannot outlive the caller
- **Short-lived unstructured tasks** that complete before `self` is deallocated (e.g., a one-shot network request)

```swift
// This is fine - task completes quickly, no cycle risk
func fetchData() {
    Task {
        let data = try await api.fetch()
        self.items = data // task ends immediately after
    }
}
```

The risk is with **long-lived** or **infinite** tasks (e.g., `for await` over an unbounded sequence).

---

## Async Sequence Retention

Iterating an `AsyncSequence` in a task keeps the iterator (and anything it captures) alive for the duration of the iteration:

```swift
class ViewModel {
    private var task: Task<Void, Never>?

    func observe() {
        // The task retains self AND the notification iterator
        task = Task {
            for await _ in NotificationCenter.default.notifications(named: .dataChanged) {
                self.refresh()
            }
        }
    }

    func stopObserving() {
        task?.cancel() // breaks the for-await loop, releases the iterator
        task = nil
    }

    deinit {
        task?.cancel()
    }
}
```

If you forget to cancel, the `for await` loop runs forever, retaining both the iterator and any captured references.

---

## Long-Lived Task Cleanup

### Store and Cancel Pattern

Always store references to long-lived tasks and cancel them when the owning object is done:

```swift
class SessionManager {
    private var heartbeatTask: Task<Void, Never>?
    private var eventTask: Task<Void, Never>?

    func start() {
        heartbeatTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                await self?.sendHeartbeat()
            }
        }

        eventTask = Task { [weak self] in
            for await event in eventStream {
                await self?.handle(event)
            }
        }
    }

    func stop() {
        heartbeatTask?.cancel()
        eventTask?.cancel()
        heartbeatTask = nil
        eventTask = nil
    }

    deinit {
        heartbeatTask?.cancel()
        eventTask?.cancel()
    }
}
```

### SwiftUI .task Modifier

In SwiftUI, the `.task` modifier handles cancellation automatically when the view disappears:

```swift
struct ContentView: View {
    @State private var items: [Item] = []

    var body: some View {
        List(items) { item in
            Text(item.name)
        }
        .task {
            // Automatically cancelled when view disappears
            for await items in store.itemStream {
                self.items = items
            }
        }
    }
}
```

No manual cancellation or `[weak self]` needed - the `.task` lifetime is tied to the view.

---

## Isolated Deinit (Swift 6.2+)

Swift 6.2 introduces `isolated deinit`, allowing deinitializers to run on a specific actor's executor. This solves the long-standing problem of needing to access actor-isolated state during cleanup.

```swift
class ResourceOwner: @MainActor {
    var connection: Connection?

    isolated deinit {
        // Runs on MainActor - safe to access MainActor-isolated properties
        connection?.close()
        NotificationCenter.default.post(name: .resourceReleased, object: nil)
    }
}
```

Without `isolated deinit`, accessing isolated state in `deinit` was unsafe because `deinit` runs on an arbitrary thread.

### Actor-Isolated Deinit

```swift
actor CacheManager {
    var entries: [String: CacheEntry] = [:]

    isolated deinit {
        // Runs on the actor's executor
        for entry in entries.values {
            entry.flush()
        }
        entries.removeAll()
    }
}
```

### Pre-6.2 Workaround

Before `isolated deinit`, the pattern was to use a separate cleanup method:

```swift
class ResourceOwner {
    @MainActor var connection: Connection?

    @MainActor func cleanup() {
        connection?.close()
    }

    deinit {
        // Cannot safely access @MainActor properties here
        // Must schedule cleanup differently
        Task { @MainActor [connection] in
            connection?.close()
        }
    }
}
```

This workaround is fragile - the `Task` in `deinit` may run after related objects are already deallocated.

---

## Task Cancellation and Memory

### How Cancellation Releases Memory

When a task is cancelled:

1. `Task.isCancelled` becomes `true`
2. `CancellationError` is thrown at the next suspension point (for `try await`)
3. The task's closure exits, releasing captured references
4. The task's result storage is freed

```swift
let task = Task {
    var buffer = LargeBuffer() // allocated
    for try await chunk in stream {
        buffer.append(chunk)
    }
    return buffer
}

// Later:
task.cancel()
// After cancellation propagates:
// - stream iteration ends
// - buffer is released
// - captured references are freed
```

### Cooperative Cancellation Pitfall

Cancellation is cooperative. If your code never checks for cancellation, resources are never freed:

```swift
// BAD: ignores cancellation, runs forever
Task {
    while true {
        doWork() // synchronous, no suspension point, cancellation never checked
    }
}

// GOOD: check for cancellation explicitly
Task {
    while !Task.isCancelled {
        doWork()
        try Task.checkCancellation() // throws if cancelled
    }
}
```

---

## Common Leak Patterns

### 1. Task Stored in the Object It Captures

```swift
// LEAK: mutual strong reference
class Poller {
    var task: Task<Void, Never>?

    func start() {
        task = Task {
            while true {
                await self.poll() // self -> task -> self
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }
}

// FIX: use weak self
func start() {
    task = Task { [weak self] in
        while let self, !Task.isCancelled {
            await self.poll()
            try? await Task.sleep(for: .seconds(5))
        }
    }
}
```

### 2. AsyncStream Continuation Capturing Self

```swift
// LEAK: continuation closure retains self
class Sensor {
    var stream: AsyncStream<Reading>?

    func start() {
        stream = AsyncStream { continuation in
            self.onReading = { reading in // self captured
                continuation.yield(reading)
            }
        }
    }
}

// FIX: use weak self in the closure
func start() {
    stream = AsyncStream { [weak self] continuation in
        self?.onReading = { reading in
            continuation.yield(reading)
        }
    }
}
```

### 3. Forgotten Task in ViewController/View

```swift
// LEAK: task outlives the view controller
class DetailViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        Task {
            for await update in liveUpdates {
                self.label.text = update // retains VC forever
            }
        }
    }
}

// FIX: store and cancel
class DetailViewController: UIViewController {
    private var updateTask: Task<Void, Never>?

    override func viewDidLoad() {
        super.viewDidLoad()
        updateTask = Task { [weak self] in
            for await update in liveUpdates {
                self?.label.text = update
            }
        }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        updateTask?.cancel()
    }
}
```

### 4. Circular Reference Through Actor

```swift
// LEAK: object and actor reference each other
class Controller {
    let processor = DataProcessor()

    func start() {
        Task {
            await processor.setDelegate(self) // processor -> self
            // self -> processor (property)
        }
    }
}

// FIX: use weak reference in the actor
actor DataProcessor {
    weak var delegate: (any DataDelegate)?

    func setDelegate(_ delegate: any DataDelegate) {
        self.delegate = delegate
    }
}
```

### 5. Detached Tasks Capturing Context

```swift
// RISK: detached tasks have no parent, run independently
func process() {
    Task.detached {
        // This closure's lifetime is completely independent
        // Anything captured here lives until the task completes
        await self.heavyWork() // self retained until heavyWork finishes
    }
}
```

Detached tasks are especially risky because they have no structured parent to cancel them.
