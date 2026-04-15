# Swift Attributes

Covers non-concurrency attributes. All examples in this file have been
compile-tested with `swiftc` (Swift 6.3, Xcode 26 toolchain).

Concurrency attributes (`@MainActor`, `@preconcurrency`, `@Sendable`,
`@concurrent`, `nonisolated(unsafe)`) live in the `swift-concurrency` skill.

## availability

### @available (declaration availability)

Marks the OS versions a declaration is available on. The compiler enforces
that callers check availability before using it.

```swift
@available(macOS 14, iOS 17, *)
func newFeature() { }

// Deprecated with a rename fix-it
@available(*, deprecated, renamed: "newMethod()")
func oldMethod() { }

// Hard-unavailable with a custom diagnostic
@available(*, unavailable, message: "Use NewClass instead")
class OldClass { }
```

The trailing `*` is the "other platforms" fallback. Without it the
declaration is unavailable on unlisted platforms.

### #available (runtime check)

Gates code on the actual OS version at runtime.

```swift
@available(macOS 14, iOS 17, *)
func newFeature() { }
func legacyAlternative() { }

func run() {
    if #available(macOS 14, *) {
        newFeature()
    } else {
        legacyAlternative()
    }
}

// Guard form for early exit - only valid inside a function
func runOrBail() {
    guard #available(iOS 17, *) else { return }
    newFeature()
}
```

Rules:

- `#available` can only appear in an `if` or `guard` condition.
- The `*` is required and means "every other platform".
- Use `#unavailable` (the inverse) for "bail out on older OS" patterns.

### Common deprecation patterns

```swift
import Foundation

// Soft deprecation with a working replacement
@available(*, deprecated, message: "Use fetchAsync instead")
func fetch(completion: (Result<Data, Error>) -> Void) { }

// Deprecated since a specific version
@available(macOS, introduced: 12, deprecated: 14, renamed: "newAPI")
func oldAPI() { }

// Obsoleted (hard error on that OS and later)
@available(macOS, introduced: 10.15, obsoleted: 14)
func transitionalAPI() { }
```

## discardableResult

Silences the "result unused" warning for functions where ignoring the
return value is normal.

```swift
struct Record {
    @discardableResult
    func save() -> Bool {
        // ...
        return true
    }
}

let r = Record()
r.save()            // no warning
let ok = r.save()   // still works
```

Use for:

- Fluent/builder APIs that return `self`.
- Persistence calls where the success `Bool` is usually ignored.
- Collection methods that return a removed value (cf. `Array.removeFirst`).

Do **not** use to hide genuinely-important return values - the warning
exists for a reason.

## frozen

Applies to public enums and structs in resilient libraries. Declares that
the type's layout and (for enums) its set of cases will never change.
Enables compiler optimizations in client code at the cost of future
flexibility.

```swift
@frozen
public enum Direction {
    case north, south, east, west
}

@frozen
public struct APIVersion: Sendable {
    public let major: Int
    public let minor: Int
}
```

When it matters:

- **Relevant** for frameworks distributed as binaries with
  `-enable-library-evolution` (Apple's SDK frameworks, resilient SwiftPM
  libraries). Enables non-resilient layout and avoids an `@unknown default`
  requirement on clients.
- **Irrelevant** for app code, test targets, and non-resilient libraries.
  It compiles but has no effect. Remove it to reduce noise.

Once you ship a `@frozen` public type, adding a case/property is an ABI
break. Treat it as a one-way door.

## inlinable

`@inlinable` exposes the body of a public function to client binaries so
the optimizer can inline across the module boundary. Used in
performance-critical library code.

```swift
@inlinable
public func clamp(_ value: Int, to range: ClosedRange<Int>) -> Int {
    min(max(value, range.lowerBound), range.upperBound)
}
```

### @usableFromInline

An `@inlinable` body can only reference symbols that are visible to
clients - `public` or `@usableFromInline`. Use `@usableFromInline` to
expose an `internal` symbol to `@inlinable` code without making it part of
the public API surface.

```swift
@usableFromInline
internal struct InternalHelper {
    @usableFromInline
    internal init() { }

    @usableFromInline
    internal func compute() -> Int { 42 }
}

@inlinable
public func useHelper() -> Int {
    InternalHelper().compute()
}
```

Caveats:

- Changing an `@inlinable` body is potentially an ABI break: old clients
  have the old body inlined into their binary.
- Only use in library targets with library evolution enabled. In app code
  the compiler can inline freely without the attribute.

## backDeployed

SE-0376. Lets a library ship a new API that runs on older OS releases by
embedding a copy of the implementation in the client binary as a fallback.

```swift
import SwiftUI

extension Text {
    @available(macOS 13, *)
    @backDeployed(before: macOS 14)
    public func customModifier() -> some View {
        self.bold()
    }
}
```

### Hard rules (SE-0376)

- The declaration must be `public` or `@usableFromInline`.
- Body restrictions match `@inlinable`: it can only reference symbols
  available to clients.
- Applies to: functions, methods, subscripts, and **computed** properties.
  Stored properties are excluded.
- On classes, methods must be `final` (the feature synthesizes a
  wrapper that clients can statically dispatch to).
- Must carry an `@available` that makes the symbol available before the
  `backDeployed` floor - the back-deployed body fills the gap between the
  OS that introduced the symbol and the OS whose framework has a native
  implementation.

### When to use

- Framework author shipping a new API and wanting it to work on the
  previous major OS without a version check at every call site.
- The implementation is small and self-contained (cannot reference
  internal framework symbols).

If your body needs internal symbols, `@backDeployed` is not an option -
use runtime checks with `#available` and maintain a parallel
implementation.

## resultBuilder

Turns a type into a DSL for building composite values from multiple
statements. SwiftUI's `ViewBuilder`, SwiftPM's `Package` manifest, and
regex builders all use this.

```swift
@resultBuilder
struct ArrayBuilder<Element> {
    static func buildBlock(_ components: Element...) -> [Element] {
        components
    }

    static func buildOptional(_ component: [Element]?) -> [Element] {
        component ?? []
    }

    static func buildEither(first component: [Element]) -> [Element] {
        component
    }

    static func buildEither(second component: [Element]) -> [Element] {
        component
    }
}

func buildList<T>(@ArrayBuilder<T> content: () -> [T]) -> [T] {
    content()
}

let items = buildList {
    "Hello"
    "World"
}
```

### Build methods (all optional except `buildBlock` / `buildPartialBlock`)

| Method                                                               | Handles                                                                     |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `buildBlock(_:)`                                                     | The sequence of statements in a block                                       |
| `buildPartialBlock(first:)` / `buildPartialBlock(accumulated:next:)` | Swift 5.9+ incremental alternative to `buildBlock` (better type-check perf) |
| `buildExpression(_:)`                                                | Individual expression - lets you accept mixed types                         |
| `buildOptional(_:)`                                                  | `if` without `else`                                                         |
| `buildEither(first:)` / `buildEither(second:)`                       | `if` / `else` branches                                                      |
| `buildArray(_:)`                                                     | `for` loops                                                                 |
| `buildLimitedAvailability(_:)`                                       | `if #available` blocks                                                      |
| `buildFinalResult(_:)`                                               | Post-processes the final value                                              |

You need **either** `buildBlock` or the `buildPartialBlock` pair. Everything
else is opt-in per feature the DSL needs to support.

## propertyWrapper

Reusable get/set logic for stored properties. The compiler rewrites
`@Wrapper var x: T` into storage of type `Wrapper<T>` plus a computed
accessor.

```swift
@propertyWrapper
struct Clamped<Value: Comparable> {
    private var value: Value
    let range: ClosedRange<Value>

    var wrappedValue: Value {
        get { value }
        set { value = min(max(newValue, range.lowerBound), range.upperBound) }
    }

    init(wrappedValue: Value, _ range: ClosedRange<Value>) {
        self.range = range
        self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }
}

struct Volume {
    @Clamped(0...100) var level: Int = 50
}

var v = Volume()
v.level = 150   // clamped to 100
v.level = -10   // clamped to 0
```

Required members:

- `wrappedValue` - the stored or computed projection.
- `init(wrappedValue:)` - enables `@Wrapper var x: T = default` syntax.

Optional members:

- `projectedValue` - accessed via `$x` at the use site (SwiftUI's
  `@State` exposes a `Binding` this way).
- `init()` with no arguments - supports `@Wrapper var x: T` without a
  default.

### Anti-pattern: clamping in didSet

The old idiom put the clamp in `didSet`:

```swift
// Avoid: works because Swift suppresses didSet recursion, but it's confusing
@propertyWrapper
struct ClampedDidSet<Value: Comparable> {
    let range: ClosedRange<Value>

    var wrappedValue: Value {
        didSet {
            wrappedValue = min(max(wrappedValue, range.lowerBound), range.upperBound)
        }
    }

    init(wrappedValue: Value, _ range: ClosedRange<Value>) {
        self.range = range
        self.wrappedValue = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }
}
```

Prefer the computed `wrappedValue` shown above: the transformation is
visible at the point where the value is written, there's no reliance on
didSet-recursion rules, and the stored `value` is clearly internal state.
