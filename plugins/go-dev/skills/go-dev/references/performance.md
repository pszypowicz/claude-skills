# Performance

The workflow: measure, change, measure again. Never optimize without evidence.

## Benchmark-Driven Workflow

1. Write a benchmark for the hot path
2. Run it: `go test -bench=BenchmarkX -benchmem -count=6 ./... > old.txt`
3. Make your change
4. Run again: `go test -bench=BenchmarkX -benchmem -count=6 ./... > new.txt`
5. Compare: `benchstat old.txt new.txt`

Multiple runs (`-count=6`) give statistical significance. `benchstat` reports the delta with confidence intervals.

Install benchstat: `go install golang.org/x/perf/cmd/benchstat@latest`

## CPU Profiling

### From tests

```bash
go test -cpuprofile=cpu.out -bench=BenchmarkX ./...
go tool pprof cpu.out
```

Inside pprof:

- `top` - hottest functions
- `top -cum` - functions by cumulative time (includes callees)
- `list FunctionName` - annotated source
- `web` - opens flamegraph in browser (requires graphviz)

### From running programs

```go
import _ "net/http/pprof"

// Exposes /debug/pprof/ endpoints on the default mux
go func() { http.ListenAndServe("localhost:6060", nil) }()
```

Then: `go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30`

### Programmatic

```go
f, _ := os.Create("cpu.out")
pprof.StartCPUProfile(f)
defer pprof.StopCPUProfile()
```

## Memory Profiling

```bash
go test -memprofile=mem.out -bench=BenchmarkX ./...
go tool pprof -alloc_space mem.out   # total allocations
go tool pprof -inuse_space mem.out   # current live allocations
```

For production: `go tool pprof http://localhost:6060/debug/pprof/heap`

## Escape Analysis

See what allocates on the heap:

```bash
go build -gcflags='-m' ./...       # basic escape decisions
go build -gcflags='-m -m' ./...    # verbose reasoning
```

Common causes of heap escape:

- Returning a pointer to a local variable
- Closures capturing variables
- Interface conversions (the value may escape through the interface)
- Slices that grow beyond their initial capacity
- `fmt.Sprintf` and similar (arguments escape through `any` interface)

## Profile-Guided Optimization (PGO)

PGO uses a production CPU profile to optimize the build. Typically gives 2-7% throughput improvement.

### Workflow

1. Collect a CPU profile from production:

   ```bash
   curl -o default.pgo http://prod:6060/debug/pprof/profile?seconds=60
   ```

2. Place it in the main package directory as `default.pgo`

3. Build normally - PGO is automatic when `default.pgo` exists:

   ```bash
   go build -pgo=auto ./cmd/myapp  # auto is the default
   ```

4. Update the profile periodically (stale profiles still help but fresh ones are better)

## Common Allocation Reducers

### Pre-allocate slices

```go
// BAD - grows multiple times
var results []Item
for _, raw := range data {
    results = append(results, parse(raw))
}

// GOOD - single allocation
results := make([]Item, 0, len(data))
for _, raw := range data {
    results = append(results, parse(raw))
}
```

### strings.Builder for concatenation

```go
// BAD - allocates a new string each iteration
s := ""
for _, part := range parts {
    s += part
}

// GOOD - single buffer
var b strings.Builder
for _, part := range parts {
    b.WriteString(part)
}
result := b.String()
```

### sync.Pool for temporary objects

Reuse frequently allocated short-lived objects:

```go
var bufPool = sync.Pool{
    New: func() any { return new(bytes.Buffer) },
}

func process(data []byte) string {
    buf := bufPool.Get().(*bytes.Buffer)
    defer func() {
        buf.Reset()
        bufPool.Put(buf)
    }()
    // use buf...
    return buf.String()
}
```

### Avoid unnecessary pointer indirection

Value types stay on the stack when they do not escape. Small structs passed by value are often faster than by pointer due to cache locality and avoiding heap allocation.

### Reduce interface conversions

Each interface conversion can cause an allocation (boxing). In hot paths, use concrete types:

```go
// Allocates on every call due to any parameter
fmt.Sprintf("count: %d", count)

// Zero allocation alternative for logging
strconv.AppendInt(buf, count, 10)
```

## Execution Tracing

For understanding scheduling, GC pauses, and goroutine behavior:

```bash
go test -trace=trace.out ./...
go tool trace trace.out           # opens in browser
```

The trace viewer shows:

- Goroutine scheduling across OS threads
- GC pauses and their duration
- Network/syscall blocking
- Goroutine creation and destruction

## Quick Reference

| Goal                          | Command                                              |
| ----------------------------- | ---------------------------------------------------- |
| CPU profile from benchmark    | `go test -cpuprofile=cpu.out -bench=. ./...`         |
| Memory profile from benchmark | `go test -memprofile=mem.out -bench=. ./...`         |
| Escape analysis               | `go build -gcflags='-m' ./...`                       |
| Compare benchmarks            | `benchstat old.txt new.txt`                          |
| Execution trace               | `go test -trace=trace.out ./...`                     |
| Profile running server        | `go tool pprof http://host:6060/debug/pprof/profile` |
| Heap snapshot                 | `go tool pprof http://host:6060/debug/pprof/heap`    |
| Build with PGO                | Place `default.pgo` in main package, build normally  |
| Assembly output               | `go build -gcflags='-S' ./...`                       |
