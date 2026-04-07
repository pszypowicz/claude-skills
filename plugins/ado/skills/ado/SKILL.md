---
name: ado
description: >-
  Azure DevOps operations — PRs, pipelines, policies, builds, variable groups,
  environments, feeds, branches, work items, comments. This skill should be used
  when the user asks to "create a PR", "list pipelines", "run a pipeline",
  "check build status", "debug failed pipeline", "create a policy",
  "add reviewers", "create a work item", "update a task", "list environments",
  "approve a pipeline", "manage variable groups", "delete a branch",
  "comment on a PR", "review PR comments", "comment on work items",
  "resolve PR thread", "code suggestion", or mentions Azure DevOps, ADO, or
  az devops CLI. Uses az CLI with PAT auth.
---

# Azure DevOps Operations

Use `az` CLI commands for most operations and bash scripts for complex multi-step orchestration.

## Authentication

Before running any command, check that auth env vars are set:

```bash
echo "ORG=${ADO_ORG:-MISSING} PROJECT=${ADO_PROJECT:-MISSING} PAT=${AZURE_DEVOPS_EXT_PAT:+set}"
```

If any are **MISSING**, stop and instruct the user:

> Please set the following in your terminal (outside Claude Code), then start a new session:
>
> ```
> export ADO_ORG=https://dev.azure.com/<org>
> export ADO_PROJECT=<project>
> export AZURE_DEVOPS_EXT_PAT=<pat>
> ```

All `az` commands use `--org "$ADO_ORG" -p "$ADO_PROJECT" --detect false`.

**Exception:** These subcommands are org-scoped — they take `--org` but **not** `--project`:

- `az boards work-item show`, `update`, `relation add`
- `az repos pr show`, `update`, `set-vote`
- `az repos pr work-item add`
- `az repos pr reviewer add`
- `az repos pr policy list`
- `az repos pr policy queue`

Only `az boards work-item create` and `az boards query` accept `--project`.

## PR Operations

```bash
# List PRs
az repos pr list -r <repo> --status active --top N --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Show PR details (org-scoped — no --project)
az repos pr show --id <ID> --org "$ADO_ORG" --detect false

# Show PR policy evaluations
az repos pr policy list --id <ID> --org "$ADO_ORG" --detect false

# Create PR
az repos pr create -r <repo> -s <branch> --title "text" \
  --auto-complete true --squash true --delete-source-branch true \
  --required-reviewers user1@email.com user2@email.com \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Update PR
az repos pr update --id <ID> --title "new" --description "new" \
  --auto-complete true --squash true \
  --org "$ADO_ORG" --detect false

# Complete/merge PR
az repos pr update --id <ID> --status completed --squash true \
  --delete-source-branch true --bypass-policy true \
  --org "$ADO_ORG" --detect false

# Abandon PR
az repos pr update --id <ID> --status abandoned --org "$ADO_ORG" --detect false

# Vote on PR
az repos pr set-vote --id <ID> --vote approve --org "$ADO_ORG" --detect false

# Add reviewers (optional or required)
# NOTE: email lookup fails with PAT auth — use identity GUIDs from work item custom fields instead
az repos pr reviewer add --id <ID> --reviewers <GUID1> <GUID2> --required true \
  --org "$ADO_ORG" --detect false

# Link work item to PR
az repos pr work-item add --id <PR_ID> --work-items <WI_ID> \
  --org "$ADO_ORG" --detect false

# Requeue failed BVP
az repos pr policy list --id <ID> -o json --org "$ADO_ORG" --detect false  # find failed evaluation IDs
az repos pr policy queue --id <ID> -e <eval-id> --org "$ADO_ORG" --detect false
```

### PR Comments & Threads

All PR comment operations require curl with PAT auth (`az rest` does not work with ADO APIs).

````bash
# Auth setup (reuse across commands)
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64)"
THREADS="${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/<repo>/pullRequests/<prId>/threads"

# List active threads (script — handles filtering + formatting)
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <ID> --repo <repo> --status active

# List threads on a specific file
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <ID> --repo <repo> --file "/src/main.tf"

# Create general comment
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}?api-version=7.1" \
  -d '{"comments":[{"content":"LGTM, one question about error handling.","commentType":1}],"status":"active"}'

# Create file-level comment
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}?api-version=7.1" \
  -d '{"comments":[{"content":"Should use a data source here.","commentType":1}],"status":"active","threadContext":{"filePath":"/src/main.tf","rightFileStart":{"line":42,"offset":1},"rightFileEnd":{"line":42,"offset":1}}}'

# Code suggestion (uses ```suggestion block — ADO renders as applicable diff)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}?api-version=7.1" \
  -d '{"comments":[{"content":"Consider:\n\n```suggestion\ndata \"azurerm_resource_group\" \"example\" {\n  name = var.rg_name\n}\n```","commentType":1}],"status":"active","threadContext":{"filePath":"/src/main.tf","rightFileStart":{"line":42,"offset":1},"rightFileEnd":{"line":44,"offset":1}}}'

# Reply to thread
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}/<threadId>/comments?api-version=7.1" \
  -d '{"parentCommentId":1,"content":"Fixed in latest push.","commentType":1}'

# Update a comment
curl -s -H "$AUTH" -H "Content-Type: application/json" -X PATCH \
  "${THREADS}/<threadId>/comments/<commentId>?api-version=7.1" \
  -d '{"content":"Updated response."}'

# Delete a comment (soft-delete, returns HTTP 200)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X DELETE \
  "${THREADS}/<threadId>/comments/<commentId>?api-version=7.1"

# Resolve thread
curl -s -H "$AUTH" -H "Content-Type: application/json" -X PATCH \
  "${THREADS}/<threadId>?api-version=7.1" \
  -d '{"status":"fixed"}'
# Status values: active, fixed, wontFix, closed, byDesign, pending

# Reactivate thread
curl -s -H "$AUTH" -H "Content-Type: application/json" -X PATCH \
  "${THREADS}/<threadId>?api-version=7.1" \
  -d '{"status":"active"}'
````

## Pipeline Operations

```bash
az pipelines list --name <filter> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines runs list --pipeline-ids <id> --top N --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines run --id <id> --branch <branch> --parameters key=value --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines build cancel --build-id <id> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines create --name <name> --repository <repo> --yml-path <path> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines update --id <id> --name <name> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines delete --id <id> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

## Policy Operations

```bash
# Step 1: Get repository ID
REPO_ID=$(az repos show -r <repo> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false --query id -o tsv)
# Step 2: List policies filtered by repository
az repos policy list --repository-id "$REPO_ID" --branch <branch> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az repos policy update --id <id> --blocking true --enabled true --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az repos policy delete --id <id> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

Create policy (complex — use script for identity resolution):

```bash
${CLAUDE_SKILL_DIR}/scripts/ado-create-policy.sh --repo <name> --type build --pipeline-id <id> [--branch main] [--display-name TEXT] [--blocking]
${CLAUDE_SKILL_DIR}/scripts/ado-create-policy.sh --repo <name> --type approver [--min-approvers N] [--creator-vote] [--reset-on-push] [--branch main] [--blocking]
${CLAUDE_SKILL_DIR}/scripts/ado-create-policy.sh --repo <name> --type required-reviewer --reviewer <email|name|team|GUID> [--reviewer ...] [--filename-patterns "/*.tf,/pipelines/*"] [--branch main] [--blocking]
```

## Variable Groups

```bash
az pipelines variable-group list --group-name <filter> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group show --id <id> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable create --group-id <id> --name KEY --value VALUE --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable update --group-id <id> --name KEY --new-value VALUE --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable delete --group-id <id> --name KEY --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

## Work Items

### Custom Fields

Project-specific custom fields and work item types should be defined in your CLAUDE.md. See `examples/project-claude-ado.md` for a template.

### Read Operations

```bash
# Show work item (all fields + relations)
az boards work-item show --id <ID> --expand all --org "$ADO_ORG" --detect false -o json

# Show specific fields only (NOTE: --expand and -f are mutually exclusive)
az boards work-item show --id <ID> -f "System.Title,System.State,System.AssignedTo,<custom-field-1>,<custom-field-2>" --org "$ADO_ORG" --detect false -o json

# Query work items (WIQL) — this command accepts --project
az boards query --wiql "SELECT [System.Id], [System.Title], [System.State] FROM workitems WHERE [System.AreaPath] UNDER '<AreaPath>' AND [System.State] = 'Active' AND [System.WorkItemType] = '<TaskType>'" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# List child work items of a parent
az boards query --wiql "SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo] FROM workitems WHERE [System.Parent] = <PARENT_ID>" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Show work item with relations (to find parent/child links)
az boards work-item show --id <ID> --expand relations --org "$ADO_ORG" --detect false -o json
# Parse parent: jq '.relations[] | select(.attributes.name == "Parent") | .url' — extract ID from URL tail
```

### Create & Update

```bash
# Create task under a project
az boards work-item create --type "<TaskType>" --title "Implement feature X" \
  --description "What needs to be done and why" \
  --assigned-to "user@email.com" \
  --area "<AreaPath>" \
  --iteration "<IterationPath>" \
  -f "<custom-field-1>=user1@email.com" "<custom-field-2>=user2@email.com" \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Update work item (state, assignment, custom fields)
az boards work-item update --id <ID> --state Active --assigned-to "me@email.com" \
  --org "$ADO_ORG" --detect false

# Set custom fields on existing work item
az boards work-item update --id <ID> \
  -f "<custom-field-1>=reviewer1@email.com" "<custom-field-2>=reviewer2@email.com" \
  --org "$ADO_ORG" --detect false

# Quick append discussion comment (az CLI shorthand — no comment ID returned, no @mention support)
az boards work-item update --id <ID> --discussion "Started work on this" \
  --org "$ADO_ORG" --detect false
```

### Comments

Full CRUD on work item comments requires REST API (curl + PAT). The `--discussion` flag above is append-only and does **not** support @mentions.

**@Mentions in comments:** Use the REST API with HTML mention format. The `--discussion` flag renders mentions as plain text.

```bash
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64)"
WI_COMMENTS="${ADO_ORG}/${ADO_PROJECT}/_apis/wit/workItems/<id>/comments"

# Post comment with @mention (use identity GUID and email)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${WI_COMMENTS}?api-version=7.1-preview.4" \
  -d '{"text":"<a href=\"mailto:user@example.com\" data-vss-mention=\"version:2.0,<IDENTITY_GUID>\">@Display Name</a> please review."}'
```

```bash
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64)"
WI_COMMENTS="${ADO_ORG}/${ADO_PROJECT}/_apis/wit/workItems/<id>/comments"

# List comments (most recent first)
curl -s -H "$AUTH" -H "Content-Type: application/json" \
  "${WI_COMMENTS}?\$top=10&order=desc&api-version=7.1-preview.4"

# Add comment (returns comment with id for later update/delete)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${WI_COMMENTS}?api-version=7.0-preview.3" \
  -d '{"text":"Started investigation. Root cause is missing RBAC assignment."}'

# Update comment
curl -s -H "$AUTH" -H "Content-Type: application/json" -X PATCH \
  "${WI_COMMENTS}/<commentId>?api-version=7.1-preview.4" \
  -d '{"text":"Updated: fix is in PR #142."}'

# Delete comment (soft-delete, returns HTTP 204)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X DELETE \
  "${WI_COMMENTS}/<commentId>?api-version=7.1-preview.4"
```

### Relations

```bash
# Add parent relation (make task child of user story)
az boards work-item relation add --id <CHILD_ID> --relation-type parent --target-id <PARENT_ID> \
  --org "$ADO_ORG" --detect false

# Add child relation
az boards work-item relation add --id <PARENT_ID> --relation-type child --target-id <CHILD_ID> \
  --org "$ADO_ORG" --detect false

# Link work item to PR (from PR side — preferred)
az repos pr work-item add --id <PR_ID> --work-items <WI_ID> \
  --org "$ADO_ORG" --detect false

# List relation types available
az boards work-item relation list-type --org "$ADO_ORG" --detect false
```

### Teams

```bash
# List teams in project
az devops team list --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# List team members
az devops team list-member --team "TeamName" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

## Scripts

```bash
# PR threads (list, filter by status/file)
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <id> --repo <repo> --status active
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <id> --repo <repo> --file "/src/main.tf" --json

# Run details with stage/job tree
${CLAUDE_SKILL_DIR}/scripts/ado-get-run.sh --run-id <id>

# Task logs
${CLAUDE_SKILL_DIR}/scripts/ado-get-logs.sh --run-id <id> --failed-only
${CLAUDE_SKILL_DIR}/scripts/ado-get-logs.sh --run-id <id> --task "Plan" --tail 100
```

## Branches & Feeds

```bash
az repos ref delete --name heads/<branch> -r <repo> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az artifacts feed list --org "$ADO_ORG" --detect false
az artifacts feed create --name <name> --org "$ADO_ORG" --detect false
az artifacts feed delete --feed <name> --org "$ADO_ORG" --detect false
```

## Environments, Checks & Approvals (REST API)

These operations have no `az` CLI support. Use curl with the REST API. See the "Manage Environment Checks & Approvals" workflow recipe below, and `reference.md` for advanced patterns (branch control checks, deployment records).

## Workflow Recipes

### PR Lifecycle

```bash
# 1. Create PR with auto-complete
az repos pr create -r my-repo -s feature/foo --title "Add feature" \
  --auto-complete true --squash true --delete-source-branch true \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# 2. Check status and policy evaluations
az repos pr show --id 42 --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az repos pr policy list --id 42 --org "$ADO_ORG" --detect false

# 3. Requeue failed BVP if needed
az repos pr policy list --id 42 -o json --org "$ADO_ORG" --detect false  # find eval ID
az repos pr policy queue --id 42 -e <eval-id> --org "$ADO_ORG" --detect false

# 4. Force-complete if stuck
az repos pr update --id 42 --status completed --squash true \
  --delete-source-branch true --bypass-policy true \
  --org "$ADO_ORG" --detect false

# 5. Abandon if no longer needed
az repos pr update --id 42 --status abandoned --org "$ADO_ORG" --detect false

# 6. Delete leftover branch
az repos ref delete --name heads/feature/foo -r my-repo --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

### Debug Failed Pipeline

```bash
# 1. Find pipeline and recent runs
az pipelines list --name "bvp" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines runs list --pipeline-ids 8 --top 5 --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# 2. Inspect run (stage/job tree)
${CLAUDE_SKILL_DIR}/scripts/ado-get-run.sh --run-id 12345

# 3. Get failed task logs
${CLAUDE_SKILL_DIR}/scripts/ado-get-logs.sh --run-id 12345 --failed-only

# 4. Drill into specific task
${CLAUDE_SKILL_DIR}/scripts/ado-get-logs.sh --run-id 12345 --task "Terraform Plan" --tail 100
```

### Manage Policies

```bash
# List policies on a repo (requires repo GUID)
REPO_ID=$(az repos show -r my-repo --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false --query id -o tsv)
az repos policy list --repository-id "$REPO_ID" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Add BVP
${CLAUDE_SKILL_DIR}/scripts/ado-create-policy.sh --repo my-repo --type build --pipeline-id 7 --display-name "BVP" --blocking

# Disable temporarily
az repos policy update --id 5 --enabled false --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Re-enable
az repos policy update --id 5 --enabled true --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Delete
az repos policy delete --id 5 --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

### Manage Variable Groups

```bash
az pipelines variable-group list --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group show --id 3 --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable create --group-id 3 --name TF_STATE_RG --value rg-terraform --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable update --group-id 3 --name TF_STATE_RG --new-value rg-terraform-v2 --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
az pipelines variable-group variable delete --group-id 3 --name OLD_VAR --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

### Manage Environment Checks & Approvals

```bash
# List environments
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64 | tr -d '\n')"
BASE="${ADO_ORG}/${ADO_PROJECT}/_apis"

curl -s -H "$AUTH" "$BASE/distributedtask/environments?api-version=7.1"

# List checks on environment
curl -s -H "$AUTH" "$BASE/pipelines/checks/configurations?resourceType=environment&resourceId=<ENV_ID>&\$expand=settings&api-version=7.1-preview.1"

# Approve a pipeline run
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '[{"approvalId":"<ID>","status":"approved","comment":"Verified plan"}]' \
  "$BASE/pipelines/approvals?api-version=7.1-preview.1"
```

### PR Review Workflow

````bash
# 1. Show PR details + list active threads
az repos pr show --id <ID> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <ID> --repo <repo> --status active

# 2. Read a specific thread in full (--json + python3 for formatting)
${CLAUDE_SKILL_DIR}/scripts/ado-pr-threads.sh --pr-id <ID> --repo <repo> --json \
  | python3 -c "import sys,json; threads=json.load(sys.stdin); t=[x for x in threads if x['id']==<threadId>]; print(json.dumps(t[0],indent=2)) if t else print('Not found')"

# 3. Reply to reviewer feedback
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64)"
THREADS="${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/<repo>/pullRequests/<ID>/threads"
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}/<threadId>/comments?api-version=7.1" \
  -d '{"parentCommentId":1,"content":"Fixed in latest push.","commentType":1}'

# 4. Provide code suggestion
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}?api-version=7.1" \
  -d '{"comments":[{"content":"Consider:\n\n```suggestion\nnew_code_here\n```","commentType":1}],"status":"active","threadContext":{"filePath":"/path","rightFileStart":{"line":10,"offset":1},"rightFileEnd":{"line":12,"offset":1}}}'

# 5. Resolve addressed threads
curl -s -H "$AUTH" -H "Content-Type: application/json" -X PATCH \
  "${THREADS}/<threadId>?api-version=7.1" \
  -d '{"status":"fixed"}'

# 6. Ask for clarification (create new general thread)
curl -s -H "$AUTH" -H "Content-Type: application/json" -X POST \
  "${THREADS}?api-version=7.1" \
  -d '{"comments":[{"content":"Question: what is the expected behavior when X?","commentType":1}],"status":"active"}'
````

### Work Item → Development → PR Workflow

```bash
# 1a. Get ticket context (all fields + relations for parent/child)
az boards work-item show --id <WI_ID> --expand all --org "$ADO_ORG" --detect false -o json

# 1b. Load work item comments for context
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64)"
curl -s -H "$AUTH" -H "Content-Type: application/json" \
  "${ADO_ORG}/${ADO_PROJECT}/_apis/wit/workItems/<WI_ID>/comments?\$top=10&order=desc&api-version=7.1-preview.4"

# 2. Get parent story for context (parse parent URL from relations, extract ID)
az boards work-item show --id <PARENT_ID> --expand all --org "$ADO_ORG" --detect false -o json
# Note parent's: custom fields, area-path, iteration-path

# 3a. Pick up existing unassigned task
az boards work-item update --id <WI_ID> --state Active --assigned-to "me@email.com" \
  --org "$ADO_ORG" --detect false
# Set custom fields if missing
az boards work-item update --id <WI_ID> \
  -f "<custom-field-1>=reviewer1@email.com" "<custom-field-2>=reviewer2@email.com" \
  --org "$ADO_ORG" --detect false

# 3b. Or create new task from parent story (inherit custom fields, area, iteration)
az boards work-item create --type "<TaskType>" --title "Implement X" \
  --description "Description of the task" \
  --area "<AreaPath>" \
  --iteration "<IterationPath>" \
  -f "<custom-field-1>=reviewer1@email.com" "<custom-field-2>=reviewer2@email.com" \
  --assigned-to "me@email.com" \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
# Link to parent
az boards work-item relation add --id <NEW_TASK_ID> --relation-type parent --target-id <PARENT_ID> \
  --org "$ADO_ORG" --detect false

# 4. Do development work...

# 5. Create PR
az repos pr create -r my-repo -s feature/branch --title "Implement X" \
  --auto-complete true --squash true --delete-source-branch true \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# 6. Link work item to PR
az repos pr work-item add --id <PR_ID> --work-items <WI_ID> \
  --org "$ADO_ORG" --detect false

# 7. Add reviewers to PR (use GUIDs from identity fields, not emails — PAT can't resolve emails)
az repos pr reviewer add --id <PR_ID> --reviewers <REVIEWER1_GUID> <REVIEWER2_GUID> --required true \
  --org "$ADO_ORG" --detect false
```

### Find Team Members for Review

```bash
# 1. List teams
az devops team list --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false -o table

# 2. Get members of a team
az devops team list-member --team "<TeamName>" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false -o table

# 3. Add as PR reviewer (use member GUID from list-member output — email lookup fails with PAT auth)
az repos pr reviewer add --id <PR_ID> --reviewers <MEMBER_GUID> \
  --org "$ADO_ORG" --detect false
```

## Troubleshooting

### --expand and -f are mutually exclusive

`az boards work-item show` does not allow `--expand` and `-f` (fields) together. Use one or the other.

### Creating and activating a task requires two calls

Setting `--state Active` and `--assigned-to` in the same `create` call is not supported. Create the task first (it starts as `New`), then update it in a second call:

```bash
# 1. Create
az boards work-item create --type "<TaskType>" --title "..." --description "..." \
  --area "<AreaPath>" --iteration "<IterationPath>" \
  --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false -o json
# 2. Activate and assign
az boards work-item update --id <NEW_ID> --state Active --assigned-to "me@email.com" \
  --org "$ADO_ORG" --detect false
```

## Identity Discovery

At the start of each session that involves assigning work items or adding PR reviewers, resolve the current user's identity:

```bash
az ad signed-in-user show --query '{displayName: displayName, mail: mail, id: id}' -o json
```

Use the returned email for `--assigned-to` and the GUID for reviewer operations. Do **not** persist this to memory — the user may switch accounts between sessions.

## Instructions

Check CLAUDE.md for project-specific ADO configuration (custom work item types, area paths, iteration paths, custom fields, team conventions).

When the user asks for an ADO operation:

1. Ensure auth env vars are set (check, then instruct user to resolve if missing)
2. Use `az` CLI with `-o json` when parsing programmatically, `-o table` for display
3. For complex queries, chain commands (e.g., list pipelines -> find ID -> run pipeline)
4. Use scripts from `${CLAUDE_SKILL_DIR}/scripts/` for: create-policy, get-run, get-logs, pr-threads
5. For environments/checks/approvals and comments, use REST curl patterns
6. For work items, remember: `az boards work-item show/update/relation add` are org-scoped (no `--project`), only `create` and `query` take `--project`
7. When creating tasks from stories, inherit custom fields, area-path, and iteration-path from the parent
8. When linking work items to PRs, prefer `az repos pr work-item add` (from PR side)
9. If an `az` command fails unexpectedly, fall back to raw curl
10. When reading a work item or PR for context, also load comments/threads for full picture
11. For PR review, start by listing active threads to see what needs attention
12. Code suggestions use ` ```suggestion ` blocks — ADO renders them as applicable diffs

## Additional Resources

For detailed reference material and real output examples, consult:

- **`reference.md`** — Full az CLI flag tables, JMESPath query patterns, REST API details for environments/checks/approvals, work item comments, PR comment threads, work item field reference, identity resolution cascade, policy type GUIDs
- **`examples.md`** — Real output samples for all major commands (PR list/show/policy, pipeline list/runs, run tree, work item JSON, query results, task logs, PR threads, work item comments, code suggestions)
- **`examples/project-claude-ado.md`** — Template for project-specific ADO configuration (custom fields, work item types, area/iteration paths) to add to your CLAUDE.md
