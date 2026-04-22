#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: go-quality-check.sh [PACKAGES] [--skip-test] [--verbose] [--short]

Run the full Go verification pipeline in sequence: gofmt, go vet,
staticcheck (if installed), go build, go test -race. Stops on the first
failure with a clear message about which step failed.

Arguments:
  PACKAGES       Package pattern to check (default: ./...)

Flags:
  --skip-test    Skip the go test step
  --verbose      Pass -v to go test
  --short        Pass -short to go test
  -h, --help     Show this help and exit

Examples:
  go-quality-check.sh
  go-quality-check.sh ./pkg/... --short
  go-quality-check.sh --skip-test --verbose
EOF
}

PACKAGES=""
SKIP_TEST=false
VERBOSE=""
SHORT=""

for arg in "$@"; do
    case "$arg" in
        -h|--help)   usage; exit 0 ;;
        --skip-test) SKIP_TEST=true ;;
        --verbose)   VERBOSE="-v" ;;
        --short)     SHORT="-short" ;;
        -*)          echo "Unknown flag: $arg" >&2; usage >&2; exit 1 ;;
        *)           PACKAGES="$arg" ;;
    esac
done

PACKAGES="${PACKAGES:-./...}"

step() {
    echo "==> $1"
}

fail() {
    echo ""
    echo "FAILED: $1" >&2
    exit 1
}

# Step 1: Format check
step "Checking formatting (gofmt -d)"
FMT_OUTPUT=$(gofmt -d . 2>&1) || true
if [ -n "$FMT_OUTPUT" ]; then
    echo "$FMT_OUTPUT"
    fail "gofmt found formatting differences. Run 'gofmt -w .' to fix."
fi

# Step 2: Static analysis
step "Running go vet $PACKAGES"
go vet "$PACKAGES" || fail "go vet found issues"

# Step 3: staticcheck (optional - skip if not installed)
if command -v staticcheck &>/dev/null; then
    step "Running staticcheck $PACKAGES"
    staticcheck "$PACKAGES" || fail "staticcheck found issues"
else
    step "Skipping staticcheck (not installed)"
fi

# Step 4: Build check
step "Checking compilation (go build $PACKAGES)"
go build "$PACKAGES" || fail "go build failed"

# Step 5: Tests (unless --skip-test)
if [ "$SKIP_TEST" = true ]; then
    step "Skipping tests (--skip-test)"
else
    TEST_FLAGS="-race -count=1"
    [ -n "$VERBOSE" ] && TEST_FLAGS="$TEST_FLAGS $VERBOSE"
    [ -n "$SHORT" ] && TEST_FLAGS="$TEST_FLAGS $SHORT"
    step "Running go test $TEST_FLAGS $PACKAGES"
    # shellcheck disable=SC2086
    go test $TEST_FLAGS "$PACKAGES" || fail "go test failed"
fi

echo ""
echo "All checks passed."
