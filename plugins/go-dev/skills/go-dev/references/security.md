# Security

## SQL Injection Prevention

Always use parameterized queries. Never interpolate user input into SQL strings:

```go
// BAD - SQL injection
query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userInput)
rows, err := db.Query(query)

// GOOD - parameterized query
rows, err := db.QueryContext(ctx, "SELECT * FROM users WHERE id = $1", userID)
```

This applies to all database operations: `Query`, `QueryRow`, `Exec`. The placeholder syntax varies by driver (`$1` for PostgreSQL, `?` for MySQL/SQLite).

For dynamic column or table names (which cannot be parameterized), validate against an allowlist:

```go
validColumns := map[string]bool{"name": true, "email": true, "created_at": true}
if !validColumns[sortColumn] {
    return fmt.Errorf("invalid sort column: %q", sortColumn)
}
query := fmt.Sprintf("SELECT * FROM users ORDER BY %s", sortColumn)
```

## Path Traversal Prevention

User-supplied file paths can escape intended directories:

```go
// BAD - user can pass "../../etc/passwd"
path := filepath.Join(baseDir, userInput)
data, err := os.ReadFile(path)

// BETTER - clean and verify the path stays within baseDir
cleaned := filepath.Clean(filepath.Join(baseDir, userInput))
if !strings.HasPrefix(cleaned, filepath.Clean(baseDir)+string(os.PathSeparator)) {
    return fmt.Errorf("path traversal attempt: %q", userInput)
}

// BEST (Go 1.24+) - os.Root enforces directory boundary
root, err := os.OpenRoot(baseDir)
if err != nil {
    return err
}
defer root.Close()
f, err := root.Open(userInput)  // cannot escape baseDir
```

`os.Root` (Go 1.24+) is the safest approach - the kernel enforces the boundary, not string checks.

## TLS Configuration

```go
tlsConfig := &tls.Config{
    MinVersion: tls.VersionTLS12,  // TLS 1.2 minimum
    // Do NOT set InsecureSkipVerify: true in production
}

server := &http.Server{
    TLSConfig: tlsConfig,
    // ...
}
```

Common mistakes:

- `InsecureSkipVerify: true` - disables certificate verification. Only for local testing, never production.
- Omitting `MinVersion` - defaults to TLS 1.0 which has known vulnerabilities.
- Custom `CipherSuites` - the Go defaults are well-chosen. Override only if compliance requires it.

## Cryptography

### Random values

```go
// GOOD - cryptographically secure
import "crypto/rand"
token := make([]byte, 32)
_, err := crypto_rand.Read(token)

// BAD - predictable, not for security
import "math/rand"
token := rand.Int()  // do not use for tokens, secrets, or keys
```

### Password hashing

```go
import "golang.org/x/crypto/bcrypt"

// Hashing
hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)

// Verification
err := bcrypt.CompareHashAndPassword(hash, []byte(password))
if err != nil {
    // wrong password
}
```

Never store passwords in plain text. Never use MD5, SHA-1, or SHA-256 for password hashing - they are too fast for this purpose (brute-force friendly).

## HTTP Server Security

### Timeouts

An `http.Server` without timeouts is vulnerable to slowloris attacks:

```go
server := &http.Server{
    Addr:         ":8080",
    ReadTimeout:  5 * time.Second,
    WriteTimeout: 10 * time.Second,
    IdleTimeout:  120 * time.Second,
}
```

### Request body limits

Prevent clients from sending unbounded request bodies:

```go
func handler(w http.ResponseWriter, r *http.Request) {
    r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1MB limit
    err := json.NewDecoder(r.Body).Decode(&payload)
    if err != nil {
        // MaxBytesError if body exceeds limit
    }
}
```

### CORS and security headers

```go
func securityHeaders(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("X-Content-Type-Options", "nosniff")
        w.Header().Set("X-Frame-Options", "DENY")
        w.Header().Set("Content-Security-Policy", "default-src 'self'")
        next.ServeHTTP(w, r)
    })
}
```

## Secrets Management

- Never hardcode secrets in source code
- Never log secrets (tokens, passwords, API keys)
- Use environment variables or a secrets manager
- Use `.gitignore` to exclude config files with secrets

```go
apiKey := os.Getenv("API_KEY")
if apiKey == "" {
    log.Fatal("API_KEY environment variable is required")
}
```

## Vulnerability Scanning

`govulncheck` scans your code and dependencies for known vulnerabilities:

```bash
govulncheck ./...
```

It only reports vulnerabilities in code paths your program actually calls (not just any vulnerability in a dependency). This reduces false positives compared to generic dependency scanners.

Run it in CI to catch vulnerabilities early:

```bash
go install golang.org/x/vuln/cmd/govulncheck@latest
govulncheck ./...
```

## Race Conditions as Security Bugs

Data races are not just correctness issues - they can be security vulnerabilities:

- TOCTOU (Time-of-Check-Time-of-Use): checking a permission then acting on it without atomicity
- Double-spend: processing the same request twice due to unsynchronized state
- Authentication bypass: race on session validation

Always run tests with `-race` in CI:

```bash
go test -race ./...
```

## Input Validation

Validate at system boundaries (HTTP handlers, CLI argument parsing, file readers), not deep inside business logic:

```go
func (h *Handler) CreateUser(w http.ResponseWriter, r *http.Request) {
    var req CreateUserRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "invalid JSON", http.StatusBadRequest)
        return
    }
    if err := req.Validate(); err != nil {
        http.Error(w, err.Error(), http.StatusBadRequest)
        return
    }
    // From here on, req is trusted
    user, err := h.service.CreateUser(r.Context(), req)
    // ...
}
```

Internal function calls between trusted packages do not need redundant validation.
