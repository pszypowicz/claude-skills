---
description: Find the worktree path for a given branch across any repo under ~/Developer/
argument-hint: <branch-name>
---

Look up which worktree (if any) is attached to branch `$ARGUMENTS` across all git repos under `~/Developer/`. Read-only - do not mutate anything.

Steps:

1. If `$ARGUMENTS` is empty, say so and stop.
2. Enumerate base clones under `~/Developer/<provider>/<org>/<repo>/`. A base clone has `.git` as a directory (not a file, which would indicate a worktree). Exclude anything under `~/Developer/.worktrees/`:

   ```bash
   find ~/Developer -maxdepth 4 -type d -name .git -not -path '*/.worktrees/*' -print | sed 's|/\.git$||'
   ```

3. For each repo, run `git -C <repo> worktree list --porcelain` and find entries whose `branch` line ends in `refs/heads/$ARGUMENTS`. Note the corresponding `worktree` path.
4. Verify each candidate path still exists on disk; skip entries where the path is gone (stale - suggest `git worktree prune` in that repo).
5. Report based on match count:
   - **Exactly one match:** print the worktree path on its own line, then a one-line confirmation `(branch: $ARGUMENTS, repo: <repo-name>)`. Route edits there.
   - **Multiple matches** (same branch in different repos - unusual): list all as `<repo-name>: <worktree-path>` and ask which one.
   - **No match:** check whether the branch exists on the remote of any repo (`git -C <repo> ls-remote --heads origin "$ARGUMENTS"`). If yes, resolve the current session-id (see below) and print the fetch + worktree-add scaffold for the first such repo:

     ```
     git -C <repo> fetch origin <default-branch> --quiet && \
     git -C <repo> worktree add ~/Developer/.worktrees/<session-id>/<mirrored-repo-path> -b $ARGUMENTS origin/<default-branch>
     ```

     where `<default-branch>` comes from `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'` (fall back to `main`), and `<mirrored-repo-path>` is `<repo>` with the `~/Developer/` prefix stripped. If the branch is not on any remote, say so and stop.

Do not execute the fetch/add - just print the commands for the user to review and run. Do not run any state-changing git commands.

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

If the resolver yields an empty `session_id`, ask the user to paste the 8-char prefix rather than guessing.
