---
name: start-project
description: Batch-provision git worktrees for a set of planned tasks across one or more repos under ~/Developer/. Use whenever the user names a set of tasks or branches to work on, wants to "start a project", "kick off" or "begin" planned work, "set up worktrees for X/Y/Z", or otherwise wants isolated working copies to land commits against before a single-repo edit makes sense. Trigger even if the user doesn't use the exact word "worktree" - if they're framing upcoming work as a list of {repo, branch} pairs, this skill handles it. Do NOT trigger for inventory questions ("what worktrees do I have?" - that's `/worktree-status`), single-branch lookups ("where's the worktree for X?" - `/worktree-for`), or teardown ("clean up my worktrees" - `/worktree-cleanup`).
---

# start-project

Turn a list of planned tasks into ready-to-edit git worktrees. Each task becomes a worktree: a fresh branch checked out from its repo's default branch, materialized at a predictable path so the user (and you) can start editing immediately.

> **Assumed layout:** this skill (and the sibling `/worktree-status`, `/worktree-for`, `/worktree-cleanup` commands) assume clones live under `~/Developer/<provider>/<org>/<repo>` and worktrees under `~/Developer/.worktrees/<session-id>/`. If your repos live elsewhere, adapt the paths throughout before running.

## Why this exists

Working against a repo's base clone is fine for a single quick change, but falls apart when the user has several concurrent streams of work - commits from one task leak into another, mid-review branches get dirty, and rebasing gets painful. Worktrees give each task its own checkout rooted at the same bare repo, so the streams stay isolated with no extra clones.

This skill automates the mechanical parts: resolving the repo, figuring out the default branch, creating the worktree at a consistent path under `~/Developer/.worktrees/<session-id>/`. You drive it via the Bash tool - there are no bundled shell scripts to call.

## Inputs

The user provides a list of tasks. Each task is `{repo_name, branch_name, description}`:

- `repo_name`: the repo's directory name, e.g. `claude-skills`. No fuzzy matching - it must match a directory under `~/Developer/<provider>/<org>/`.
- `branch_name`: the new branch to create, e.g. `feat/auth-flow`. Task-meaningful names; no imposed convention like `claude/<slug>`.
- `description`: free-text purpose, used only for the summary table at the end.

If the user gives you a less structured prompt ("start work on auth-flow in claude-skills and config-loader refactor in dotfiles"), parse it into the tuple form before proceeding. Ask for clarification when any field is ambiguous rather than guessing.

## Steps

### 1. Resolve the session-id

Walk up from the Bash tool's shell to find the `claude` process, then read its session file:

```bash
pid=$$
while parent=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' '); [ -n "$parent" ] && [ "$parent" != "1" ]; do
  pid=$parent
  [ "$(ps -o comm= -p "$pid" 2>/dev/null | tr -d ' ')" = "claude" ] && break
done
session_id=$(jq -r '.sessionId' ~/.config/claude/sessions/"$pid".json 2>/dev/null | cut -c1-8)
```

The `sessions/<pid>.json` file is maintained by Claude Code for each live session. The first 8 chars of `sessionId` are immutable for the session's lifetime - this is the stable identifier the worktree layout anchors on (session `name` is deliberately not used because the user can rename mid-session via `/rename` and that would desync existing directories).

If `session_id` comes back empty, ask the user to paste their 8-char session id prefix rather than guessing.

### 2. Resolve each repo to an absolute path

For each `repo_name`, look for directories matching the canonical `~/Developer/<provider>/<org>/<repo_name>` layout:

```bash
ls -d ~/Developer/*/*/"$repo_name" 2>/dev/null
```

- **One match**: use it.
- **Zero matches**: tell the user you couldn't find the repo and ask for the full path (or a correction).
- **Multiple matches** (same repo name under different orgs): list the candidates and ask which one.

Don't search more broadly than this pattern. The expected layout is `<provider>/<org>/<repo>` (for example `github.com/acme/repo-a` or `dev.azure.com/acme-org/repo-b`), and relaxing the glob leads to matching worktrees or nested directories that are not base clones.

### 3. For each task, provision the worktree

Per task:

1. **Default branch**: `git -C <repo_root> symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'`. Fall back to `main` if that fails.
2. **Mirrored repo path**: strip the `$HOME/Developer/` prefix from `<repo_root>`.
3. **Worktree path**: `~/Developer/.worktrees/<session-id>/<mirrored-repo-path>`.
4. **Fetch and create**:

   ```bash
   git -C <repo_root> fetch origin <default_branch> --quiet
   git -C <repo_root> worktree add <wt_path> -b <branch_name> origin/<default_branch>
   ```

Do these one task at a time, not in parallel. If any `worktree add` fails (branch already exists, dirty index, network error on fetch), stop immediately and tell the user what went wrong. Do not leave half-provisioned state - the user will either re-run with adjustments or clean up manually. Do not try to recover automatically.

### 4. Report a summary table

After all worktrees are created successfully, print a single compact table the user can skim:

```
branch             | repo           | worktree path                                                | purpose
-------------------|----------------|--------------------------------------------------------------|----------------------
feat/auth-flow     | repo-a         | ~/Developer/.worktrees/ecb3066b/<path>/repo-a                | wire up OIDC
fix/memory-leak    | repo-b         | ~/Developer/.worktrees/ecb3066b/<path>/repo-b                | plug the goroutine leak
```

End with a one-liner reminding the user which worktree path to reference for each follow-up task - you will route subsequent edits there rather than to the base clone.

## What this skill does NOT do

- Does not touch the base clone's working tree.
- Does not create remote branches (only local). Push happens later when the user is ready.
- Does not run any teardown - when the work is done, the user invokes `/worktree-cleanup`.
- Does not re-enter an existing worktree if the branch already exists - that surfaces as an error. If the user wants to resume an existing branch, they use `/worktree-for <branch>` instead.
- Does not discover repos by content (e.g. "every repo that has a `config/` dir"). If the user phrases the task that way, enumerate the candidates first, show them, and ask the user to confirm the list before creating anything.

## Common pitfalls

- **Parallel worktree creation against the same bare repo**: git serializes worktree metadata updates per repo, so creating multiple worktrees in the same repo concurrently can fail intermittently. Always serialize per repo.
- **Stale default-branch detection**: `origin/HEAD` can point to a branch that no longer exists if the remote renamed its default. If `fetch origin <default_branch>` fails with "couldn't find remote ref", ask the user rather than trying alternatives.
- **Branch names with slashes**: `feat/foo` is valid as a branch name. Do not rewrite it to `feat-foo` or similar - let git store the branch under `refs/heads/feat/foo`. The worktree path does not embed the branch name, so no sanitization is needed there.
