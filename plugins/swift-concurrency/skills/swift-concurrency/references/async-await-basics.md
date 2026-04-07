# Async/Await Basics

> **Use this when:** You need to write or call asynchronous functions, fetch data from the network, run parallel async operations, or convert callback-based APIs.
>
> **Skip this file if:** You already understand async/await and need help with task lifecycle (-> [tasks.md](tasks.md)), shared state protection (-> [actors.md](actors.md)), or Sendable conformance (-> [sendable.md](sendable.md)).
>
> **Jump to:** [async let](#async-let-parallel-execution) | [URLSession patterns](#urlsession-patterns) | [Typed errors](#typed-errors-swift-6) | [Migration from closures](#migration-from-closures)

---

## async/await Syntax

### Declaring an async function

```swift
func fetchUser(id: Int) async throws -> User {
    let url = URL(string: "https://api.example.com/users/\(id)")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONDecoder().decode(User.self, from: data)
}
```

Key rules:
- `async` comes before `throws` in the declaration: `async throws`
- `await` comes before `try` at the call site: `try await`
- Every `await` is a **suspension point** -- the function may pause and resume on a different thread
- An async function can only be called from another async context

### Calling async functions

```swift
// From another async function
func loadProfile() async throws -> Profile {
    let user = try await fetchUser(id: 42)
    let avatar = try await fetchAvatar(for: user)
    return Profile(user: user, avatar: avatar)
}

// From synchronous code -- you need a Task
Task {
    do {
        let profile = try await loadProfile()
        // use profile
    } catch {
        // handle error
    }
}
```

### Computed properties can be async

```swift
extension User {
    var profileImageURL: URL {
        get async throws {
            let config = try await fetchConfig()
            return config.cdnBase.appendingPathComponent(avatarPath)
        }
    }
}

// Usage
let url = try await user.profileImageURL
```

### Subscripts can be async (read-only)

```swift
struct RemoteCollection {
    subscript(index: Int) -> Item {
        get async throws {
            try await fetchItem(at: index)
        }
    }
}
```

---

## Execution Order

Async/await is **sequential by default**. Each `await` completes before the next line runs.

```swift
func loadDashboard() async throws -> Dashboard {
    // These run ONE AT A TIME, sequentially:
    let user = try await fetchUser()          // 1st
    let posts = try await fetchPosts()        // 2nd (waits for 1st)
    let notifications = try await fetchNotifications() // 3rd (waits for 2nd)
    return Dashboard(user: user, posts: posts, notifications: notifications)
}
```

This is often **unnecessarily slow**. If the operations are independent, use `async let` for parallelism.

---

## async let (Parallel Execution)

`async let` starts a child task immediately and lets you await the result later.

```swift
func loadDashboard() async throws -> Dashboard {
    // All three start concurrently:
    async let user = fetchUser()
    async let posts = fetchPosts()
    async let notifications = fetchNotifications()

    // Await all results (order doesn't matter):
    return try await Dashboard(
        user: user,
        posts: posts,
        notifications: notifications
    )
}
```

### Rules for async let

1. **Implicit await at scope exit.** If you don't explicitly `await` an `async let`, it is implicitly awaited (and cancelled) when the scope exits.
2. **Cancellation on throw.** If one `async let` throws, the other in-flight child tasks are automatically cancelled.
3. **Structured concurrency.** `async let` creates child tasks that are bound to the parent scope.

```swift
func fetchFirstAvailable() async throws -> Data {
    async let a = fetchFromServerA()
    async let b = fetchFromServerB()

    // If a succeeds, b is cancelled when this scope exits
    // If a throws, b is also cancelled
    return try await a
    // b is implicitly cancelled and awaited here
}
```

### async let vs TaskGroup

| | `async let` | `TaskGroup` |
|---|---|---|
| Number of tasks | Fixed, known at compile time | Dynamic, determined at runtime |
| Return types | Can differ per binding | Must be the same type |
| Syntax | Lightweight | More verbose |
| Use case | 2-5 independent calls | Collections, fan-out |

```swift
// async let -- fixed number, different types
async let name = fetchName()
async let avatar = fetchAvatar()
let header = try await Header(name: name, avatar: avatar)

// TaskGroup -- dynamic number, same type
let images = try await withThrowingTaskGroup(of: UIImage.self) { group in
    for url in imageURLs {
        group.addTask { try await downloadImage(from: url) }
    }
    var results: [UIImage] = []
    for try await image in group {
        results.append(image)
    }
    return results
}
```

---

## URLSession Patterns

### Basic data fetch

```swift
func fetchJSON<T: Decodable>(_ type: T.Type, from url: URL) async throws -> T {
    let (data, response) = try await URLSession.shared.data(from: url)

    guard let httpResponse = response as? HTTPURLResponse,
          (200...299).contains(httpResponse.statusCode) else {
        throw NetworkError.invalidResponse
    }

    return try JSONDecoder().decode(T.self, from: data)
}
```

### Download with progress (AsyncSequence of bytes)

```swift
func download(from url: URL) async throws -> Data {
    let (bytes, response) = try await URLSession.shared.bytes(from: url)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 200 else {
        throw NetworkError.invalidResponse
    }

    let totalBytes = Int(httpResponse.expectedContentLength)
    var data = Data(capacity: totalBytes)

    for try await byte in bytes {
        data.append(byte)
        // Update progress
        let progress = Double(data.count) / Double(totalBytes)
        await updateProgress(progress)
    }

    return data
}
```

### POST request

```swift
func createUser(_ user: NewUser) async throws -> User {
    var request = URLRequest(url: URL(string: "https://api.example.com/users")!)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONEncoder().encode(user)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 201 else {
        throw NetworkError.invalidResponse
    }

    return try JSONDecoder().decode(User.self, from: data)
}
```

### Parallel fetches with error handling

```swift
func fetchAllUsers(ids: [Int]) async throws -> [User] {
    try await withThrowingTaskGroup(of: User.self) { group in
        for id in ids {
            group.addTask {
                try await self.fetchUser(id: id)
            }
        }

        var users: [User] = []
        for try await user in group {
            users.append(user)
        }
        return users
    }
}
```

---

## Typed Errors (Swift 6)

Swift 6 introduces typed throws, allowing you to specify the exact error type an async function can throw.

### Syntax

```swift
// Before Swift 6 -- throws any Error
func fetchUser() async throws -> User { ... }

// Swift 6 -- typed throws
func fetchUser() async throws(NetworkError) -> User {
    let (data, response) = try await URLSession.shared.data(from: url)
    guard let http = response as? HTTPURLResponse else {
        throw NetworkError.invalidResponse
    }
    guard http.statusCode == 200 else {
        throw NetworkError.httpError(http.statusCode)
    }
    do {
        return try JSONDecoder().decode(User.self, from: data)
    } catch {
        throw NetworkError.decodingFailed(error)
    }
}
```

### Benefits

```swift
enum NetworkError: Error {
    case invalidResponse
    case httpError(Int)
    case decodingFailed(Error)
}

// Caller gets exhaustive switch -- no default needed
func loadUser() async {
    do {
        let user = try await fetchUser()
    } catch {
        // error is NetworkError, not any Error
        switch error {
        case .invalidResponse:
            showOfflineMessage()
        case .httpError(let code):
            showHTTPError(code)
        case .decodingFailed(let underlying):
            logDecodingError(underlying)
        }
        // No default case needed -- exhaustive
    }
}
```

### throws(Never) -- non-throwing async

```swift
// Explicitly non-throwing async function
func cachedUser() async throws(Never) -> User {
    await cache.get("user") ?? User.guest
}

// Can be called without try
let user = await cachedUser()
```

---

## Migration from Closures

### Pattern: Wrapping a completion handler with a continuation

```swift
// BEFORE: callback-based
func fetchData(completion: @escaping (Result<Data, Error>) -> Void) {
    URLSession.shared.dataTask(with: url) { data, response, error in
        if let error {
            completion(.failure(error))
        } else if let data {
            completion(.success(data))
        }
    }.resume()
}

// AFTER: async wrapper using withCheckedThrowingContinuation
func fetchData() async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        fetchData { result in
            continuation.resume(with: result)
        }
    }
}
```

### Continuation types

| Function | Throws | Checks |
|----------|--------|--------|
| `withCheckedContinuation` | No | Yes (crashes on misuse in debug) |
| `withCheckedThrowingContinuation` | Yes | Yes |
| `withUnsafeContinuation` | No | No (undefined behavior on misuse) |
| `withUnsafeThrowingContinuation` | Yes | No |

**Always use `withChecked...` during development.** Switch to `withUnsafe...` only after thorough testing if you need to eliminate the runtime check overhead.

### Critical rules for continuations

```swift
// A continuation MUST be resumed EXACTLY once.

// WRONG -- might never resume (leaks the task forever)
func bad() async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        fetchData { result in
            if case .success(let data) = result {
                continuation.resume(returning: data)
            }
            // BUG: .failure case never resumes the continuation
        }
    }
}

// CORRECT -- always resumes
func good() async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        fetchData { result in
            switch result {
            case .success(let data):
                continuation.resume(returning: data)
            case .failure(let error):
                continuation.resume(throwing: error)
            }
        }
    }
}
```

### Wrapping a delegate-based API

```swift
class LocationFetcher: NSObject, CLLocationManagerDelegate {
    private var continuation: CheckedContinuation<CLLocation, Error>?
    private let manager = CLLocationManager()

    func currentLocation() async throws -> CLLocation {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            manager.delegate = self
            manager.requestLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        continuation?.resume(returning: locations.first!)
        continuation = nil
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}
```

---

## Common Patterns

### Retry with exponential backoff

```swift
func withRetry<T>(
    maxAttempts: Int = 3,
    initialDelay: Duration = .seconds(1),
    operation: () async throws -> T
) async throws -> T {
    var delay = initialDelay
    for attempt in 1...maxAttempts {
        do {
            return try await operation()
        } catch {
            if attempt == maxAttempts { throw error }
            try await Task.sleep(for: delay)
            delay *= 2
        }
    }
    fatalError("Unreachable")
}

// Usage
let data = try await withRetry {
    try await fetchData(from: url)
}
```

### Async initialization pattern

```swift
// You cannot make init async directly on most types,
// but you can use a static factory method:
struct AppConfig {
    let apiKey: String
    let featureFlags: [String: Bool]

    static func load() async throws -> AppConfig {
        async let key = fetchAPIKey()
        async let flags = fetchFeatureFlags()
        return try await AppConfig(apiKey: key, featureFlags: flags)
    }
}
```

---

## Best Practices

1. **Prefer async/await over completion handlers** for new code.
2. **Use `async let` for parallel work** when you have a fixed number of independent operations.
3. **Always handle cancellation** -- check `Task.isCancelled` or call `try Task.checkCancellation()` in long-running work.
4. **Use checked continuations during development** -- switch to unsafe only after testing.
5. **Never resume a continuation more than once** -- this is a programming error.
6. **Remember that each `await` is a suspension point** -- state may change across an `await`.

---

## Decision Tree

```
Need to call an async function?
|
+-- From async context?
|   +-- YES -> just use `try await`
|   +-- NO -> wrap in `Task { }`
|
Need parallel execution?
|
+-- Fixed number of operations?
|   +-- YES -> use `async let`
|   +-- NO -> use `TaskGroup` (see tasks.md)
|
Need to wrap a callback API?
|
+-- Single callback?
|   +-- YES -> use `withChecked[Throwing]Continuation`
|   +-- NO (stream of values) -> use `AsyncStream` (see async-sequences.md)
|
Need typed errors?
|
+-- YES -> use `throws(MyError)` (Swift 6+)
+-- NO -> use plain `throws`
```

---

## Further Learning

- [The Swift Programming Language: Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)
- [SE-0296: Async/await](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0296-async-await.md)
- [SE-0317: async let](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0317-async-let.md)
- [SE-0413: Typed throws](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0413-typed-throws.md)
