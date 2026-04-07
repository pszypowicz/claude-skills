# Swift Concurrency Reference Index

## Quick Navigation

| File | Covers |
|------|--------|
| [async-await-basics.md](async-await-basics.md) | async/await syntax, async let, URLSession, typed errors, closure migration |
| [tasks.md](tasks.md) | Task lifecycle, cancellation, task groups, .task modifier, structured vs unstructured |
| [actors.md](actors.md) | Actor isolation, @MainActor, reentrancy, #isolation, custom executors, Mutex |
| [sendable.md](sendable.md) | Isolation domains, Sendable conformance, @unchecked Sendable, region-based isolation |
| [threading.md](threading.md) | Thread pools, cooperative threading, main actor scheduling, priority inversion |
| [observable.md](observable.md) | @Observable macro, @MainActor patterns, ObservableObject migration |
| [async-sequences.md](async-sequences.md) | AsyncSequence, AsyncStream, for-await-in, buffering, backpressure |
| [async-algorithms.md](async-algorithms.md) | Swift Async Algorithms package, merge, combineLatest, debounce, throttle |
| [testing.md](testing.md) | Testing async code, Swift Testing framework, mocking actors, test isolation |
| [performance.md](performance.md) | Continuation overhead, actor contention, task creation cost, instruments |
| [memory-management.md](memory-management.md) | Capture semantics in tasks, weak self patterns, task cancellation and leaks |
| [core-data.md](core-data.md) | Core Data + concurrency, NSManagedObjectContext isolation, ModelActor |
| [migration.md](migration.md) | Migrating from GCD/completion handlers, incremental Swift 6 adoption |
| [linting.md](linting.md) | Strict concurrency checking, compiler warnings, common fixes |
| [glossary.md](glossary.md) | Terms and definitions for Swift Concurrency concepts |

---

## Problem Router

**Start here.** Find your problem, jump to the right file.

### "I need to call an async function"
-> [async-await-basics.md](async-await-basics.md)

### "I need to run multiple async operations at the same time"
- **Fixed number of operations, different return types** -> [async-await-basics.md](async-await-basics.md) (async let)
- **Dynamic number of operations, same return type** -> [tasks.md](tasks.md) (TaskGroup)
- **Fire-and-forget side effects** -> [tasks.md](tasks.md) (unstructured Task / detached Task)

### "I'm getting a data race warning / Sendable error"
- **"Capture of non-sendable type"** -> [sendable.md](sendable.md)
- **"Actor-isolated property cannot be referenced from non-isolated context"** -> [actors.md](actors.md)
- **"Global variable is not concurrency-safe"** -> [sendable.md](sendable.md) (global variables section)
- **"Passing closure as a @Sendable parameter"** -> [sendable.md](sendable.md) (@Sendable closures)

### "I need to protect shared mutable state"
- **Shared across async boundaries** -> [actors.md](actors.md)
- **Synchronous-only access, high contention** -> [actors.md](actors.md) (Mutex section)
- **UI state on main thread** -> [actors.md](actors.md) (@MainActor)

### "I need to update the UI from async code"
-> [actors.md](actors.md) (@MainActor) and [observable.md](observable.md) (@Observable patterns)

### "I need to convert a callback/delegate API to async"
-> [async-await-basics.md](async-await-basics.md) (migration from closures) and [migration.md](migration.md)

### "I need to cancel an async operation"
-> [tasks.md](tasks.md) (cancellation section)

### "I need to stream values over time"
-> [async-sequences.md](async-sequences.md)

### "My app is slower after adopting concurrency"
-> [performance.md](performance.md) and [actors.md](actors.md) (reentrancy / contention)

### "I'm migrating to Swift 6 strict concurrency"
-> [migration.md](migration.md) and [linting.md](linting.md)

---

## Further Learning

- [The Swift Programming Language: Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [Swift Evolution Proposals](https://www.swift.org/swift-evolution/) (search for "concurrency", "actor", "sendable", "isolation")
- [Swift Migration Guide](https://www.swift.org/migration/documentation/migrationguide/)
- [WWDC Sessions on Swift Concurrency](https://developer.apple.com/videos/) (search "Swift concurrency")
