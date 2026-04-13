# Interfaces and API Design

## Accept Interfaces, Return Structs

This is the most important Go API design principle. Functions should:

- **Accept** the smallest interface that satisfies their needs (maximizes what callers can pass in)
- **Return** concrete types (maximizes what callers can do with the result)

```go
// GOOD - accepts io.Reader (any data source), returns concrete type
func ParseConfig(r io.Reader) (*Config, error) { ... }

// BAD - accepts concrete type (limits callers to files only)
func ParseConfig(f *os.File) (*Config, error) { ... }

// BAD - returns interface (hides what caller actually gets)
func NewService() ServiceInterface { ... }

// GOOD - returns concrete type
func NewService() *Service { ... }
```

Why return concrete types? The caller can always assign a concrete type to an interface variable. But an interface return type hides available methods and makes the API harder to use.

Exception: return an interface when the concrete type must vary (factory functions, plugin systems).

## Small Interfaces

Go's best interfaces are tiny. The stdlib models this:

```go
type Reader interface { Read(p []byte) (n int, err error) }
type Writer interface { Write(p []byte) (n int, err error) }
type Stringer interface { String() string }
type Error interface { Error() string }
```

A one-method interface can be satisfied by almost anything. A ten-method interface is basically a concrete type in disguise.

Guideline: if your interface has more than 3-4 methods, consider whether it is actually describing a contract or just mirroring a struct.

## Define Interfaces at the Consumer

The package that needs the interface should define it, not the package that implements it:

```go
// package repository - provides the concrete type
type UserRepository struct { db *sql.DB }
func (r *UserRepository) FindByID(ctx context.Context, id int64) (*User, error) { ... }
func (r *UserRepository) Save(ctx context.Context, u *User) error { ... }

// package service - defines the interface it needs
type UserStore interface {
    FindByID(ctx context.Context, id int64) (*User, error)
    Save(ctx context.Context, u *User) error
}

type UserService struct {
    store UserStore  // depends on the interface, not the concrete type
}
```

This inverts the dependency: the service package does not import the repository package. Testing becomes trivial - implement the interface with a fake or mock.

## Composition via Embedding

Go uses embedding instead of inheritance. Embed interfaces or structs to compose behavior:

```go
// Interface embedding
type ReadWriter interface {
    io.Reader
    io.Writer
}

// Struct embedding
type Server struct {
    http.Server          // embeds all http.Server methods
    logger *slog.Logger  // additional field
}
```

Embedding promotes the embedded type's methods to the outer type. The outer type satisfies any interface the embedded type satisfies.

Be deliberate: embedding exposes the entire method set of the embedded type. If you only need a few methods, use a named field instead and write forwarding methods.

## Pointer vs Value Receivers

### Consistency Rule

If any method on a type uses a pointer receiver, all methods should use pointer receivers. Mixing is confusing and creates subtle interface satisfaction issues.

### When to Use Each

**Value receiver** (`func (t T) Method()`):

- Type is small (a few words or less)
- Type is immutable (methods do not modify state)
- Type is a map, func, or channel (already reference types)

**Pointer receiver** (`func (t *T) Method()`):

- Method modifies the receiver
- Type is large (copying would be expensive)
- Type contains a sync.Mutex or similar (must not be copied)

### Interface Satisfaction

A value of type `T` can call methods with value receivers.
A value of type `*T` can call methods with both value and pointer receivers.

This means: if an interface method is defined with a pointer receiver, only `*T` satisfies the interface, not `T`.

```go
type Sizer interface { Size() int }

type Data struct { n int }
func (d *Data) Size() int { return d.n }  // pointer receiver

var s Sizer = Data{}   // COMPILE ERROR: Data does not implement Sizer
var s Sizer = &Data{}  // OK
```

## Constructor Pattern

Use `NewXxx` functions to create instances:

```go
func NewServer(addr string, opts ...Option) *Server {
    s := &Server{addr: addr, timeout: 30 * time.Second}
    for _, opt := range opts {
        opt(s)
    }
    return s
}
```

Do not use `init()` for construction. Constructors are explicit and testable.

## Functional Options

For constructors with many optional parameters:

```go
type Option func(*Server)

func WithTimeout(d time.Duration) Option {
    return func(s *Server) { s.timeout = d }
}

func WithLogger(l *slog.Logger) Option {
    return func(s *Server) { s.logger = l }
}

// Usage:
srv := NewServer(":8080",
    WithTimeout(60*time.Second),
    WithLogger(logger),
)
```

Advantages over a config struct:

- Self-documenting at the call site
- Options can validate and have defaults
- Backward-compatible: new options do not break existing callers

Use a config struct instead when there are many required fields or when the configuration needs to be serialized.

## Package Organization

### By Domain, Not Layer

```
// BAD - organized by layer
models/
controllers/
services/
repositories/

// GOOD - organized by domain
user/       // user.go, user_service.go, user_store.go
order/      // order.go, order_service.go, order_store.go
auth/       // auth.go, token.go, middleware.go
```

Domain packages are self-contained. Layer packages create circular dependency nightmares.

### internal/ for Implementation Hiding

```
mymodule/
    api/           // public API
    internal/      // importable only within mymodule
        cache/
        worker/
```

Code in `internal/` cannot be imported by packages outside the parent of `internal/`. Use this to hide implementation details from consumers of your module.

### Package Naming

- Short, lowercase, single word: `http`, `user`, `auth`
- No `util`, `common`, `misc` - these are junk drawers that grow without limit
- Package name is part of the qualified identifier: `user.New()` not `user.NewUser()`

## Generics: When to Use

Generics (Go 1.18+) are valuable when:

- You are writing the same logic for multiple types (sort, filter, map, contains)
- Type safety matters more than the flexibility of `any`
- The stdlib already uses generics for the pattern (`slices`, `maps`, `cmp`)

Generics are not needed when:

- An interface already solves the problem (`io.Reader`, `fmt.Stringer`)
- There is only one concrete type (generics add complexity for no benefit)
- You are writing application code, not library code (most application types are concrete)

```go
// Good use of generics - works for any ordered type
func Max[T cmp.Ordered](a, b T) T {
    if a > b { return a }
    return b
}

// Unnecessary generic - just use the concrete type
func ProcessOrders[T Order](orders []T) { ... }  // if there's only one Order type
func ProcessOrders(orders []Order) { ... }        // simpler, clearer
```

Prefer `any` over `interface{}` since Go 1.18. They are identical but `any` is idiomatic.
