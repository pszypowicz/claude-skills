# claude-skills

A small Claude Code marketplace of plugins I use day to day. Nothing here is proprietary; publishing it so you can install the same skills I do.

## Install

```
/plugin marketplace add pszypowicz/claude-skills
/plugin install <plugin-name>@pszypowicz-claude-skills
```

Once added, `/plugin` lists everything the marketplace offers. The marketplace is internally named `pszypowicz-claude-skills` (derived from the repo slug).

## Plugins

| Plugin                                                                             | Version | What it does                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`ado`](plugins/ado/skills/ado/SKILL.md)                                           | 2.0.1   | Azure DevOps operations: PRs, pipelines, policies, builds, variable groups, environments, feeds, branches, work items, comments. Uses `az` CLI with PAT auth from the environment or a sequester profile, falling back to `az login` tokens. |
| [`swift-concurrency`](plugins/swift-concurrency/skills/swift-concurrency/SKILL.md) | 1.0.0   | Diagnose data races, implement actor isolation, resolve Sendable issues, fix `@Observable` + `@MainActor` interaction problems, and guide Swift 6 migration.                                                                                 |
| [`modern-swift`](plugins/modern-swift/skills/modern-swift/SKILL.md)                | 1.0.0   | Swift language features beyond concurrency: attributes (`@available`, `@discardableResult`, `@frozen`, `@inlinable`, `@backDeployed`, `@resultBuilder`, `@propertyWrapper`) and macro usage (`#Preview`, custom macros).                     |
| [`go-dev`](plugins/go-dev/skills/go-dev/SKILL.md)                                  | 1.0.0   | Go development with a toolchain-first verification workflow: writing, testing, debugging, profiling, and dependency management.                                                                                                              |
| [`worktrees`](plugins/worktrees/skills/start-project/SKILL.md)                     | 1.0.0   | Batch-provision git worktrees for planned work across multiple repos, plus `/worktree-status`, `/worktree-for`, `/worktree-cleanup` slash commands.                                                                                          |

## Layout

```
.claude-plugin/marketplace.json    # marketplace manifest
plugins/<name>/
  .claude-plugin/plugin.json       # per-plugin manifest
  skills/<skill>/SKILL.md          # skill entry point
  skills/<skill>/references/       # supporting reference material
  skills/<skill>/scripts/          # bundled shell scripts, where applicable
  commands/                        # slash commands, where applicable
```

## License

MIT - see [LICENSE](LICENSE).
