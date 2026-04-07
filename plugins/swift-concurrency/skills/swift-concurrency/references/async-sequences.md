# AsyncSequence and AsyncStream

## AsyncSequence Protocol

`AsyncSequence` is the async counterpart of `Sequence`. Each element is produced asynchronously, and iteration uses `for await`.

### Basic Usage

```swift
func printLines(from url: URL) async throws {
    for try await line in url.lines {
        print(line)
    }
}
```

The compiler transforms `for try await` into a while loop calling `next()` on an `AsyncIterator`:

```swift
var iterator = url.lines.makeAsyncIterator()
while let line = try await iterator.next() {
    print(line)
}
```

### Custom AsyncSequence

```swift
struct Counter: AsyncSequence {
    typealias Element = Int
    let limit: Int

    struct AsyncIterator: AsyncIteratorProtocol {
        let limit: Int
        var current = 0

        mutating func next() async -> Int? {
            guard current < limit else { return nil }
            current += 1
            return current
        }
    }

    func makeAsyncIterator() -> AsyncIterator {
        AsyncIterator(limit: limit)
    }
}

for await value in Counter(limit: 5) {
    print(value) // 1, 2, 3, 4, 5
}
```

### Standard Operators

AsyncSequence includes familiar functional operators:

```swift
let values = url.lines
    .filter { !$0.isEmpty }
    .map { $0.uppercased() }
    .prefix(10)

for try await line in values {
    print(line)
}
```

Available operators: `map`, `compactMap`, `flatMap`, `filter`, `prefix`, `prefix(while:)`, `dropFirst`, `drop(while:)`, `reduce`, `contains`, `allSatisfy`, `min`, `max`, `first(where:)`, `collect` (via Array initializer).

### Termination

Iteration ends when:
- The iterator returns `nil`
- The iterator throws an error
- The consumer breaks out of the loop
- The enclosing task is cancelled

```swift
for await value in someAsyncSequence {
    if value > threshold {
        break // iteration stops, resources cleaned up
    }
}
```

---

## AsyncStream

`AsyncStream` bridges callback-based or imperative code into `AsyncSequence` without implementing the full protocol yourself.

### Basic Creation

```swift
let stream = AsyncStream<Int> { continuation in
    for i in 0..<5 {
        continuation.yield(i)
    }
    continuation.finish()
}

for await value in stream {
    print(value)
}
```

### AsyncThrowingStream

When the producer can fail:

```swift
let stream = AsyncThrowingStream<Data, Error> { continuation in
    let task = fetchChunks { chunk in
        continuation.yield(chunk)
    } onComplete: { error in
        if let error {
            continuation.finish(throwing: error)
        } else {
            continuation.finish()
        }
    }
}
```

---

## Bridging Closures to Streams

### Progress + Completion Pattern

```swift
func downloadFile(url: URL) -> AsyncThrowingStream<Double, Error> {
    AsyncThrowingStream { continuation in
        let downloader = FileDownloader(url: url)
        downloader.onProgress = { progress in
            continuation.yield(progress)
        }
        downloader.onComplete = { result in
            switch result {
            case .success:
                continuation.finish()
            case .failure(let error):
                continuation.finish(throwing: error)
            }
        }
        downloader.start()
    }
}

// Usage
for try await progress in downloadFile(url: fileURL) {
    progressBar.value = progress
}
```

### Result-Based Callbacks

```swift
func pollResults() -> AsyncThrowingStream<Result<Item, Error>, Error> {
    AsyncThrowingStream { continuation in
        poller.onResult = { result in
            continuation.yield(result)
        }
        poller.onFinished = {
            continuation.finish()
        }
    }
}
```

---

## Bridging Delegates

### Location Manager Example

```swift
final class AsyncLocationStream: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: AsyncStream<CLLocation>.Continuation?

    var locations: AsyncStream<CLLocation> {
        AsyncStream { continuation in
            self.continuation = continuation
            manager.delegate = self
            manager.startUpdatingLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager,
                         didUpdateLocations locations: [CLLocation]) {
        for location in locations {
            continuation?.yield(location)
        }
    }

    func locationManager(_ manager: CLLocationManager,
                         didFailWithError error: Error) {
        continuation?.finish()
    }
}

// Usage
let locationStream = AsyncLocationStream()
for await location in locationStream.locations {
    print("Lat: \(location.coordinate.latitude)")
}
```

---

## Stream Lifecycle

### Termination Callback

Use `onTermination` to clean up resources when the stream ends (whether by finishing, cancellation, or the consumer stopping iteration):

```swift
let stream = AsyncStream<Event> { continuation in
    let monitor = EventMonitor()
    monitor.start { event in
        continuation.yield(event)
    }

    continuation.onTermination = { termination in
        monitor.stop()
        switch termination {
        case .cancelled:
            print("Stream was cancelled")
        case .finished:
            print("Stream finished normally")
        @unknown default:
            break
        }
    }
}
```

### Cancellation

When the enclosing task is cancelled, the stream terminates and fires `onTermination`:

```swift
let task = Task {
    for await event in eventStream {
        handle(event)
    }
}

// Later:
task.cancel() // triggers onTermination with .cancelled
```

---

## Buffer Policies

AsyncStream buffers elements when the producer is faster than the consumer. Control this with the `bufferingPolicy` parameter:

```swift
// Unlimited buffer (default) - stores all elements, risk of unbounded memory
let stream1 = AsyncStream<Int>(bufferingPolicy: .unbounded) { continuation in
    // ...
}

// Keep the newest N elements, drop older ones
let stream2 = AsyncStream<Int>(bufferingPolicy: .bufferingNewest(10)) { continuation in
    // ...
}

// Keep the oldest N elements, drop newer ones
let stream3 = AsyncStream<Int>(bufferingPolicy: .bufferingOldest(10)) { continuation in
    // ...
}
```

**Choosing a policy:**

| Policy | Use When |
|---|---|
| `.unbounded` | Every element matters and you can guarantee the consumer keeps up |
| `.bufferingNewest(n)` | Only the latest values matter (e.g., UI updates, sensor readings) |
| `.bufferingOldest(n)` | First-in values matter most and you want backpressure-like behavior |

---

## Repeated Async Calls (Unfolding)

Use `AsyncStream.init(unfolding:)` for sequences built from repeated async calls:

```swift
let pages = AsyncStream<Page>(unfolding: {
    await api.fetchNextPage()
})

for await page in pages {
    display(page.items)
}
```

Each call to the closure produces the next element. Return `nil` to end the sequence. This respects task cancellation automatically.

---

## Standard Library Integration

### NotificationCenter

```swift
for await notification in NotificationCenter.default.notifications(named: .NSManagedObjectContextDidSave) {
    guard let context = notification.object as? NSManagedObjectContext else { continue }
    viewContext.mergeChanges(fromContextDidSave: notification)
}
```

### Combine .values

Bridge any Combine publisher to an AsyncSequence:

```swift
let cancellable = publisher
    .values // AsyncPublisher<Publisher>

for await value in publisher.values {
    print(value)
}
```

This works with `@Published` properties too:

```swift
for await name in viewModel.$userName.values {
    nameLabel.text = name
}
```

---

## Limitations

### Single Consumer

An `AsyncStream` can only be iterated by one consumer. Creating multiple `for await` loops on the same stream results in elements being split unpredictably between consumers, not duplicated:

```swift
let stream = makeStream()

// BAD - elements are split between the two loops
Task { for await v in stream { print("A: \(v)") } }
Task { for await v in stream { print("B: \(v)") } }
```

For multi-consumer scenarios, use `AsyncBroadcastSequence` from swift-async-algorithms or create separate streams.

---

## Decision Guide

| Need | Use |
|---|---|
| Transform an existing async sequence | AsyncSequence operators (`.map`, `.filter`, etc.) |
| Bridge callback/delegate-based API | `AsyncStream` or `AsyncThrowingStream` |
| Produce values from repeated async calls | `AsyncStream(unfolding:)` |
| Produce a single async value | Plain `async` function, not a stream |
| Multi-consumer broadcasting | `AsyncChannel` or `AsyncBroadcastSequence` from AsyncAlgorithms |
| Time-based operations (debounce, throttle) | AsyncAlgorithms package |
| Combine existing async sequences | AsyncAlgorithms (`merge`, `zip`, `combineLatest`) |

### When to Use AsyncAlgorithms

Reach for the [swift-async-algorithms](https://github.com/apple/swift-async-algorithms) package when you need:

- **Time-based operators**: `debounce`, `throttle`, `AsyncTimerSequence`
- **Combining sequences**: `merge`, `combineLatest`, `zip`, `chain`
- **Multi-consumer support**: `AsyncChannel`
- **Advanced transformations**: `chunks`, `adjacentPairs`, `removeDuplicates`, `compacted`

These are not available in the standard library and require the package import.
