# Modules and Dependencies

## go.mod Anatomy

```
module github.com/user/project

go 1.26

require (
    github.com/lib/pq v1.10.9
    golang.org/x/sync v0.7.0
)

require (
    // indirect dependencies (managed by go mod tidy)
    golang.org/x/text v0.16.0 // indirect
)

tool (
    golang.org/x/tools/cmd/stringer
)

retract v1.0.0  // accidental publish with broken API
```

### Key Directives

| Directive | Purpose                                                                     |
| --------- | --------------------------------------------------------------------------- |
| `module`  | Module path (import path prefix for all packages)                           |
| `go`      | Minimum Go version required; controls language features available           |
| `require` | Dependencies and their versions                                             |
| `replace` | Redirect a module to a different path or version (local development, forks) |
| `exclude` | Skip a specific version (force upgrade past a known-bad release)            |
| `retract` | Mark versions of your own module as not recommended                         |
| `tool`    | Tools to install with `go install` (Go 1.24+)                               |

## Common Operations

### Adding a dependency

```bash
go get github.com/lib/pq@latest        # add or update to latest
go get github.com/lib/pq@v1.10.9       # pin to specific version
go mod tidy                              # sync go.mod/go.sum with actual imports
```

### Removing a dependency

Remove the import from your code, then:

```bash
go mod tidy
```

### Updating dependencies

```bash
go get -u ./...              # update all direct dependencies to latest minor/patch
go get -u=patch ./...        # update to latest patch only
go list -m -u all            # check for available updates without applying
```

### Understanding dependency graph

```bash
go mod why github.com/lib/pq           # why is this module needed?
go mod graph                             # full dependency tree
go mod graph | grep github.com/lib/pq  # filter for specific module
```

### Verifying integrity

```bash
go mod verify   # check that dependencies on disk match go.sum
```

## go.sum

`go.sum` is a checksum database that ensures reproducible builds. It contains hashes of module zip files and their go.mod files.

- Always commit `go.sum` to version control
- Never edit it manually
- The Go checksum database (`sum.golang.org`) verifies these hashes by default

## Minimum Version Selection (MVS)

Go's dependency resolution algorithm. Unlike other package managers that pick the newest compatible version, Go picks the **minimum** version that satisfies all requirements.

This means: if module A requires `foo v1.2.0` and module B requires `foo v1.3.0`, Go selects `foo v1.3.0` (the minimum that satisfies both). It will never pick `v1.4.0` unless explicitly requested.

Consequence: `go get -u` is the only way to get newer versions. Without it, builds are deterministic and do not change when new versions are published.

## Workspace Mode (go.work)

For developing multiple modules simultaneously:

```bash
go work init ./api ./worker ./shared
```

Creates `go.work`:

```
go 1.26

use (
    ./api
    ./worker
    ./shared
)
```

Now changes in `./shared` are immediately visible to `./api` and `./worker` without publishing.

Rules:

- `go.work` is for local development. Do not commit it (add to `.gitignore`).
- `go.work.sum` is the workspace equivalent of `go.sum`.
- CI/CD should use `go.mod`, not `go.work`.

## Vendoring

Copies all dependencies into a `vendor/` directory for offline/hermetic builds:

```bash
go mod vendor           # create/update vendor directory
go build -mod=vendor    # build using vendored dependencies
```

When to vendor:

- Compliance requirements mandate auditable dependencies
- Air-gapped build environments with no network access
- You want protection against dependency disappearance (left-pad scenario)

When not to vendor:

- Most projects - the module proxy (`proxy.golang.org`) caches modules reliably
- Large dependency trees where vendor/ bloats the repository

## Private Modules

For modules hosted on private infrastructure:

```bash
# Skip the public proxy and checksum database for private paths
export GOPRIVATE="github.com/mycompany/*,git.internal.example.com/*"
```

`GOPRIVATE` sets both `GONOSUMCHECK` (skip checksum verification) and `GONOPROXY` (download directly, skip proxy) for matching paths.

For fine-grained control:

```bash
export GONOSUMCHECK="github.com/mycompany/*"   # skip checksum only
export GONOPROXY="github.com/mycompany/*"       # skip proxy only
```

Git authentication for private repos:

```bash
git config --global url."ssh://git@github.com/mycompany".insteadOf "https://github.com/mycompany"
```

## Updating the Go Directive

The `go` directive controls which language features are available:

```bash
go mod edit -go=1.26    # update to Go 1.26
go mod tidy              # may update indirect dependencies
```

The `go` directive does NOT require the Go toolchain to match. You can have `go 1.26` in go.mod and build with Go 1.26.2 toolchain. The directive is a minimum language version, not a toolchain pin.

## Retraction

Mark a version of your own module as not recommended:

```go
// In go.mod:
retract (
    v1.0.0  // accidental publish, broken API
    [v1.1.0, v1.2.0]  // range of bad versions
)
```

Retracted versions still exist but `go get` will skip them when resolving `@latest`.

## Quick Reference

| Task                   | Command                      |
| ---------------------- | ---------------------------- |
| Add dependency         | `go get <module>@<version>`  |
| Remove unused          | `go mod tidy`                |
| Check why needed       | `go mod why <module>`        |
| See dependency tree    | `go mod graph`               |
| Verify checksums       | `go mod verify`              |
| Update all             | `go get -u ./...`            |
| Update patch only      | `go get -u=patch ./...`      |
| List available updates | `go list -m -u all`          |
| Vendor dependencies    | `go mod vendor`              |
| Init workspace         | `go work init ./mod1 ./mod2` |
| Update go version      | `go mod edit -go=1.26`       |
