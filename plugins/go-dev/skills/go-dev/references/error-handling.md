# Error Handling

Go's error model is explicit: errors are values returned from functions, not exceptions thrown across stack frames. This makes error paths visible and forces callers to decide what to do.

## The Three Error Representations

Choose based on what callers need to do with the error:

### Sentinel Errors

Package-level `var` values. Use when callers need to check for a specific condition using `errors.Is`.

```go
var ErrNotFound = errors.New("not found")
var ErrPermission = errors.New("permission denied")
```

Naming convention: `Err` prefix + condition. These are values, not types.

When to use: the error carries no additional data beyond "this condition occurred." Examples: `io.EOF`, `sql.ErrNoRows`, `context.Canceled`.

### Error Types

Custom types implementing `error`. Use when callers need to extract structured data using `errors.As` or `errors.AsType`.

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}
```

Naming convention: descriptive name + `Error` suffix.

When to use: the error carries data callers need to act on (field name, status code, retry-after duration).

### Wrapped Errors (Most Common)

Errors enriched with context using `fmt.Errorf` and `%w`. This is the default choice.

```go
func ReadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("reading config %s: %w", path, err)
    }
    // ...
}
```

The `%w` verb wraps the original error, preserving the chain for `errors.Is`/`errors.As`.

## Wrapping: %w vs %v

- **`%w`** (wrap): use inside your module/package. Preserves the error chain so callers can inspect causes with `errors.Is`/`errors.As`.
- **`%v`** (format only): use at API boundaries where you do not want to expose internal error types to external consumers. The original error becomes part of the message string but is not inspectable.

```go
// Internal - wrap to preserve chain
return fmt.Errorf("querying user %d: %w", id, err)

// API boundary - format only, hide internal types
return fmt.Errorf("user lookup failed: %v", err)
```

## Inspecting Errors

### errors.Is (check identity)

Walks the error chain looking for a match with a target value:

```go
if errors.Is(err, sql.ErrNoRows) {
    return nil, ErrNotFound
}
```

Never compare errors with `==` directly - it breaks on wrapped errors.

### errors.As (extract type)

Walks the chain looking for an error matching a target type:

```go
var ve *ValidationError
if errors.As(err, &ve) {
    log.Printf("field %s failed: %s", ve.Field, ve.Message)
}
```

### errors.AsType[T] (Go 1.26+)

Generic version of `errors.As` - cleaner, no need for a pre-declared variable:

```go
if ve, ok := errors.AsType[*ValidationError](err); ok {
    log.Printf("field %s failed: %s", ve.Field, ve.Message)
}
```

Prefer `errors.AsType` on Go 1.26+ projects. It avoids the pointer-to-interface pitfall that `errors.As` is prone to.

## Combining Errors: errors.Join (Go 1.20+)

When multiple operations can fail independently and you want to report all of them:

```go
var errs []error
for _, item := range items {
    if err := validate(item); err != nil {
        errs = append(errs, err)
    }
}
if err := errors.Join(errs...); err != nil {
    return err
}
```

The joined error supports `errors.Is` and `errors.As` across all constituent errors.

## Custom Unwrap

For custom error types that wrap other errors:

```go
// Single wrapped error
type QueryError struct {
    Query string
    Err   error
}

func (e *QueryError) Unwrap() error { return e.Err }

// Multiple wrapped errors (Go 1.20+)
type MultiError struct {
    Errors []error
}

func (e *MultiError) Unwrap() []error { return e.Errors }
```

## Error Categorization

Understanding whether an error is transient or permanent matters for retry decisions:

**Transient** (may succeed on retry): network timeout, temporary unavailability, rate limiting, connection reset.

**Permanent** (will never succeed): invalid input, permission denied, resource not found, schema violation.

Pattern for communicating this:

```go
type TemporaryError interface {
    Temporary() bool
}

// Or use sentinel wrapping:
var ErrTemporary = errors.New("temporary")

func fetchData(ctx context.Context, url string) ([]byte, error) {
    resp, err := http.Get(url)
    if err != nil {
        return nil, fmt.Errorf("%w: %w", ErrTemporary, err)
    }
    // ...
}

// Caller:
if errors.Is(err, ErrTemporary) {
    // retry with backoff
}
```

## The Single-Handling Rule

Handle an error exactly once. Either:

- **Return it** (with wrapping context) for the caller to handle, OR
- **Handle it** (log, retry, degrade gracefully) and do not propagate it

Never log-and-return - this results in duplicate log entries and confused error handling:

```go
// BAD: log and return
if err != nil {
    log.Printf("failed: %v", err)  // logged here...
    return err                      // ...and the caller logs it again
}

// GOOD: return with context
if err != nil {
    return fmt.Errorf("fetching user %d: %w", id, err)
}

// GOOD: handle and stop propagation
if err != nil {
    log.Printf("non-critical: falling back to cache: %v", err)
    return cachedValue, nil
}
```

## Anti-Patterns

**String matching on errors** - fragile, breaks on any message change:

```go
// BAD
if strings.Contains(err.Error(), "not found") { ... }

// GOOD
if errors.Is(err, ErrNotFound) { ... }
```

**Using errors.New for programmatic checking** - creates a new value each time:

```go
// BAD - each call creates a different value, errors.Is will never match
func doThing() error {
    return errors.New("thing failed")
}

// GOOD - sentinel at package level
var ErrThingFailed = errors.New("thing failed")
```

**Bare return without context** - impossible to trace in logs:

```go
// BAD
return err

// GOOD
return fmt.Errorf("saving order %s: %w", orderID, err)
```

**Ignoring errors with `_`** - only acceptable when the function documents it is safe to ignore:

```go
// BAD - silently drops the error
_ = db.Close()

// GOOD - if you truly want to ignore, document why
_ = w.Close() // best-effort; response already sent
```

## Error Messages

- Start with lowercase (they may be wrapped in a chain)
- No trailing punctuation
- Include relevant identifiers (user ID, file path, operation name)
- Keep cardinality low for observability (don't embed unique request IDs in the message; put those in structured log fields)

```go
// Good error messages:
"reading config: %w"
"querying user %d: %w"
"connecting to %s:%d: %w"

// Bad error messages:
"Error: Failed to read config file."   // uppercase, punctuation, verbose
"error at 2024-01-15T10:30:00Z"        // timestamp belongs in logs, not errors
```
