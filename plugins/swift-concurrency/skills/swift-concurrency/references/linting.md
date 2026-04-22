# SwiftLint Concurrency Rules

## async_without_await

This rule flags functions marked `async` that never use `await` internally. However, there are several legitimate reasons a function must be `async` even without an `await` call.

### When async is required (suppress the warning)

**Protocol conformance.** If a protocol declares a method as `async`, all conforming types must use `async` even if their implementation is synchronous.

```swift
protocol DataProvider {
    func fetchData() async -> Data
}

struct LocalProvider: DataProvider {
    // Must be async to satisfy protocol, even though it never awaits
    func fetchData() async -> Data { // swiftlint:disable:this async_without_await
        Data()
    }
}
```

**Override of an async method.** Subclass overrides inherit the `async` requirement from the superclass.

```swift
class Base {
    func load() async -> String { ... }
}

class Child: Base {
    // swiftlint:disable:next async_without_await
    override func load() async -> String {
        "cached"
    }
}
```

**@concurrent functions.** In Swift 6, `@concurrent` implies `async` because the function must switch off the caller's isolation domain. The body may not contain an explicit `await`, but the function signature requires `async`.

```swift
@concurrent
func compute(_ x: Int) async -> Int { // swiftlint:disable:this async_without_await
    x * 2
}
```

### When async is unnecessary (fix the code)

If none of the above apply, remove `async` from the function signature. An unnecessarily `async` function forces all callers to `await` it, introducing a potential suspension point for no benefit.

```swift
// Bad
func formatName(_ name: String) async -> String {
    name.uppercased()
}

// Good
func formatName(_ name: String) -> String {
    name.uppercased()
}
```

---

## Other Concurrency Lint Rules

### non_sendable_in_actor

Warns when a non-`Sendable` value crosses an actor isolation boundary. Fix by making the type `Sendable`, using `sending`, or restructuring to avoid the crossing.

### actor_state_mutation_in_closure

Flags closures that capture and mutate actor-isolated state without proper isolation. The closure may execute on a different isolation domain.

### unavailable_from_async

Detects calls to functions annotated `@available(*, noasync)` from async contexts. These functions (e.g., certain lock-based APIs) must not be called across suspension points.

### implicitly_unwrapped_optional / force_cast in async contexts

While not concurrency-specific, force operations in async code are especially dangerous because error recovery across suspension points is harder to reason about.

### class_delegate_protocol

Encourages marking delegate protocols as `AnyObject`-constrained (or `any`-typed). In a concurrency context this matters because class-bound protocols can be made `Sendable` or actor-isolated more easily than unconstrained protocols.

---

## Suppression Strategies

Use inline suppression sparingly. Every suppression should include a rationale so future readers understand why the rule was bypassed.

### Inline suppression (single line)

```swift
func fetchData() async -> Data { // swiftlint:disable:this async_without_await - protocol requirement
    Data()
}
```

### Next-line suppression

```swift
// swiftlint:disable:next async_without_await - override of async superclass method
override func load() async -> String {
    "cached"
}
```

### Block suppression (use rarely)

```swift
// swiftlint:disable async_without_await
// ... multiple functions that conform to an async protocol ...
// swiftlint:enable async_without_await
```

### Rationale guidelines

Always document **why** a suppression exists:
- "Protocol conformance requires async"
- "Override of async superclass method"
- "@concurrent requires async signature"
- "Async needed for future implementation (tracked in ISSUE-1234)"

Avoid suppressions without rationale. They become mystery comments that no one dares to remove.

---

## Configuring SwiftLint for Swift 6 Projects

### .swiftlint.yml baseline

```yaml
# .swiftlint.yml
analyzer_rules:
  - unused_import

opt_in_rules:
  - async_without_await
  - non_sendable_in_actor
  - unavailable_from_async

# If migrating incrementally, you may temporarily disable rules
# that produce too much noise in partially-migrated modules:
disabled_rules: []

# Exclude generated code and build artifacts
excluded:
  - .build
  - DerivedData
  - "**/*.generated.swift"
```

### Compiler settings that interact with SwiftLint

Swift 6 strict concurrency is enabled by the language mode, not by SwiftLint. Make sure your build settings align:

```
// Package.swift
swiftLanguageVersions: [.v6]

// Or per-target in Xcode:
// SWIFT_STRICT_CONCURRENCY = complete
// SWIFT_VERSION = 6
```

When `SWIFT_STRICT_CONCURRENCY = complete`, the compiler itself catches many issues that SwiftLint also flags. In that scenario you may choose to rely on the compiler for data-race safety and use SwiftLint primarily for style and the `async_without_await` rule (which the compiler does not enforce).

### Incremental adoption strategy

1. **Start with warnings.** Set `SWIFT_STRICT_CONCURRENCY = targeted` or `complete` in warning mode while you fix violations.
2. **Enable SwiftLint concurrency rules as opt-in.** Review violations in CI before promoting them to errors.
3. **Promote to errors.** Once the module is clean, switch the language mode to Swift 6 (which makes concurrency violations errors) and move SwiftLint concurrency rules into the required set.
4. **Suppress only what you must.** For protocol conformances and overrides, use inline suppression with rationale. For genuinely non-Sendable types that must cross boundaries, prefer `sending` or `@unchecked Sendable` with documented justification over blanket disables.

### CI integration tip

Run SwiftLint as a separate CI step rather than a build phase so that lint failures do not block compilation feedback. This is especially valuable during migration when you want to see both compiler concurrency errors and lint warnings in a single CI run.
