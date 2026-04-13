---
name: go-dev
description: >-
  Go development with toolchain-first verification workflow. Use whenever the
  user (1) writes, modifies, debugs, or reviews Go code, (2) works with go.mod,
  go.sum, or Go module dependencies, (3) writes or runs Go tests, benchmarks, or
  fuzz tests, (4) mentions go doc, go vet, go fix, go test, go build, go mod,
  gofmt, staticcheck, golangci-lint, govulncheck, or pprof, (5) asks about Go
  error handling (errors.Is/As/AsType/Join), concurrency (goroutines, channels,
  sync, context), interfaces, or package design, (6) encounters Go compiler
  errors, test failures, or race conditions, (7) profiles Go code for
  performance or works with PGO, (8) asks about Go best practices, code review,
  or idiomatic Go, (9) works with files ending in .go or _test.go, (10) wants
  to modernize Go code to 1.21-1.26 features. Trigger this skill proactively
  when the user is working in a Go codebase even if they do not explicitly ask
  for Go help - the toolchain-first workflow (verify APIs with go doc before
  coding, run go vet after) catches bugs that hallucinated signatures and
  skipped static analysis miss. Do NOT trigger for pure educational or
  comparative content about Go that does not involve writing or debugging code
  (e.g. tutorials for blog posts, Java vs Go decision documents, explanations
  of the Go scheduler for learning purposes).
---

# Go Development

## Session Init

At the start of any Go session, detect the project's Go version:

1. Read `go.mod` and extract the `go` directive (e.g., `go 1.26`)
2. This version controls which language features and stdlib APIs are available
3. If you are about to suggest a feature gated behind a newer version, stop and note the incompatibility

### Version Feature Table

| Version | Key additions                                                                                                                                                   |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.21    | `log/slog`, `slices`, `maps`, `min`/`max`/`clear` builtins, `context.AfterFunc`, `context.WithoutCancel`, `sync.OnceFunc`/`OnceValue`, PGO auto                 |
| 1.22    | `for i := range n`, `math/rand/v2`, enhanced `http.ServeMux` routing (method+pattern), loopvar semantic change                                                  |
| 1.23    | `iter.Seq`/`iter.Seq2`, range-over-func, `unique.Handle`, `structs.HostLayout`                                                                                  |
| 1.24    | `testing.T.Context`, `testing.T.Chdir`, `os.Root`, generic type aliases, `go tool` runs module tools, `testing/synctest`, `omitzero` JSON tag                   |
| 1.25    | `sync.WaitGroup.Go`, `testing.T.Attr`, `testing.T.Output`, `sync.Map` range-over-func, `os.OpenRoot`                                                            |
| 1.26    | `errors.AsType[T]`, `testing.T.ArtifactDir`, `go test -artifacts`, `go fix` command (21 fixers), new vet analyzers (waitgroup, hostport), `new(expr)` shorthand |

## Toolchain-First Workflow

This is the core of this skill. Go ships a powerful toolchain - use it instead of guessing.

### Before Writing Code

When about to use a stdlib or third-party API you are not certain about, verify the signature first:

```bash
go doc <package>.<Symbol>          # exact function/type/method
go doc -all <package>.<Type>       # full type with all methods
go doc -src <package>.<Symbol>     # source code when implementation matters
```

Token efficiency matters: `go doc fmt.Fprintf` returns 5 lines. `go doc fmt` returns hundreds. Always use the most specific query that answers your question.

For third-party packages, they must be importable (in go.mod) before `go doc` works. For stdlib, it always works.

### After Writing or Modifying Code

Pick the verification level that matches the scope of the change:

**Full** - new files, unfamiliar APIs, concurrency code, public interface changes:

```bash
gofmt -d .                              # format check (should produce no output)
go vet ./...                            # static analysis
go build ./...                          # compilation check
go test -race -count=1 ./...            # tests with race detector, cache bypassed
```

Or use the bundled script: `${CLAUDE_SKILL_DIR}/scripts/go-quality-check.sh ./...`

**Standard** - modifying existing code in patterns the project already uses:

```bash
go vet ./...
go test -count=1 -run TestRelevant ./path/to/pkg/...
```

**Light** - formatting, comments, documentation, renaming:

```bash
gofmt -d <changed-file>
```

### When Modernizing Code

Go 1.26 introduced `go fix`, which applies automated improvements:

```bash
go fix -diff ./...     # preview changes as unified diff
go fix ./...           # apply all fixes
```

This replaces patterns like `interface{}` with `any`, `sort.Slice` with `slices.Sort`, manual `wg.Add/Done` with `wg.Go`, and many more. Always preview with `-diff` first.

### When Debugging Test Failures

```bash
go test -v -run TestName -count=1 ./pkg/...    # verbose, cache-bypassed
go test -race -count=1 ./...                    # if concurrency is involved
go test -coverprofile=c.out ./... && go tool cover -func=c.out  # coverage gaps
```

### When Adding Dependencies

1. Prefer stdlib when the stdlib solution is adequate
2. Run `go doc` on the candidate package to verify its API before committing to it
3. `go get <module>@latest && go mod tidy`
4. `go mod why <module>` to verify it is actually used

## Tool Command Reference

### go doc

| Pattern                        | What it returns                     |
| ------------------------------ | ----------------------------------- |
| `go doc fmt`                   | Package synopsis                    |
| `go doc fmt.Fprintf`           | Specific function signature and doc |
| `go doc -all fmt.Stringer`     | Full type including all methods     |
| `go doc -src fmt.Fprintf`      | Source code of the function         |
| `go doc -short fmt`            | One-line per symbol                 |
| `go doc -u net/http.Transport` | Include unexported fields           |
| `go doc cmd/go`                | Go command documentation            |

### go vet analyzers (37 total)

| Analyzer       | What it catches                            |
| -------------- | ------------------------------------------ |
| `appends`      | Missing values after append                |
| `assign`       | Useless assignments                        |
| `atomic`       | Common sync/atomic mistakes                |
| `bools`        | Boolean operator mistakes                  |
| `buildtag`     | Invalid `//go:build` directives            |
| `composites`   | Unkeyed composite literals                 |
| `copylocks`    | Locks passed by value                      |
| `defers`       | Common defer mistakes                      |
| `errorsas`     | Wrong types passed to `errors.As`          |
| `hostport`     | Bad address format for `net.Dial`          |
| `httpresponse` | HTTP response handling mistakes            |
| `loopclosure`  | Loop variable capture in nested functions  |
| `lostcancel`   | Context cancel function not called         |
| `printf`       | Printf format string mismatches            |
| `shadow`       | Variable shadowing (via `-vettool`)        |
| `slog`         | Invalid structured logging calls           |
| `stdversion`   | Uses of too-new stdlib symbols             |
| `structtag`    | Malformed struct tags                      |
| `tests`        | Mistaken test/example/benchmark signatures |
| `unmarshal`    | Non-pointer passed to unmarshal            |
| `unusedresult` | Unused results from certain calls          |
| `waitgroup`    | Misuses of sync.WaitGroup                  |

(Run `go tool vet help` for the full list of all 37.)

### go fix fixers (21 total, Go 1.26+)

| Fixer              | What it modernizes                                          |
| ------------------ | ----------------------------------------------------------- |
| `any`              | `interface{}` -> `any`                                      |
| `fmtappendf`       | `[]byte(fmt.Sprintf(...))` -> `fmt.Appendf`                 |
| `forvar`           | Remove redundant loop variable re-declarations              |
| `mapsloop`         | Explicit map loops -> `maps` package calls                  |
| `minmax`           | if/else chains -> `min`/`max` builtins                      |
| `newexpr`          | Simplify with `new(expr)` (1.26)                            |
| `omitzero`         | `omitempty` -> `omitzero` for struct fields                 |
| `rangeint`         | 3-clause for -> `for i := range n`                          |
| `slicescontains`   | Loop searches -> `slices.Contains`                          |
| `slicessort`       | `sort.Slice` -> `slices.Sort`                               |
| `stringsbuilder`   | String concatenation `+=` -> `strings.Builder`              |
| `stringscut`       | `strings.Index` patterns -> `strings.Cut`                   |
| `stringscutprefix` | `HasPrefix`/`TrimPrefix` -> `CutPrefix`                     |
| `stringsseq`       | `Split`/`Fields` ranges -> `SplitSeq`/`FieldsSeq` iterators |
| `testingcontext`   | `context.WithCancel` in tests -> `t.Context()`              |
| `waitgroup`        | `wg.Add(1); go func() { defer wg.Done()... }` -> `wg.Go(f)` |

(Run `go tool fix help` for the full list.)

### go test key flags

| Flag                | Purpose                                                 |
| ------------------- | ------------------------------------------------------- |
| `-race`             | Enable race detector                                    |
| `-count=1`          | Bypass test cache                                       |
| `-run <regex>`      | Run only matching tests                                 |
| `-v`                | Verbose output                                          |
| `-short`            | Skip long-running tests (tests check `testing.Short()`) |
| `-shuffle=on`       | Randomize test order                                    |
| `-failfast`         | Stop on first failure                                   |
| `-cover`            | Enable coverage analysis                                |
| `-coverprofile=f`   | Write coverage profile to file                          |
| `-coverpkg=pattern` | Apply coverage to matching packages                     |
| `-bench=<regex>`    | Run matching benchmarks                                 |
| `-benchmem`         | Report allocations in benchmarks                        |
| `-benchtime=5s`     | Benchmark duration                                      |
| `-fuzz=<regex>`     | Run matching fuzz tests                                 |
| `-timeout=10m`      | Test timeout (default 10m)                              |
| `-cpuprofile=f`     | Write CPU profile                                       |
| `-memprofile=f`     | Write memory profile                                    |
| `-artifacts`        | Store test artifacts in output directory (1.26+)        |

### go build key flags

| Flag                              | Purpose                                               |
| --------------------------------- | ----------------------------------------------------- |
| `-race`                           | Enable race detector                                  |
| `-pgo=auto`                       | Profile-guided optimization (auto uses `default.pgo`) |
| `-gcflags='-m'`                   | Show escape analysis                                  |
| `-gcflags='-S'`                   | Show assembly output                                  |
| `-ldflags='-s -w'`                | Strip debug info (smaller binary)                     |
| `-ldflags='-X main.version=v1.0'` | Embed build-time values                               |
| `-trimpath`                       | Remove filesystem paths from binary                   |
| `-tags=<list>`                    | Build constraint tags                                 |
| `-o <file>`                       | Output file path                                      |

### go mod subcommands

| Command                | Purpose                          |
| ---------------------- | -------------------------------- |
| `go mod tidy`          | Sync go.mod/go.sum with imports  |
| `go mod download`      | Download modules to cache        |
| `go mod graph`         | Print module dependency graph    |
| `go mod vendor`        | Create vendored copy             |
| `go mod verify`        | Verify dependencies match go.sum |
| `go mod why <mod>`     | Explain why a module is needed   |
| `go mod edit -go=1.26` | Update go directive              |

### gofmt flags

| Flag | Purpose                                |
| ---- | -------------------------------------- |
| `-d` | Print diff (do not modify files)       |
| `-l` | List files with formatting differences |
| `-s` | Simplify code                          |
| `-w` | Write changes to files                 |

### External tools

Check availability before use. These are not part of the Go toolchain:

| Tool            | Check                 | Purpose                                     |
| --------------- | --------------------- | ------------------------------------------- |
| `staticcheck`   | `which staticcheck`   | Extended static analysis beyond go vet      |
| `golangci-lint` | `which golangci-lint` | Meta-linter running 100+ linters            |
| `govulncheck`   | `which govulncheck`   | Scan dependencies for known vulnerabilities |

If unavailable, `go vet` covers the most critical checks. Do not block on missing external tools.

## Common Diagnostics

| Diagnostic                                        | Cause                                   | Fix                                                                        | Reference                             |
| ------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------- |
| `declared and not used`                           | Unused variable                         | Remove it or use it                                                        | -                                     |
| `imported and not used`                           | Unused import                           | Remove import; use `_` alias only during active development                | -                                     |
| `cannot use X as type Y`                          | Type mismatch                           | Run `go doc` on both types; check interface satisfaction                   | `references/interfaces-and-design.md` |
| `data race detected`                              | Concurrent unsynchronized access        | Use mutex, channel, or atomic; see concurrency patterns                    | `references/concurrency.md`           |
| `err is shadowed during return`                   | `:=` in inner scope shadows outer `err` | Use `=` instead of `:=` or rename inner variable                           | `references/error-handling.md`        |
| `loop variable X captured by func literal`        | Pre-1.22 loop var capture               | Go 1.22+ fixes this; for older: copy variable before closure               | -                                     |
| `possible misuse of sync.WaitGroup`               | `Add` called inside goroutine           | Call `Add` before starting goroutine, not inside it                        | `references/concurrency.md`           |
| `context.Background used in long-lived operation` | Missing context propagation             | Accept `context.Context` as first parameter; pass from caller              | `references/concurrency.md`           |
| `go directive in go.mod too old`                  | go.mod version < required feature       | Run `go mod edit -go=<version>` to update                                  | `references/modules-and-deps.md`      |
| Any `ioutil.*` usage                              | Deprecated since Go 1.16                | `ioutil.ReadAll` -> `io.ReadAll`; `ioutil.ReadFile` -> `os.ReadFile`; etc. | `references/modern-go.md`             |
| HTTP handler decodes body without size limit      | DoS via unbounded request body          | Wrap `r.Body` with `http.MaxBytesReader(w, r.Body, maxBytes)`              | `references/security.md`              |
| `http.Server{}` without timeouts                  | Vulnerable to slowloris attacks         | Set `ReadTimeout`, `WriteTimeout`, `IdleTimeout`                           | `references/security.md`              |

## Proactive Behaviors

These are the rules for when to use tools without being asked:

- **Verify before asserting**: run `go doc <pkg>.<Symbol>` before claiming any API signature you have not used in this session. This is the single most important behavior - wrong signatures waste the user's time.
- **Vet after structural changes**: run `go vet ./...` after creating new files, adding exported functions, or modifying concurrency code.
- **Format check before done**: run `gofmt -d <file>` before presenting code as complete. If it produces output, the code has formatting issues.
- **Race detection for concurrency**: run `go test -race -count=1 ./...` after modifying code involving goroutines, channels, shared state, or sync primitives.
- **Version gate features**: check the `go` directive in `go.mod` before suggesting features from newer versions. Use the version feature table above.
- **Modernize with go fix**: when reviewing existing code, run `go fix -diff ./...` to identify modernization opportunities. Present the diff to the user before applying.
- **Never suggest deprecated APIs**: `ioutil` (deprecated 1.16), `math/rand.Seed` (unnecessary since 1.20), `// +build` (replaced by `//go:build`).
- **Prefer errors.Is/As/AsType**: over type assertions or string matching on errors. Use `errors.AsType[T]` on Go 1.26+.
- **Limit HTTP request bodies**: when writing HTTP handlers that decode request bodies, always use `http.MaxBytesReader` to prevent denial-of-service via unbounded uploads. This is easy to forget and hard to catch in code review.
- **Set HTTP server timeouts**: when creating `http.Server`, always set `ReadTimeout`, `WriteTimeout`, and `IdleTimeout`. A server without timeouts is vulnerable to slowloris attacks.

When NOT to run tools:

- Do not run `go test` when only editing comments or documentation
- Do not run `go vet` when the user is just asking a question, not writing code
- Do not run `go doc` for universally known functions (`fmt.Println`, `len`, `append`, etc.)

## Idiomatic Go Principles

These are the philosophical foundations. When reviewing or writing Go code, apply these as judgment calls, not rigid rules:

- **Clear is better than clever.** Readable code is maintainable code. Prefer explicit control flow over clever one-liners.
- **Accept interfaces, return structs.** Functions should accept the smallest interface that satisfies their needs and return concrete types. This maximizes flexibility for callers and clarity for the API.
- **Define interfaces at the consumer, not the provider.** The package that uses an interface should define it, keeping it as small as needed.
- **Errors are values.** Handle them, don't ignore them. Wrap with context using `fmt.Errorf("doing X: %w", err)`. See `references/error-handling.md`.
- **Make the zero value useful.** Design types so their zero value is valid and usable (e.g., `sync.Mutex`, `bytes.Buffer`).
- **Composition over inheritance.** Use struct embedding for reuse, not deep hierarchies.
- **Keep packages focused.** Organize by domain, not by layer. A `user` package, not a `models` package.
- **defer for cleanup.** Place `defer` immediately after acquiring a resource. It communicates cleanup intent right where the resource is opened.
- **Unexported by default.** Export only what is part of the public API. Unexported symbols can be changed freely.
- **Pointer vs value receivers.** Be consistent per type. Use value receivers for small, immutable types. Use pointer receivers for mutation or large structs. A type with any pointer receiver should use pointer receivers everywhere.

## Reference Router

Open the reference file that matches the question. Load only one at a time.

### Foundations

- **Error handling** (wrapping, sentinel errors, error types, `errors.Is`/`As`/`AsType`, `errors.Join`) -> `references/error-handling.md`
- **Concurrency** (goroutines, channels, sync primitives, context, patterns, pitfalls) -> `references/concurrency.md`
- **Testing** (table tests, subtests, benchmarks, fuzzing, golden files, coverage, helpers) -> `references/testing.md`

### Modern Go

- **Version-gated features** (1.21-1.26 features, deprecated patterns, `go fix` guide) -> `references/modern-go.md`

### Applied Topics

- **Performance** (profiling, pprof, PGO, escape analysis, benchstat, allocation reduction) -> `references/performance.md`
- **Interface and API design** (small interfaces, composition, functional options, generics) -> `references/interfaces-and-design.md`
- **Modules and dependencies** (go.mod, versioning, workspace mode, vendoring) -> `references/modules-and-deps.md`
- **Security** (input validation, SQL injection, path traversal, TLS, crypto, govulncheck) -> `references/security.md`

For a problem-based router ("I need to..."), see `references/_index.md`.

## Verification Checklist

Before declaring work done on Go code:

1. `gofmt -d .` produces no output
2. `go vet ./...` produces no diagnostics
3. `go build ./...` succeeds
4. `go test -race -count=1 ./...` passes
5. No deprecated patterns (`ioutil`, `math/rand.Seed`, `// +build`)
6. Error values wrapped with `%w` where callers need `errors.Is`/`errors.As`
7. Exported functions and types have doc comments
8. `context.Context` is threaded through where cancellation matters
9. HTTP handlers use `http.MaxBytesReader` for request body limits
10. HTTP servers have `ReadTimeout`, `WriteTimeout`, `IdleTimeout` set
11. `go mod tidy` has been run if dependencies changed
