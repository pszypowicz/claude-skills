# Swift Concurrency Performance

## Instruments Workflow

### Swift Concurrency Instrument

Xcode includes a dedicated Swift Concurrency instrument template for profiling async code. To use it:

1. **Product > Profile** (Cmd+I) to build for profiling
2. Choose the **Swift Concurrency** template (or add the instrument to a custom template)
3. Record your app performing the operation you want to analyze

The instrument provides several tracks:

- **Tasks** - shows task creation, suspension, and resumption over time
- **Actors** - shows when actors are executing work and when tasks are queued waiting for access
- **Task Continuations** - visualizes the suspension-to-resumption flow

### Reading Actor Hops

An "actor hop" occurs when execution moves from one isolation domain to another (e.g., from a nonisolated context to a `@MainActor` method). Each hop involves:

1. Suspending the current task
2. Enqueuing work on the target actor
3. Waiting for the actor to become available
4. Resuming on the actor

In Instruments, actor hops appear as gaps between execution intervals. Frequent hops between two actors indicate a design that may benefit from consolidation.

```swift
// Frequent hops between MainActor and a custom actor
// Each await is a potential hop
await mainActorMethod()     // hop to MainActor
await customActor.process() // hop to customActor
await mainActorMethod()     // hop back to MainActor
await customActor.finalize()// hop to customActor again
```

### Task Scheduling

The instrument shows when tasks are **runnable** (ready to execute) vs **running** (actually on a thread). Large gaps between runnable and running indicate thread pool contention - too many tasks competing for the limited number of cooperative threads.

---

## Reducing Suspension Points

Every `await` is a potential suspension point. While suspension enables concurrency, excessive suspension points add overhead:

- Context switching cost
- Cache invalidation
- Scheduling latency

### Batching Work

```swift
// BAD: suspends on every item
for item in items {
    await actor.process(item) // N actor hops
}

// BETTER: batch the work into a single actor access
await actor.processAll(items) // 1 actor hop
```

### Avoiding Unnecessary Isolation Crossings

```swift
// BAD: crosses isolation boundary to read each property
let name = await viewModel.name
let email = await viewModel.email
let avatar = await viewModel.avatar

// BETTER: return a struct in one hop
struct UserSnapshot: Sendable {
    let name: String
    let email: String
    let avatar: URL
}

let snapshot = await viewModel.userSnapshot() // 1 hop
```

---

## Actor Contention Diagnosis

Actor contention occurs when multiple tasks compete for the same actor, causing them to queue up. In Instruments, this appears as tasks waiting in the actor's queue.

### Symptoms

- Tasks spend significant time in "enqueued" state on a specific actor
- Throughput plateaus despite available CPU cores
- UI freezes if `@MainActor` is contended

### Solutions

**Split actors by responsibility:**

```swift
// BAD: one actor does everything
actor AppState {
    var userData: UserData
    var settings: Settings
    var cache: [String: Data]

    func updateUser(...) { ... }
    func updateSettings(...) { ... }
    func cacheData(...) { ... }
}

// BETTER: separate concerns into independent actors
actor UserStore { var userData: UserData }
actor SettingsStore { var settings: Settings }
actor CacheStore { var cache: [String: Data] }
```

**Move computation out of actors:**

```swift
actor ImageProcessor {
    // BAD: heavy computation inside actor, blocks other tasks
    func process(image: CGImage) -> CGImage {
        applyExpensiveFilter(image) // holds the actor for seconds
    }

    // BETTER: only use actor for state, compute outside
    func process(image: CGImage) async -> CGImage {
        let params = self.filterParams // quick actor access
        return await Task.detached {
            applyExpensiveFilter(image, params: params)
        }.value
    }
}
```

**Use nonisolated for read-only computed properties:**

```swift
actor Account {
    let id: UUID          // let properties are implicitly nonisolated
    let createdAt: Date

    nonisolated var displayId: String {
        id.uuidString.prefix(8).description
    }
}
```

---

## Choosing Execution Style

### @concurrent vs nonisolated (Swift 6.2+)

In Swift 6.2, `nonisolated` methods on actors run on the **caller's executor** by default (callee-inherited isolation). This avoids unnecessary hops but means the method does not run concurrently with respect to its enclosing module's isolation.

`@concurrent` explicitly opts into running on the global concurrent executor:

```swift
actor DataProcessor {
    var results: [Result] = []

    // Runs on the caller's executor (may be MainActor)
    nonisolated func format(data: Data) -> String {
        // lightweight, no need for concurrency
        String(data: data, encoding: .utf8) ?? ""
    }

    // Explicitly runs on the concurrent pool
    @concurrent nonisolated func heavyComputation(data: Data) -> ProcessedData {
        // CPU-intensive, should not block caller
        expensiveTransform(data)
    }
}
```

**Guidelines:**
- Use `nonisolated` (default) for lightweight work that benefits from staying on the caller's executor
- Use `@concurrent nonisolated` for CPU-heavy work that should run on the thread pool
- Avoid `@concurrent` for trivial getters - the hop overhead outweighs any benefit

---

## Parallelism Costs: When Parallel Is Slower

Parallel execution is not always faster. The overhead of task creation, scheduling, and synchronization can exceed the work itself.

### Task Group Overhead

```swift
// SLOWER for small items: task creation overhead dominates
await withTaskGroup(of: Int.self) { group in
    for i in 0..<1000 {
        group.addTask { i * 2 } // trivial work, expensive scheduling
    }
    // ...
}

// FASTER: batch small work items
await withTaskGroup(of: [Int].self) { group in
    for chunk in items.chunks(ofCount: 100) {
        group.addTask {
            chunk.map { $0 * 2 } // meaningful batch per task
        }
    }
    // ...
}
```

### Rule of Thumb

Parallelize when each unit of work takes **significantly more** time than task creation overhead (~1-10 microseconds). For sub-microsecond operations, sequential execution wins.

```swift
// Sequential is fine here
let results = items.map { transform($0) }

// Parallel is justified here
let results = await withTaskGroup(of: (Int, ProcessedImage).self) { group in
    for (index, image) in images.enumerated() {
        group.addTask { (index, await processImage(image)) } // ~50ms each
    }
    // collect results...
}
```

### Amdahl's Law in Practice

If 90% of your operation is sequential (e.g., file I/O, database writes), parallelizing the remaining 10% yields minimal speedup. Profile first to find the actual bottleneck.

---

## Benchmarking Async Code

### Using swift-benchmark

```swift
import Benchmark

let benchmarks = {
    Benchmark("Sequential processing") { benchmark in
        for _ in benchmark.scaledIterations {
            await processSequentially(items)
        }
    }

    Benchmark("Parallel processing") { benchmark in
        for _ in benchmark.scaledIterations {
            await processInParallel(items)
        }
    }
}
```

### Manual Measurement

```swift
func measure<T>(_ label: String, operation: () async throws -> T) async rethrows -> T {
    let clock = ContinuousClock()
    let start = clock.now
    let result = try await operation()
    let elapsed = clock.now - start
    print("\(label): \(elapsed)")
    return result
}

let data = await measure("Fetch + Parse") {
    let raw = try await api.fetchData()
    return try parse(raw)
}
```

### Tips for Reliable Benchmarks

- **Warm up** before measuring (first run may involve caches, JIT, etc.)
- **Run multiple iterations** and use median, not mean (outliers from scheduling jitter)
- **Profile on device**, not just Simulator (thread pool sizes differ)
- **Control for background work** - close other apps, use airplane mode for network tests
- **Compare sequential vs parallel** at different data sizes to find the crossover point
- **Use release builds** - debug builds have dramatically different performance characteristics due to runtime checks and lack of optimization
