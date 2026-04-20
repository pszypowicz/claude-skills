---
description: Print teardown commands for the current Claude session's worktrees
argument-hint: [session-id-override]
---

Print the exact shell commands needed to tear down every worktree this session has materialized. Do not execute them yourself - the user runs them after confirming.

Steps:

1. Resolve the current session-id (see "Session id resolver" below). If `$ARGUMENTS` is non-empty, use it as an override to clean up a different session's worktrees.
2. Worktree root: `~/Developer/.worktrees/<session-id>/`. If it doesn't exist or is empty, say so and stop.
3. Find each inner worktree - a worktree has a `.git` **file** (not directory) at its root:

   ```bash
   find ~/Developer/.worktrees/<session-id> -maxdepth 8 -name .git -type f -print
   ```

4. For each worktree `<wt>` (parent of the `.git` file):
   - Compute the origin clone path: strip the `~/Developer/.worktrees/<session-id>/` prefix, re-root at `~/Developer/`. Verify by reading the `gitdir` line in `<wt>/.git` - it points to `<origin>/.git/worktrees/<name>`.
   - Check `git -C <wt> status --short` - if dirty, surface this prominently before suggesting removal.
   - Emit: `git -C <origin> worktree remove <wt>` (use `--force` only if the user explicitly asks, after seeing the dirty-state warning).
5. After all `worktree remove` commands, emit one `git -C <origin> worktree prune` per unique origin clone.
6. Finally, suggest removing any now-empty directories under the session root with `find ~/Developer/.worktrees/<session-id> -depth -type d -empty -delete` so no stale empty dirs are left behind.

Print everything as a single fenced bash block the user can review and run. Do not execute it.

## Session id resolver

Walk up from the Bash tool's shell (`$$`) via PPID until a process named `claude` is found, then read its session file and take the first 8 chars of `sessionId`:

```bash
pid=$$
while parent=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' '); [ -n "$parent" ] && [ "$parent" != "1" ]; do
  pid=$parent
  [ "$(ps -o comm= -p "$pid" 2>/dev/null | tr -d ' ')" = "claude" ] && break
done
session_id=$(jq -r '.sessionId' ~/.config/claude/sessions/"$pid".json 2>/dev/null | cut -c1-8)
```

If the resolver yields an empty `session_id` and `$ARGUMENTS` is also empty, ask the user to paste the 8-char prefix rather than guessing.
