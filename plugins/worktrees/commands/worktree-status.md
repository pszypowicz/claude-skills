---
description: List worktrees materialized under the current Claude session
---

Report the state of every git worktree this session has materialized. Read-only - do not mutate anything.

Steps:

1. Resolve the current session-id (see "Session id resolver" below) to get an 8-char slug.
2. Worktree root for this session: `~/Developer/.worktrees/<session-id>/`. If the directory does not exist, say so and stop.
3. Find each inner worktree - a worktree has a `.git` **file** (not directory) at its root:

   ```bash
   find ~/Developer/.worktrees/<session-id> -maxdepth 8 -name .git -type f -print
   ```

4. For each worktree dir `<wt>` (the parent of the `.git` file), report a one-line summary:
   - Path relative to `~/Developer/.worktrees/<session-id>/`.
   - `git -C <wt> rev-parse --abbrev-ref HEAD` (current branch).
   - `git -C <wt> rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null` formatted as `behind/ahead`.
   - `git -C <wt> status --short | wc -l` as a dirty-file count.
5. For each unique origin clone (derived by stripping the `.worktrees/<session-id>/` segment from the worktree path and re-rooting at `~/Developer/`), run `git -C <origin> worktree list --porcelain` and flag any entries whose `worktree` path no longer exists on disk - those are orphans needing `git worktree prune`.

Format the output as a compact table. Do not run any state-changing git commands.

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

The `sessions/<pid>.json` file is maintained by Claude Code for each live session. If the resolver yields an empty `session_id`, ask the user to paste the 8-char prefix of their session id rather than guessing.
