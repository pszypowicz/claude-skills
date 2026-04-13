# Testing

## Table-Driven Tests

The standard Go testing pattern. Define inputs and expectations as a slice, run each as a subtest:

```go
func TestParseSize(t *testing.T) {
    tests := []struct {
        name    string
        input   string
        want    int64
        wantErr bool
    }{
        {name: "bytes", input: "100B", want: 100},
        {name: "kilobytes", input: "2KB", want: 2048},
        {name: "empty", input: "", wantErr: true},
        {name: "invalid", input: "abc", wantErr: true},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := ParseSize(tt.input)
            if (err != nil) != tt.wantErr {
                t.Fatalf("ParseSize(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
            }
            if got != tt.want {
                t.Errorf("ParseSize(%q) = %d, want %d", tt.input, got, tt.want)
            }
        })
    }
}
```

Use `t.Fatalf` for conditions that make continuing pointless. Use `t.Errorf` when you want to see all failures.

## Test Helpers

Mark helper functions with `t.Helper()` so failure messages point to the caller, not the helper:

```go
func assertNoError(t *testing.T, err error) {
    t.Helper()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
}
```

## Cleanup

`t.Cleanup` registers a function to run when the test (and all its subtests) complete:

```go
func setupDB(t *testing.T) *sql.DB {
    t.Helper()
    db, err := sql.Open("postgres", testDSN)
    assertNoError(t, err)
    t.Cleanup(func() { db.Close() })
    return db
}
```

Cleanup functions run in LIFO order (last registered, first called).

## Parallel Tests

`t.Parallel()` marks a test or subtest as safe to run concurrently:

```go
func TestConcurrent(t *testing.T) {
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            // test body - must not share mutable state with other subtests
            got := process(tt.input)
            if got != tt.want {
                t.Errorf("got %v, want %v", got, tt.want)
            }
        })
    }
}
```

Rules:

- Do not access shared mutable state from parallel tests without synchronization
- Parallel subtests wait for all non-parallel subtests to finish before starting
- `t.Setenv` cannot be used in parallel tests (it modifies shared process state)

## t.Context (Go 1.24+)

Returns a context that is cancelled when the test finishes:

```go
func TestWithContext(t *testing.T) {
    ctx := t.Context()
    result, err := fetchWithTimeout(ctx, url)
    // ctx is automatically cancelled when the test ends
}
```

Replaces the pattern of creating `context.WithCancel` and deferring `cancel()` in every test.

## t.Chdir (Go 1.24+)

Temporarily changes the working directory for the test:

```go
func TestReadConfig(t *testing.T) {
    t.Chdir("testdata/project")
    cfg, err := ReadConfig("config.yaml")
    // working dir is restored when the test ends
}
```

## t.ArtifactDir (Go 1.26+)

Returns a directory for storing test output artifacts:

```go
func TestGenerateReport(t *testing.T) {
    report := generateReport(data)
    path := filepath.Join(t.ArtifactDir(), "report.html")
    os.WriteFile(path, report, 0644)
}
```

Use with `go test -artifacts=./output` to persist artifacts outside temp directories.

## t.Attr (Go 1.25+)

Attach metadata to test results for CI/CD systems:

```go
func TestSlowOperation(t *testing.T) {
    t.Attr("category", "integration")
    t.Attr("owner", "platform-team")
    // ...
}
```

## Benchmarks

```go
func BenchmarkProcess(b *testing.B) {
    data := loadTestData()
    b.ResetTimer() // exclude setup time
    for b.Loop() { // Go 1.24+; use `for range b.N` on older versions
        process(data)
    }
}
```

Run with: `go test -bench=. -benchmem -count=6 ./...`

- `-benchmem` reports allocations per operation
- `-count=6` runs multiple times for statistical significance
- Use `benchstat` to compare results: `benchstat old.txt new.txt`

### Benchmark Pitfalls

**Compiler eliminating work**: if the result is unused, the compiler may optimize the call away entirely:

```go
// BAD - compiler may eliminate the call
func BenchmarkHash(b *testing.B) {
    for b.Loop() {
        sha256.Sum256(data) // result unused, may be optimized away
    }
}

// GOOD - store result to prevent elimination
var sink [32]byte
func BenchmarkHash(b *testing.B) {
    for b.Loop() {
        sink = sha256.Sum256(data)
    }
}
```

**Including setup in measurements**: use `b.ResetTimer()` after expensive setup, `b.StopTimer()`/`b.StartTimer()` for per-iteration setup.

## Fuzzing

Fuzzing discovers inputs that cause panics, crashes, or unexpected behavior:

```go
func FuzzParseJSON(f *testing.F) {
    // Seed corpus - provide representative inputs
    f.Add([]byte(`{"key": "value"}`))
    f.Add([]byte(`[]`))
    f.Add([]byte(`null`))

    f.Fuzz(func(t *testing.T, data []byte) {
        var result any
        err := json.Unmarshal(data, &result)
        if err != nil {
            return // invalid input is fine, just don't panic
        }
        // If it parsed, it should re-marshal without error
        _, err = json.Marshal(result)
        if err != nil {
            t.Errorf("round-trip failed: %v", err)
        }
    })
}
```

Run with: `go test -fuzz=FuzzParseJSON -fuzztime=30s`

Use fuzzing for parsers, deserializers, and any function that accepts untrusted input. Table-driven tests are better for known behavior verification.

## Golden File Testing

Compare output against a known-good file in `testdata/`:

```go
func TestRender(t *testing.T) {
    got := render(input)
    golden := filepath.Join("testdata", t.Name()+".golden")

    if *update {
        os.WriteFile(golden, got, 0644)
        return
    }

    want, err := os.ReadFile(golden)
    if err != nil {
        t.Fatalf("reading golden file: %v", err)
    }
    if !bytes.Equal(got, want) {
        t.Errorf("output mismatch; run with -update to regenerate")
    }
}

var update = flag.Bool("update", false, "update golden files")
```

Run `go test -update` to regenerate golden files after intentional changes.

## Integration Test Isolation

### Using -short

```go
func TestDatabaseQuery(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test in short mode")
    }
    // ... test that requires a real database
}
```

Run unit tests only: `go test -short ./...`
Run everything: `go test ./...`

### Using Build Tags

Create a file `integration_test.go`:

```go
//go:build integration

package mypackage

func TestWithRealDB(t *testing.T) { ... }
```

Run: `go test -tags=integration ./...`

## HTTP Testing

```go
func TestHandler(t *testing.T) {
    handler := NewRouter()

    req := httptest.NewRequest("GET", "/users/42", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusOK {
        t.Errorf("status = %d, want %d", rec.Code, http.StatusOK)
    }
}
```

For tests that need an actual TCP listener:

```go
func TestAPI(t *testing.T) {
    srv := httptest.NewServer(NewRouter())
    t.Cleanup(srv.Close)

    resp, err := http.Get(srv.URL + "/health")
    // ...
}
```

## Black-Box vs White-Box Testing

- **Same package** (`package foo`): access unexported identifiers. Use for unit tests of internal logic.
- **Test package** (`package foo_test`): only sees exported API. Use for integration/behavior tests that exercise the public interface.

Both can coexist in the same directory. File naming does not determine this - the `package` declaration does.

## Coverage

```bash
go test -coverprofile=coverage.out ./...           # generate profile
go tool cover -func=coverage.out                   # per-function summary
go tool cover -html=coverage.out -o coverage.html  # HTML report
go test -coverpkg=./... ./...                      # include all packages, not just tested ones
```

Coverage measures line execution, not correctness. 100% coverage does not mean 100% tested - edge cases, error paths, and concurrency behavior all need targeted tests.

## Flaky Test Patterns

Common causes and fixes:

| Cause                     | Symptom                           | Fix                                                             |
| ------------------------- | --------------------------------- | --------------------------------------------------------------- |
| Time-dependent assertions | Pass/fail varies with system load | Use `testing/synctest` (1.24+) or inject a clock interface      |
| Goroutine ordering        | Intermittent wrong results        | Use channels or WaitGroup for synchronization, not `time.Sleep` |
| Port binding              | "address already in use"          | Use port 0 to get a random available port                       |
| Shared state              | Parallel tests interfere          | Isolate state per test; use `t.TempDir()` for files             |
| External service          | Network flakes                    | Mock at the HTTP layer with `httptest.NewServer`                |

Never use `time.Sleep` for synchronization in tests. It makes tests both slow and flaky.
