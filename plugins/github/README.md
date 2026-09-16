# github

GitHub's remote MCP server, limited to the tools that the `gh` CLI does not
cover well: documentation search and the read-only security toolsets.

## What it exposes

- `github_support_docs_search` answers GitHub product and support questions
  from the official documentation.
- Read-only tools for code scanning alerts, secret scanning alerts, Dependabot
  alerts, and security advisories.

The repository, issue, and pull request toolsets stay off. The `gh` CLI covers
them without any tool schema cost in the context window.

## Authentication

The server runs at `https://api.githubcopilot.com/mcp/`. The plugin reads the
bearer token from the `gh` CLI at connection time, so it needs a logged-in
`gh` (`gh auth login`) and no token variable in the environment.

## Safety settings

- `X-MCP-Readonly: true` disables every write tool, even when a toolset
  includes one.
- `X-MCP-Lockdown: true` hides public-repository content from authors without
  push access, to reduce prompt injection from untrusted issues and comments.

## Widening the toolsets

Edit `X-MCP-Toolsets` in `.mcp.json`. The toolset list is in the
[remote server docs](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md).
Every added toolset costs context in each session, so add only what you use.

## Permission rule

To run the documentation search without a prompt, allow the tool in
`settings.json`:

```json
{
  "permissions": {
    "allow": ["mcp__plugin_github_github__github_support_docs_search"]
  }
}
```
