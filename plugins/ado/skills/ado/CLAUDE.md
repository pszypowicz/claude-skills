# ADO Skill Development

Command preference order:

1. `az` CLI commands (first choice)
2. curl + PAT auth for REST APIs (`az rest` does NOT work with ADO — it's ARM-only)

Only create scripts for operations that require multi-step logic (client-side filtering, JSON shaping across multiple calls). Simple REST calls belong inline in SKILL.md as curl one-liners.
