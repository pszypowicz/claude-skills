# ADO Project Configuration Template

Add this section to your `~/.claude/CLAUDE.md` (or project-level CLAUDE.md) to configure project-specific ADO settings that the skill will pick up automatically.

---

```markdown
## ADO Project Configuration

### Custom Fields

- `Custom.Reviewer1` — Primary reviewer (identity field)
- `Custom.Reviewer2` — Secondary reviewer (identity field)
- `Custom.Blocked` — Blocked status (`"Yes"` / `"No"`)

### Work Item Types

If your project uses custom work item types instead of standard `Task`/`User Story`:

- User stories: `My User Story`
- Tasks: `My Task` (requires `--description`)

### Area & Iteration Paths

- Default area path: `MyProject\MyTeam`
- Iteration format: `MyProject\MyTeam\Sprint N YYYY`

### Work Item Conventions

<!-- Add any team-specific conventions here, e.g.: -->

- Keep descriptions focused on what needs to be done and why
- Do not duplicate metadata (parent ID, reviewers, assignee) in descriptions
- Do not sync PR changelogs back to task descriptions
```
