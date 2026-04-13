# Concurrency

Go's concurrency model is built on goroutines and channels, with additional synchronization primitives in the `sync` and `sync/atomic` packages. The core rule: **always know how a goroutine ends.**

## Goroutine Lifecycle

Every goroutine you launch must have a clear termination path. A goroutine that runs forever without a shutdown mechanism is a leak.

```go
// BAD - no way to stop this
go func() {
    for {
        processQueue()
        time.Sleep(time.Second)
    }
}()

// GOOD - context-driven shutdown
go func() {
    ticker := time.NewTicker(time.Second)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            processQueue()
        }
    }
}()
```

## WaitGroup

### Traditional Pattern

```go
var wg sync.WaitGroup
for _, item := range items {
    wg.Add(1)  // MUST be before the goroutine, not inside it
    go func() {
        defer wg.Done()
        process(item)
    }()
}
wg.Wait()
```

Critical: call `wg.Add` before `go`, not inside the goroutine. Otherwise `Wait` may return before `Add` runs.

### wg.Go (Go 1.25+)

Combines `Add`, `go`, and `Done` into one call:

```go
var wg sync.WaitGroup
for _, item := range items {
    wg.Go(func() {
        process(item)
    })
}
wg.Wait()
```

Cleaner and eliminates the "Add before go" mistake. The function passed to `Go` must not panic.

## errgroup.Group

From `golang.org/x/sync/errgroup`. Like WaitGroup but collects the first error and supports context cancellation:

```go
g, ctx := errgroup.WithContext(ctx)
for _, url := range urls {
    g.Go(func() error {
        return fetch(ctx, url)
    })
}
if err := g.Wait(); err != nil {
    return fmt.Errorf("fetching urls: %w", err)
}
```

When one goroutine returns an error, the context is cancelled, signaling other goroutines to stop. Use `g.SetLimit(n)` to bound concurrency.

## Channels

### Directional Types

Declare channel direction in function signatures to communicate intent:

```go
func produce(ch chan<- int) { ... }  // send-only
func consume(ch <-chan int) { ... }  // receive-only
```

### Common Patterns

**Fan-out**: distribute work to multiple goroutines reading from one channel.

```go
jobs := make(chan Job, 100)
var wg sync.WaitGroup
for range numWorkers {
    wg.Go(func() {
        for job := range jobs {
            process(job)
        }
    })
}
// Send jobs...
close(jobs) // signals workers to exit
wg.Wait()
```

**Fan-in**: merge results from multiple goroutines into one channel.

```go
func merge(channels ...<-chan int) <-chan int {
    var wg sync.WaitGroup
    merged := make(chan int)
    for _, ch := range channels {
        wg.Go(func() {
            for v := range ch {
                merged <- v
            }
        })
    }
    go func() {
        wg.Wait()
        close(merged)
    }()
    return merged
}
```

**Done channel / context**: signal shutdown across goroutines.

```go
ctx, cancel := context.WithCancel(context.Background())
defer cancel()

go worker(ctx)

// When ready to shut down:
cancel()
```

### Channel Rules

- Only the sender should close a channel. Closing from the receiver side panics if the sender writes again.
- A nil channel blocks forever on both send and receive. Use this in `select` to dynamically disable cases.
- Unbuffered channels synchronize sender and receiver. Buffered channels decouple them up to the buffer size.
- `range` over a channel reads until it is closed.

## Mutexes

### sync.Mutex vs sync.RWMutex

- `sync.Mutex`: exclusive access. Use when reads and writes are roughly equal or when critical sections are short.
- `sync.RWMutex`: multiple concurrent readers, exclusive writer. Use when reads vastly outnumber writes.

```go
type SafeMap struct {
    mu sync.RWMutex
    m  map[string]int
}

func (s *SafeMap) Get(key string) (int, bool) {
    s.mu.RLock()
    defer s.mu.RUnlock()
    v, ok := s.m[key]
    return v, ok
}

func (s *SafeMap) Set(key string, val int) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.m[key] = val
}
```

### When to Use Mutex vs Channel

- **Mutex**: protecting shared state (maps, counters, structs). Think "guarding data."
- **Channel**: communicating between goroutines, coordinating work, signaling events. Think "passing ownership."

If you are protecting a data structure, use a mutex. If you are passing data between goroutines, use a channel.

## Atomic Operations

Type-safe atomics (Go 1.19+) for simple counters and flags:

```go
var counter atomic.Int64
counter.Add(1)
val := counter.Load()

var ready atomic.Bool
ready.Store(true)
if ready.Load() { ... }

var current atomic.Pointer[Config]
current.Store(newConfig)
cfg := current.Load()
```

Use atomics for single values where a full mutex would be overkill. Do not use atomics for compound operations (check-then-act requires a mutex).

## Context

### Purpose

`context.Context` carries deadlines, cancellation signals, and request-scoped values across API boundaries. Always pass it as the first parameter:

```go
func FetchUser(ctx context.Context, id int64) (*User, error) { ... }
```

### Creation

| Constructor                       | Use case                                                  |
| --------------------------------- | --------------------------------------------------------- |
| `context.Background()`            | Top of call chain (main, init, test setup)                |
| `context.TODO()`                  | Placeholder when unsure (grep for these and resolve them) |
| `context.WithCancel(parent)`      | Manual cancellation                                       |
| `context.WithTimeout(parent, d)`  | Deadline relative to now                                  |
| `context.WithDeadline(parent, t)` | Absolute deadline                                         |
| `context.WithValue(parent, k, v)` | Request-scoped data (use sparingly)                       |
| `context.WithoutCancel(parent)`   | Derived context that survives parent cancellation (1.21+) |

### AfterFunc (Go 1.21+)

Schedule cleanup when a context is cancelled:

```go
stop := context.AfterFunc(ctx, func() {
    conn.Close()
})
defer stop()
```

### Cancellation Checking

Long-running operations should check for cancellation:

```go
for _, item := range items {
    if err := ctx.Err(); err != nil {
        return fmt.Errorf("processing items: %w", err)
    }
    process(item)
}
```

In `select` loops, always include `case <-ctx.Done()`.

## sync.Once and Variants

### sync.Once (classic)

```go
var once sync.Once
var db *sql.DB

func GetDB() *sql.DB {
    once.Do(func() {
        db = connectDB()
    })
    return db
}
```

### sync.OnceFunc (Go 1.21+)

Returns a function that runs `f` only once:

```go
initDB := sync.OnceFunc(func() {
    db = connectDB()
})
```

### sync.OnceValue[T] (Go 1.21+)

Like OnceFunc but returns a value:

```go
getConfig := sync.OnceValue(func() *Config {
    return loadConfig()
})

cfg := getConfig() // loads on first call, cached after
```

## Select Statement

```go
select {
case msg := <-inbox:
    handle(msg)
case <-ctx.Done():
    return ctx.Err()
case <-time.After(5 * time.Second):
    return ErrTimeout
default:
    // non-blocking: runs if no case is ready
}
```

- Without `default`, `select` blocks until a case is ready.
- With `default`, `select` is non-blocking. Use this for try-send/try-receive patterns.
- When multiple cases are ready, Go picks one at random.

## Common Pitfalls

### Goroutine Leak

A goroutine blocked on a channel that nobody reads or writes is a leak. Always ensure channels are eventually closed or contexts are cancelled.

```go
// LEAK - if nobody reads from ch, goroutine blocks forever
ch := make(chan int)
go func() {
    ch <- expensiveCompute()
}()
// if we return early without reading ch, the goroutine leaks

// FIX - use a buffered channel so send doesn't block
ch := make(chan int, 1)
go func() {
    ch <- expensiveCompute()
}()
```

### Mutex Copy

A `sync.Mutex` must not be copied after first use. Embedding a mutex in a struct that gets copied (e.g., passed by value) silently creates a separate lock that protects nothing.

```go
// BAD - Lock is copied with the struct
type Counter struct {
    sync.Mutex
    n int
}
func (c Counter) Value() int { // value receiver copies the mutex
    c.Lock()
    defer c.Unlock()
    return c.n
}

// GOOD - pointer receiver, no copy
func (c *Counter) Value() int {
    c.Lock()
    defer c.Unlock()
    return c.n
}
```

`go vet` catches this with the `copylocks` analyzer.

### Closing Channel From Wrong Side

Only the sender should close a channel. If the receiver closes it, the sender will panic on the next write.

### Race on Shared Map

Maps are not safe for concurrent use. Concurrent read + write (or write + write) on a map causes a runtime crash, not just wrong results.

Fix: protect with `sync.Mutex`, use `sync.Map`, or restrict access to a single goroutine.

## Testing Concurrent Code

- Always run `go test -race` for packages with goroutines. The race detector catches races that execute during the test.
- The race detector only finds races that happen. It does not prove absence of races.
- Use `testing/synctest` (Go 1.24+) for deterministic testing of time-dependent concurrent code.
- Use `go.uber.org/goleak` to detect goroutine leaks in tests.

```go
func TestNoLeak(t *testing.T) {
    defer goleak.VerifyNone(t)
    // ... test code ...
}
```
