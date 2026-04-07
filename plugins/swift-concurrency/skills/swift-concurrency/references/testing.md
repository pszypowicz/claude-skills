# Testing Async Code

## Swift Testing Framework (Preferred)

Swift Testing (available from Xcode 16+) is the recommended framework for testing async Swift code. Tests are regular `async` functions decorated with `@Test`.

### Async Test Functions

```swift
import Testing

@Test func fetchUser() async throws {
    let user = try await api.fetchUser(id: 42)
    #expect(user.name == "Alice")
}
```

No special setup needed. The test runner handles the async context.

### #expect and #require

`#expect` is a soft assertion (test continues on failure). `#require` throws on failure, stopping the test:

```swift
@Test func loadItems() async throws {
    let items = try await store.loadItems()

    #expect(items.count > 0)
    #expect(items.first?.isActive == true)

    // #require unwraps or fails the test
    let first = try #require(items.first)
    #expect(first.title == "Welcome")
}
```

Use `#require` when subsequent assertions depend on the unwrapped value.

### Confirmation for Async Events

`confirmation` replaces XCTest expectations. It verifies that a callback or event fires a specific number of times:

```swift
@Test func notificationPosted() async {
    await confirmation("received notification") { confirm in
        let task = Task {
            for await _ in NotificationCenter.default.notifications(named: .dataDidUpdate) {
                confirm()
                break
            }
        }

        NotificationCenter.default.post(name: .dataDidUpdate, object: nil)
        await task.value
    }
}
```

Specify expected count:

```swift
@Test func multipleCallbacks() async {
    await confirmation("callback fired", expectedCount: 3) { confirm in
        await processor.process(items: [1, 2, 3]) { _ in
            confirm()
        }
    }
}
```

### withKnownIssue

Mark tests with known bugs that you haven't fixed yet. The test runs but failure is expected:

```swift
@Test func brokenEndpoint() async throws {
    withKnownIssue("Server returns 500 for this route, tracked in ISSUE-1234") {
        let response = try await api.fetchBroken()
        #expect(response.status == 200)
    }
}
```

If the issue is actually fixed (the test passes), Swift Testing flags it so you can remove the annotation.

---

## XCTest Fallback

For projects that cannot adopt Swift Testing yet, XCTest supports async test methods.

### Async Test Methods

```swift
import XCTest

final class UserServiceTests: XCTestCase {
    func testFetchUser() async throws {
        let service = UserService()
        let user = try await service.fetchUser(id: 42)
        XCTAssertEqual(user.name, "Alice")
    }
}
```

### fulfillment(of:) Replacing waitForExpectations

The modern `fulfillment(of:timeout:)` method is the replacement for the older `waitForExpectations(timeout:)`:

```swift
func testAsyncCallback() async {
    let expectation = expectation(description: "callback received")

    let monitor = EventMonitor()
    monitor.onEvent = { _ in
        expectation.fulfill()
    }
    monitor.start()

    await fulfillment(of: [expectation], timeout: 5.0)
}
```

Key difference: `fulfillment(of:)` is `async` and does not block the cooperative thread pool, unlike the older `wait(for:timeout:)`.

---

## Testing Actors

Actors require `await` for external access. Tests naturally accommodate this:

```swift
actor Counter {
    private var value = 0
    func increment() { value += 1 }
    func current() -> Int { value }
}

@Test func counterIncrements() async {
    let counter = Counter()
    await counter.increment()
    await counter.increment()
    let value = await counter.current()
    #expect(value == 2)
}
```

### Testing Actor State Transitions

When testing sequences of state changes, each access crosses an isolation boundary:

```swift
@Test func orderLifecycle() async throws {
    let manager = OrderManager()

    await manager.placeOrder(item: "Widget")
    #expect(await manager.status == .placed)

    await manager.confirmPayment()
    #expect(await manager.status == .confirmed)

    await manager.ship()
    #expect(await manager.status == .shipped)
}
```

---

## Testing @MainActor Code

### Marking Tests as @MainActor

If the code under test is `@MainActor`, annotate the test:

```swift
@MainActor
@Test func viewModelUpdates() async {
    let vm = DashboardViewModel()
    await vm.refresh()
    #expect(vm.items.count > 0)
}
```

In XCTest:

```swift
@MainActor
final class ViewModelTests: XCTestCase {
    func testRefresh() async {
        let vm = DashboardViewModel()
        await vm.refresh()
        XCTAssertFalse(vm.items.isEmpty)
    }
}
```

### Avoiding MainActor Deadlocks in Tests

If a synchronous test calls `@MainActor` code, you get a deadlock because the test blocks the main thread. Always use `async` test methods when testing `@MainActor`-isolated code.

---

## Flaky Test Fixes

### Race Conditions

Use `Task` + confirmation instead of arbitrary delays:

```swift
// BAD: fragile timing
@Test func badTest() async throws {
    viewModel.startLoading()
    try await Task.sleep(for: .seconds(1)) // hope it's done
    #expect(viewModel.isLoaded)
}

// GOOD: observe the actual state change
@Test func goodTest() async {
    await confirmation("loaded") { confirm in
        let task = Task {
            for await isLoaded in viewModel.$isLoaded.values where isLoaded {
                confirm()
                break
            }
        }
        viewModel.startLoading()
        await task.value
    }
}
```

### Task.yield for Cooperative Scheduling

When testing code that depends on other tasks running:

```swift
@Test func producerConsumer() async {
    let buffer = AsyncBuffer()

    Task { await buffer.produce(value: 42) }

    // Give the producer task a chance to run
    await Task.yield()

    let value = await buffer.consume()
    #expect(value == 42)
}
```

### Timeouts

Swift Testing provides test timeouts via traits:

```swift
@Test(.timeLimit(.seconds(10)))
func slowOperation() async throws {
    let result = try await longRunningTask()
    #expect(result.isValid)
}
```

---

## Memory Management Tests

### Leak Detection Pattern

Verify that objects are deallocated after async work completes:

```swift
@Test func noLeakAfterCancel() async {
    weak var weakRef: MyService?

    do {
        let service = MyService()
        weakRef = service

        let task = Task {
            try await service.start()
        }
        task.cancel()
        try? await task.value
    }

    // Service should be deallocated
    #expect(weakRef == nil)
}
```

### Tracking Allocations in Tests

```swift
@Test func taskGroupCleansUp() async {
    weak var weakItem: WorkItem?

    await withTaskGroup(of: Void.self) { group in
        let item = WorkItem()
        weakItem = item
        group.addTask {
            await item.process()
        }
    }

    #expect(weakItem == nil, "WorkItem should be released after task group completes")
}
```

---

## Deterministic Testing with Swift Concurrency Extras

The [swift-concurrency-extras](https://github.com/pointfreeco/swift-concurrency-extras) library from Point-Free provides tools for making async tests deterministic.

### withMainSerialExecutor

Forces all tasks to run serially, eliminating non-determinism:

```swift
import ConcurrencyExtras

@Test func deterministic() async {
    await withMainSerialExecutor {
        let vm = CounterViewModel()

        // Tasks run in a predictable order
        await vm.increment()
        await vm.increment()

        #expect(vm.count == 2)
    }
}
```

### TestClock (via swift-clocks)

Replace real time with a controllable clock:

```swift
import Clocks

@Test func debounceSearch() async {
    let clock = TestClock()
    let searcher = ArticleSearcher(clock: clock)

    await searcher.updateQuery("swift")

    // Advance time precisely
    await clock.advance(by: .milliseconds(300))

    #expect(searcher.results.count > 0)
}
```

### Benefits of Deterministic Testing

- **No flaky tests**: Timing is fully controlled
- **Fast execution**: No real delays
- **Reproducible failures**: Same input always produces same output
- **CI-friendly**: No sensitivity to machine load or scheduling differences
