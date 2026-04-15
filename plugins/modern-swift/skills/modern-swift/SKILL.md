---
name: modern-swift
description: >-
  Swift language features beyond concurrency: attributes (@available,
  @discardableResult, @frozen, @inlinable, @usableFromInline, @backDeployed,
  @resultBuilder, @propertyWrapper) and macro usage (#Preview, custom macros).
  Use when the user asks about API availability checks, library evolution,
  deprecating or renaming APIs, back-deploying functions to older OSes,
  result builders / DSLs, property wrappers, or Swift macros. Do NOT use
  this skill for concurrency topics (async/await, actors, Sendable,
  @MainActor, @Observable) - those belong to swift-concurrency.
---

# Modern Swift

Focused reference for Swift language features that are commonly misused or
forgotten but are **not** concurrency-related. Concurrency lives in the
`swift-concurrency` skill; this skill deliberately does not duplicate it.

## When to load which reference

| Topic                                            | File                                         | Load when                                                                                 |
| ------------------------------------------------ | -------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `@available`, `#available`, deprecation, renames | `references/attributes.md#availability`      | Marking API availability, deprecating, renaming, or gating runtime behavior on OS version |
| `@discardableResult`                             | `references/attributes.md#discardableresult` | Function returns a value callers may reasonably ignore                                    |
| `@frozen`                                        | `references/attributes.md#frozen`            | Library author deciding whether an enum/struct layout is stable                           |
| `@inlinable`, `@usableFromInline`                | `references/attributes.md#inlinable`         | Performance-critical code in a resilient library                                          |
| `@backDeployed`                                  | `references/attributes.md#backdeployed`      | Shipping a new API to clients running older OSes                                          |
| `@resultBuilder`                                 | `references/attributes.md#resultbuilder`     | Building a DSL (SwiftUI-style)                                                            |
| `@propertyWrapper`                               | `references/attributes.md#propertywrapper`   | Encapsulating get/set behavior on stored properties                                       |
| `#Preview`                                       | `references/macros.md#preview`               | Writing SwiftUI previews                                                                  |
| Custom macros                                    | `references/macros.md#custom-macros`         | Understanding or authoring Swift macros                                                   |

## Routing guardrails

- **Concurrency topics** (`async`, `await`, `actor`, `@MainActor`, `Sendable`,
  `@Observable`, `@preconcurrency`) belong to **swift-concurrency**. Do not
  answer them from this skill - defer.
- **`@frozen`, `@inlinable`, `@backDeployed`** are relevant only to
  **resilient libraries** (frameworks distributed as binaries with ABI
  stability). App targets rarely need them. If the user is writing an app,
  say so and suggest the simpler alternative.
- **`@backDeployed` has real rules** beyond "copy the body": public or
  `@usableFromInline`, body must follow `@inlinable` restrictions, methods
  on classes must be `final`, stored properties are excluded. See
  `references/attributes.md#backdeployed`.

## Common mistakes

1. **Using `@frozen` in an app target.** It's a library-evolution feature
   and has no effect outside resilient libraries. Remove it.
2. **`@backDeployed` on a stored property.** Not supported. Only computed
   properties (no storage), functions, `final` methods, and subscripts.
3. **`@inlinable` body referencing an `internal` symbol.** The body is
   emitted into client binaries, so it can only reference public or
   `@usableFromInline` symbols.
4. **Forgetting `@discardableResult` on a fluent API.** Causes "result
   unused" warnings for legitimate call sites. Mark the method, don't tell
   the caller to add `_ =`.
5. **Property wrapper with `didSet` clamping loop.** Swift prevents the
   recursion, but it's still clearer to clamp in the setter of a computed
   `wrappedValue` backed by a private stored value. See the canonical
   pattern in `references/attributes.md#propertywrapper`.
