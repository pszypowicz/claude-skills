# Swift Concurrency Glossary

**Actor** - A reference type that protects its mutable state by ensuring only one task accesses that state at a time. External access to an actor's isolated members requires `await` because the caller may need to suspend until the actor is available.

**async/await** - Language keywords for asynchronous programming. `async` marks a function that can suspend, and `await` marks a point where the calling task may suspend while waiting for the result.

**AsyncSequence** - A protocol for sequences that produce elements asynchronously. You iterate over an `AsyncSequence` using `for await ... in`. Each element may require a suspension to become available.

**AsyncStream** - A concrete `AsyncSequence` provided by the standard library that bridges callback-based or imperative code into the async sequence world. Created with a continuation that you call `yield(_:)` and `finish()` on.

**@concurrent** - A Swift 6 attribute that opts a `nonisolated async` function into running on the cooperative thread pool rather than inheriting the caller's isolation. Functions marked `@concurrent` may run in parallel with the caller and therefore require their arguments to be `Sendable` (or `sending`).

**Continuation** - The mechanism (`CheckedContinuation`, `UnsafeContinuation`) for bridging non-async code (such as completion handlers or delegate callbacks) into async/await. You must resume a continuation exactly once.

**Cooperative thread pool** - The fixed-size pool of threads managed by the Swift runtime that executes tasks. Tasks voluntarily yield the thread at suspension points, allowing other tasks to run. The pool is intentionally limited (typically to the number of CPU cores) to avoid thread explosion.

**Data race** - A bug where two or more threads access the same memory concurrently and at least one access is a write, with no synchronization. Swift 6 strict concurrency aims to eliminate data races at compile time.

**Race condition** - A broader class of bug where the correctness of a program depends on the relative timing of events. Unlike data races, race conditions can occur even in data-race-safe code (e.g., two actors updating related state in an unexpected order).

**Default isolation** - In Swift 6, the isolation that a declaration inherits when it has no explicit isolation annotation. For top-level code and `@MainActor`-annotated types, the default isolation is the main actor. The `nonisolated` keyword overrides default isolation.

**Detached task** - A task created with `Task.detached { }` that does not inherit the caller's priority, task-local values, or actor isolation. Use detached tasks only when you explicitly need to break away from the current context.

**Global actor** - An actor that provides a single shared isolation domain accessible via a global attribute. `@MainActor` is the most common global actor. You can define custom global actors with the `@globalActor` attribute.

**isolated / nonisolated** - Keywords controlling whether a declaration participates in an actor's isolation domain. `isolated` (the default for actor members) means the declaration is protected by the actor. `nonisolated` means the declaration opts out and can be called without `await`, but cannot access the actor's isolated state.

**Isolation domain** - A region of code and data protected by a single concurrency primitive (an actor, a global actor, or a task). Within one isolation domain, code runs serially and can safely access shared mutable state. Crossing between isolation domains requires `await` and `Sendable` conformance.

**@MainActor** - A global actor attribute that isolates code to the main thread. UI frameworks require main-actor isolation for view updates. Functions, types, and properties can all be annotated with `@MainActor`.

**Mutex** - (`Mutex<Value>` in the Synchronization framework.) A synchronous locking primitive that protects a value with mutual exclusion. Unlike actors, a `Mutex` blocks the current thread rather than suspending. Useful for protecting small critical sections where suspension is not desired.

**nonisolated(nonsending)** - A Swift 6 annotation for nonisolated async functions indicating the function does not send its execution to the cooperative thread pool and instead stays on the caller's isolation context. This is the default for nonisolated async functions in Swift 6 (replacing the Swift 5 behavior where they always hopped to the pool).

**@Observable** - A macro (from the Observation framework) that makes a class's properties observable. In concurrency contexts, `@Observable` classes are often isolated to `@MainActor` so that UI observations happen on the main thread. The macro synthesizes tracking infrastructure but does not itself provide thread safety.

**Region-based isolation** - A Swift compiler analysis that tracks which "region" a value belongs to, allowing non-`Sendable` values to safely cross isolation boundaries when the compiler can prove they are not shared. This reduces the need for `@unchecked Sendable` and `sending` in many common patterns.

**Reentrancy** - The property of actors that allows them to process other messages while a task is suspended awaiting a result. Actor state may change across an `await` within an actor method, so you must not assume state is unchanged after a suspension point.

**Sendable** - A protocol indicating a type's values can be safely shared across isolation domains. Value types with `Sendable` stored properties, actors, and immutable classes can conform. The compiler enforces `Sendable` at isolation boundaries in strict concurrency mode.

**@Sendable** - An attribute on function types (closures) indicating the closure may be called from a different isolation domain. A `@Sendable` closure must not capture mutable local state unless that state is itself `Sendable` and protected.

**sending keyword** - A parameter or result annotation indicating the value is being transferred out of one isolation domain and into another. The compiler verifies that the caller does not retain a reference to the sent value after the call. More precise than requiring `Sendable` conformance.

**Structured concurrency** - A model where child tasks are scoped to their parent, forming a tree. If a parent is cancelled, all children are cancelled. Child tasks must complete before the parent scope exits. Achieved with `async let` and task groups.

**Suspension point** - A point in an async function (marked by `await`) where the task may pause and yield its thread. Actor state can change across suspension points (reentrancy), and other tasks may run on the same thread.

**Task** - The basic unit of concurrency in Swift. A task runs an async function from start to finish, suspending and resuming as needed. Tasks have priority, can be cancelled, and carry task-local values.

**Task group** - A form of structured concurrency (`withTaskGroup`, `withThrowingTaskGroup`, `withDiscardingTaskGroup`) that dynamically spawns child tasks and collects their results. The group scope guarantees all child tasks finish before the group returns.

**Task-local values** - Values bound to a task via `@TaskLocal` that are automatically inherited by child tasks. Useful for propagating contextual information (like request IDs or loggers) through an async call chain without explicit parameter passing.

**@unchecked Sendable** - A way to assert `Sendable` conformance without compiler verification. The developer takes responsibility for thread safety. Use only when the compiler cannot prove safety but you have ensured it (e.g., internally-synchronized classes, immutable-after-initialization patterns). Always document why it is safe.

**Unstructured task** - A task created with `Task { }` that inherits the caller's priority, actor isolation, and task-local values but whose lifetime is not bound to a scope. The caller gets a `Task` handle for cancellation but is not required to await it.
