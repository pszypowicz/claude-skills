# Modern Go Features (1.21-1.26)

Check `go.mod` for the project's Go version before suggesting features from this guide. Only use features available at or below the declared version.

## Go 1.21

### log/slog - Structured Logging

Replaces `log` for production use. Structured key-value pairs instead of unstructured strings:

```go
slog.Info("user logged in", "user_id", userID, "ip", req.RemoteAddr)
slog.Error("query failed", "err", err, "query", q)
```

Supports JSON output, log levels, and custom handlers. Use `slog.With` for common fields:

```go
logger := slog.With("service", "auth", "version", version)
logger.Info("starting")
```

### slices and maps packages

Generic utility functions replacing hand-written loops:

```go
slices.Sort(names)                          // sort in place
slices.SortFunc(users, func(a, b User) int { return cmp.Compare(a.Age, b.Age) })
idx, found := slices.BinarySearch(sorted, target)
slices.Contains(roles, "admin")
slices.Compact(sorted)                      // remove consecutive duplicates

maps.Keys(m)                                // iter.Seq[K]
maps.Values(m)                              // iter.Seq[V]
maps.Clone(m)                               // shallow copy
```

### min, max, clear builtins

```go
smallest := min(a, b, c)    // works with any ordered type
largest := max(x, y)
clear(myMap)                 // removes all entries
clear(mySlice)               // zeros all elements, keeps length
```

### context additions

```go
// AfterFunc - schedule cleanup on cancellation
stop := context.AfterFunc(ctx, func() { conn.Close() })
defer stop()

// WithoutCancel - derived context that survives parent cancellation
bgCtx := context.WithoutCancel(ctx)

// WithCancelCause - cancellation with a reason
ctx, cancel := context.WithCancelCause(parent)
cancel(fmt.Errorf("user requested shutdown"))
// later: context.Cause(ctx) returns the error
```

### sync.OnceFunc / OnceValue

```go
initDB := sync.OnceFunc(func() { db = connectDB() })

getConfig := sync.OnceValue(func() *Config { return loadConfig() })
cfg := getConfig()
```

### PGO Auto

Profile-Guided Optimization is automatic when a `default.pgo` file exists in the main package directory. No build flags needed.

## Go 1.22

### Range over integers

```go
for i := range 10 {
    fmt.Println(i) // 0, 1, 2, ..., 9
}
```

Replaces `for i := 0; i < 10; i++`.

### Enhanced http.ServeMux

Pattern-based routing with method matching:

```go
mux := http.NewServeMux()
mux.HandleFunc("GET /users/{id}", getUser)
mux.HandleFunc("POST /users", createUser)
mux.HandleFunc("DELETE /users/{id}", deleteUser)
```

Extract path parameters: `r.PathValue("id")`

### math/rand/v2

Replaces `math/rand`. No seeding needed. Better API:

```go
n := rand.IntN(100)           // [0, 100)
f := rand.Float64()           // [0.0, 1.0)
rand.Shuffle(len(s), func(i, j int) { s[i], s[j] = s[j], s[i] })
```

### Loop variable semantic change

In Go 1.22+, each iteration of a `for` loop creates a new variable. The pre-1.22 gotcha where closures captured the same loop variable is fixed:

```go
// This is now safe in Go 1.22+ (was a bug before)
for _, v := range values {
    go func() {
        fmt.Println(v) // each goroutine gets its own v
    }()
}
```

## Go 1.23

### Iterators: iter.Seq and iter.Seq2

Range-over-func enables custom iteration:

```go
type iter.Seq[V any]     func(yield func(V) bool)
type iter.Seq2[K, V any] func(yield func(K, V) bool)
```

Standard library functions returning iterators:

```go
for k, v := range maps.All(m) { ... }
for i, v := range slices.All(s) { ... }
for v := range slices.Values(s) { ... }
collected := slices.Collect(seq)
```

### unique.Handle

Interning for deduplication:

```go
h := unique.Make("frequently-used-string")
// h.Value() returns the canonical copy
```

## Go 1.24

### testing.T.Context

Returns a context cancelled when the test ends:

```go
ctx := t.Context()  // replaces ctx, cancel := context.WithCancel(...)
```

### testing.T.Chdir

```go
t.Chdir("testdata/fixtures")  // restored automatically
```

### os.Root

Safe file access within a directory tree - prevents path traversal:

```go
root, err := os.OpenRoot("/var/data")
f, err := root.Open("user/config.json")  // cannot escape /var/data
```

### Generic type aliases

Type aliases can now be parameterized:

```go
type Set[T comparable] = map[T]struct{}
```

### go tool runs module tools

Tools declared in go.mod can be run directly:

```go
// In go.mod:
tool golang.org/x/tools/cmd/stringer

// Then:
// $ go tool stringer -type=Color
```

### testing/synctest

Deterministic testing of time-dependent code:

```go
func TestTimeout(t *testing.T) {
    synctest.Run(func() {
        ctx, cancel := context.WithTimeout(t.Context(), 5*time.Second)
        defer cancel()
        // synctest controls the fake clock
        synctest.Wait() // advance to next timer
    })
}
```

### omitzero JSON tag

```go
type Event struct {
    Time time.Time `json:"time,omitzero"`  // omitted when zero value
    Data Data      `json:"data,omitzero"`  // works with structs too
}
```

Unlike `omitempty`, `omitzero` checks for the zero value of the type, which is correct for structs like `time.Time`.

## Go 1.25

### sync.WaitGroup.Go

```go
var wg sync.WaitGroup
wg.Go(func() { process(item) })
wg.Wait()
```

Replaces the `wg.Add(1); go func() { defer wg.Done(); ... }()` pattern.

### testing.T.Attr and T.Output

```go
t.Attr("category", "integration")
t.Output(os.Stdout)  // redirect test output
```

### sync.Map range-over-func

```go
var m sync.Map
for k, v := range m.Range { // returns iter.Seq2
    fmt.Println(k, v)
}
```

## Go 1.26

### errors.AsType[T]

Generic error type extraction:

```go
if ve, ok := errors.AsType[*ValidationError](err); ok {
    fmt.Println(ve.Field)
}
```

Cleaner than `errors.As` - no need for a pre-declared variable.

### go fix command

Automated code modernization with 21 fixers:

```bash
go fix -diff ./...   # preview as unified diff
go fix ./...         # apply all fixes
go fix -any ./...    # run only the 'any' fixer
```

### testing.T.ArtifactDir

```go
dir := t.ArtifactDir()
os.WriteFile(filepath.Join(dir, "output.html"), data, 0644)
```

Use with `go test -artifacts=./output` to persist.

### New vet analyzers

- `waitgroup`: detects `wg.Add` called inside goroutine
- `hostport`: checks address format for `net.Dial` and related functions

### new(expr) shorthand

```go
p := new(MyStruct{Field: "value"})  // equivalent to: tmp := MyStruct{...}; p = &tmp
```

## Deprecated Patterns Migration

| Deprecated                                    | Replacement                       | Since |
| --------------------------------------------- | --------------------------------- | ----- |
| `ioutil.ReadAll`                              | `io.ReadAll`                      | 1.16  |
| `ioutil.ReadFile`                             | `os.ReadFile`                     | 1.16  |
| `ioutil.WriteFile`                            | `os.WriteFile`                    | 1.16  |
| `ioutil.TempDir`                              | `os.MkdirTemp`                    | 1.16  |
| `ioutil.TempFile`                             | `os.CreateTemp`                   | 1.16  |
| `ioutil.ReadDir`                              | `os.ReadDir`                      | 1.16  |
| `ioutil.NopCloser`                            | `io.NopCloser`                    | 1.16  |
| `ioutil.Discard`                              | `io.Discard`                      | 1.16  |
| `math/rand.Seed`                              | Delete call (auto-seeded)         | 1.20  |
| `math/rand.Read`                              | `crypto/rand.Read`                | 1.20  |
| `// +build`                                   | `//go:build`                      | 1.17  |
| `interface{}`                                 | `any`                             | 1.18  |
| `sort.Slice`                                  | `slices.Sort` / `slices.SortFunc` | 1.21  |
| `sort.Search`                                 | `slices.BinarySearch`             | 1.21  |
| Manual `for i := 0; i < n; i++`               | `for i := range n`                | 1.22  |
| `wg.Add(1); go func() { defer wg.Done()... }` | `wg.Go(f)`                        | 1.25  |

Use `go fix -diff ./...` to detect and preview many of these replacements automatically.
