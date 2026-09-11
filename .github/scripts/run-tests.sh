#!/usr/bin/env bash
# Run the Python test suite of every plugin that has one.
set -euo pipefail

status=0
for suite in plugins/*/tests; do
  [ -d "$suite" ] || continue
  plugin=$(dirname "$suite")
  echo "== $plugin"
  (cd "$plugin" && python3 -m unittest discover -s tests -t . -v) || status=1
done
exit "$status"
