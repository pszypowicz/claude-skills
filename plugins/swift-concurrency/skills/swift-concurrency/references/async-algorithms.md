# Swift Async Algorithms

The [swift-async-algorithms](https://github.com/apple/swift-async-algorithms) package extends `AsyncSequence` with time-based operators, combining operators, and utilities that mirror familiar patterns from Combine and reactive frameworks.

## Quick Start: Top 5 Operators

| Operator | What It Does | Combine Equivalent |
|---|---|---|
| `debounce(for:)` | Waits for a pause in values before emitting | `debounce(for:scheduler:)` |
| `merge(_:_:)` | Interleaves elements from multiple sequences | `MergeMany` / `merge(with:)` |
| `combineLatest(_:_:)` | Emits a tuple of latest values when any input changes | `combineLatest(_:)` |
| `throttle(for:latest:)` | Rate-limits emissions to a time interval | `throttle(for:scheduler:latest:)` |
| `chunks(ofCount:)` | Groups elements into fixed-size arrays | `collect(_:)` |

---

## Installation

### Swift Package Manager

```swift
// Package.swift
dependencies: [
    .package(url: "https://github.com/apple/swift-async-algorithms", from: "1.0.0")
]

// Target dependency
.product(name: "AsyncAlgorithms", package: "swift-async-algorithms")
```

```swift
import AsyncAlgorithms
```

---

## Time-Based Operators

### debounce — Wait for Input to Settle

Emits a value only after a specified quiet period with no new values. Ideal for search-as-you-type.

```swift
struct ArticleSearcher {
    let searchField: AsyncStream<String>

    func results() async throws -> AsyncStream<[Article]> {
        // Wait 300ms after the user stops typing before searching
        for await query in searchField.debounce(for: .milliseconds(300)) {
            let results = try await api.search(query: query)
            // update UI
        }
    }
}
```

How it works: each new value resets the timer. Only the most recent value is emitted once the timer fires.

```
Input:  H--He--Hel--Hell--Hello------->
                                 |300ms|
Output: ----------------------------Hello-->
```

### throttle — Rate-Limit Emissions

Emits at most one value per time interval. Use for rapid user actions where you want periodic sampling.

```swift
// Like button: accept at most one tap per second
for await _ in likeButtonTaps.throttle(for: .seconds(1), latest: false) {
    await sendLike()
}
```

- `latest: true` — emit the most recent value in each window (default)
- `latest: false` — emit the first value in each window

### AsyncTimerSequence

A repeating timer as an async sequence:

```swift
for await _ in AsyncTimerSequence.repeating(every: .seconds(5)) {
    await refreshDashboard()
}
```

Replaces `Timer.publish(every:on:in:)` from Combine. Respects task cancellation automatically.

---

## Combining Operators

### merge — Interleave Multiple Sequences

Combines elements from multiple sequences into one, preserving arrival order.

```swift
// Multi-room chat: show messages from all rooms in one feed
let allMessages = merge(
    roomA.messages,
    roomB.messages,
    roomC.messages
)

for await message in allMessages {
    displayInFeed(message)
}
```

All input sequences must share the same `Element` type. The merged sequence finishes when all inputs finish.

### combineLatest — React to Any Change

Emits a tuple of the latest values from each input whenever any input produces a new value.

```swift
// Form validation: re-validate whenever any field changes
for await (name, email, password) in combineLatest(
    nameField.values,
    emailField.values,
    passwordField.values
) {
    let isValid = !name.isEmpty && email.contains("@") && password.count >= 8
    submitButton.isEnabled = isValid
}
```

Does not emit until every input has produced at least one value.

### zip — Pair Elements One-to-One

Pairs elements from two sequences by index, waiting for both to produce.

```swift
// Pair requests with responses
for await (request, response) in zip(requests, responses) {
    log("\(request.url) -> \(response.statusCode)")
}
```

The zipped sequence finishes when either input finishes.

### chain — Sequential Concatenation

Consumes the first sequence to completion, then the second:

```swift
// Process cached items first, then live items
for await item in chain(cachedItems, liveItems) {
    process(item)
}
```

---

## Multi-Consumer: AsyncChannel

`AsyncChannel` is a multi-producer, multi-consumer async sequence with built-in backpressure. Unlike `AsyncStream`, multiple consumers can iterate an `AsyncChannel` and each call to `send()` suspends until a consumer receives the value.

```swift
let channel = AsyncChannel<WorkItem>()

// Producer
Task {
    for item in workItems {
        await channel.send(item) // suspends until a consumer is ready
    }
    channel.finish()
}

// Consumer 1
Task {
    for await item in channel {
        await process(item)
    }
}

// Consumer 2
Task {
    for await item in channel {
        await process(item)
    }
}
```

**Key differences from AsyncStream:**
- `send()` is `async` and applies backpressure (suspends until consumed)
- Multiple consumers each get distinct elements (work distribution, not broadcasting)
- No buffering policy needed — backpressure handles flow control

---

## Utility Operators

### removeDuplicates

Suppresses consecutive duplicate values:

```swift
for await status in connectionStatus.removeDuplicates() {
    updateStatusIcon(status)
}
```

Custom predicate version:

```swift
for await location in locations.removeDuplicates {
    $0.distance(from: $1) < 10 // ignore moves under 10 meters
}
```

### chunks

Group elements into batches:

```swift
// Batch by count
for await batch in events.chunks(ofCount: 50) {
    await api.uploadBatch(batch) // [Event], up to 50 elements
}

// Batch by time
for await batch in events.chunked(by: .repeating(every: .seconds(1))) {
    processBatch(batch)
}
```

### adjacentPairs

Emit consecutive pairs:

```swift
for await (previous, current) in sensorReadings.adjacentPairs() {
    let delta = current.value - previous.value
    if abs(delta) > threshold {
        triggerAlert(delta: delta)
    }
}
```

### compacted

Remove nil values (like `compactMap { $0 }` but cleaner):

```swift
let validReadings = sensorStream.compacted()
// AsyncSequence<Optional<Reading>> -> AsyncSequence<Reading>
```

---

## Combine Migration Guide

| Combine | AsyncAlgorithms | Notes |
|---|---|---|
| `sink { }` | `for await value in seq { }` | Task-based iteration |
| `map { }` | `.map { }` | Built into AsyncSequence |
| `compactMap { }` | `.compactMap { }` | Built into AsyncSequence |
| `filter { }` | `.filter { }` | Built into AsyncSequence |
| `first(where:)` | `.first(where:)` | Built into AsyncSequence |
| `prefix(_:)` | `.prefix(_:)` | Built into AsyncSequence |
| `dropFirst(_:)` | `.dropFirst(_:)` | Built into AsyncSequence |
| `removeDuplicates()` | `.removeDuplicates()` | AsyncAlgorithms |
| `debounce(for:scheduler:)` | `.debounce(for:)` | AsyncAlgorithms, clock-based |
| `throttle(for:scheduler:latest:)` | `.throttle(for:latest:)` | AsyncAlgorithms, clock-based |
| `merge(with:)` | `merge(_:_:)` | Free function, not method |
| `combineLatest(_:)` | `combineLatest(_:_:)` | Free function, not method |
| `zip(_:)` | `zip(_:_:)` | Free function, not method |
| `collect(_:)` | `.chunks(ofCount:)` | AsyncAlgorithms |
| `Timer.publish(every:)` | `AsyncTimerSequence.repeating(every:)` | AsyncAlgorithms |
| `PassthroughSubject` | `AsyncChannel` | With backpressure |
| `CurrentValueSubject` | No direct equivalent | Use an actor with a stream |
| `@Published` | `.values` on `@Published` | Built into Combine/AsyncSequence bridge |
| `cancel()` | `task.cancel()` | Cancellation is cooperative |
