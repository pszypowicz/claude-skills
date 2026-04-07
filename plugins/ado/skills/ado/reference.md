# ADO Skill — Detailed Reference

## az repos pr — Full Flag Reference

### pr create

| Flag                                 | Description                              |
| ------------------------------------ | ---------------------------------------- |
| `-r, --repository`                   | Repository name or ID                    |
| `-s, --source-branch`                | Source branch                            |
| `-t, --target-branch`                | Target branch (default: repo default)    |
| `--title`                            | PR title                                 |
| `--description`                      | PR description (supports markdown)       |
| `--auto-complete true/false`         | Set auto-complete                        |
| `--squash true/false`                | Squash merge                             |
| `--delete-source-branch true/false`  | Delete source after merge                |
| `--draft true/false`                 | Create as draft                          |
| `--reviewers`                        | Space-separated reviewer emails          |
| `--required-reviewers`               | Space-separated required reviewer emails |
| `--work-items`                       | Space-separated work item IDs to link    |
| `--transition-work-items true/false` | Transition linked work items             |

### pr update

| Flag                                 | Description                        |
| ------------------------------------ | ---------------------------------- |
| `--id`                               | PR ID                              |
| `--title`                            | New title                          |
| `--description`                      | New description                    |
| `--status`                           | `active`, `completed`, `abandoned` |
| `--auto-complete true/false`         | Toggle auto-complete               |
| `--squash true/false`                | Squash merge                       |
| `--delete-source-branch true/false`  | Delete source after merge          |
| `--bypass-policy true/false`         | Bypass policies on completion      |
| `--bypass-policy-reason`             | Reason for bypass                  |
| `--draft true/false`                 | Toggle draft status                |
| `--transition-work-items true/false` | Transition linked work items       |

### pr set-vote

Vote values: `approve`, `approve-with-suggestions`, `reset`, `wait-for-author`, `reject`

## JMESPath Query Patterns

Filter and transform `az` CLI JSON output with `--query`:

```bash
# Get PR IDs and titles only
az repos pr list -r myrepo --query "[].{id:pullRequestId, title:title}" -o table

# Get only failed runs
az pipelines runs list --pipeline-ids 8 --query "[?result=='failed']" -o table

# Get variable names from a group
az pipelines variable-group show --id 3 --query "variables | keys(@)" -o json

# Get specific variable value
az pipelines variable-group show --id 3 --query "variables.MY_VAR.value" -o tsv

# Get pipeline ID by name
az pipelines list --query "[?name=='my-pipeline'].id | [0]" -o tsv

# Get PR reviewers who haven't voted
az repos pr show --id 42 --query "reviewers[?vote==\`0\`].displayName" -o json
```

## REST API — Environments, Checks & Approvals

### Base Setup

```bash
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64 | tr -d '\n')"
BASE="${ADO_ORG}/${ADO_PROJECT}/_apis"
```

### Environments

```bash
# List all environments
curl -s -H "$AUTH" "$BASE/distributedtask/environments?api-version=7.1" | python3 -m json.tool

# Get specific environment
curl -s -H "$AUTH" "$BASE/distributedtask/environments/<ID>?api-version=7.1"

# List deployment records for an environment
curl -s -H "$AUTH" "$BASE/distributedtask/environments/<ID>/environmentdeploymentrecords?api-version=7.1"
```

### Checks & Approvals

```bash
# List checks on environment
curl -s -H "$AUTH" \
  "$BASE/pipelines/checks/configurations?resourceType=environment&resourceId=<ENV_ID>&\$expand=settings&api-version=7.1-preview.1"

# List pending approvals
curl -s -H "$AUTH" "$BASE/pipelines/approvals?state=pending&top=50&api-version=7.1-preview.1"

# Approve
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '[{"approvalId":"<APPROVAL_ID>","status":"approved","comment":"LGTM"}]' \
  "$BASE/pipelines/approvals?api-version=7.1-preview.1"

# Reject
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '[{"approvalId":"<APPROVAL_ID>","status":"rejected","comment":"Plan has destroys"}]' \
  "$BASE/pipelines/approvals?api-version=7.1-preview.1"
```

### Update Branch Control Check

```bash
# Get current check config first, then PUT with modified allowedBranches
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "type": {"id": "...", "name": "Task Check"},
    "settings": {
      "definitionRef": {"id": "...", "name": "evaluate-branch-protection", "version": "0.0.1"},
      "displayName": "Branch control",
      "inputs": {
        "allowedBranches": "refs/heads/main,refs/tags/v*",
        "ensureProtectionOfBranch": "true"
      }
    },
    "resource": {"type": "environment", "id": "<ENV_ID>"},
    "timeout": 1440
  }' \
  "$BASE/pipelines/checks/configurations/<CHECK_ID>?api-version=7.1-preview.1"
```

## REST API — Work Item Comments

### Base Endpoint

`{org}/{project}/_apis/wit/workItems/{id}/comments`

### API Versions

| Operation     | API Version     |
| ------------- | --------------- |
| List comments | `7.1-preview.4` |
| Get comment   | `7.1-preview.4` |
| Create        | `7.0-preview.3` |
| Update        | `7.1-preview.4` |
| Delete        | `7.1-preview.4` |

### List Comments

```bash
GET {org}/{project}/_apis/wit/workItems/{id}/comments?$top=10&order=desc&api-version=7.1-preview.4
```

Parameters: `$top` (default 200, max 1000), `order` (`asc`|`desc`), `fromRevision`

### Create Comment

```bash
POST {org}/{project}/_apis/wit/workItems/{id}/comments?api-version=7.0-preview.3
Body: {"text": "Comment content here"}
```

Returns: `{id, text, createdBy, createdDate, format: "html"}`

Note: Response field is `id` (not `commentId`). Format is always `html`.

### Update Comment

```bash
PATCH {org}/{project}/_apis/wit/workItems/{id}/comments/{commentId}?api-version=7.1-preview.4
Body: {"text": "Updated content"}
```

### Delete Comment

```bash
DELETE {org}/{project}/_apis/wit/workItems/{id}/comments/{commentId}?api-version=7.1-preview.4
```

Returns HTTP 204 (no body).

### CLI Shorthand

`az boards work-item update --id <ID> --discussion "text"` — append-only, no comment ID returned. Use REST for full CRUD.

## REST API — PR Comment Threads

### Base Endpoint

`{org}/{project}/_apis/git/repositories/{repo}/pullRequests/{prId}/threads`

Repo name works directly — no GUID resolution needed. API version: `7.1` (GA, not preview).

### Thread Operations

**List all threads:**

```bash
GET .../threads?api-version=7.1
```

No server-side status filtering — must filter client-side.

**Create thread:**

```bash
POST .../threads?api-version=7.1
Body: {"comments": [{"content": "...", "commentType": 1}], "status": "active"}
```

**Create file-level thread:**

```bash
POST .../threads?api-version=7.1
Body: {
  "comments": [{"content": "...", "commentType": 1}],
  "status": "active",
  "threadContext": {
    "filePath": "/path/to/file",
    "rightFileStart": {"line": 42, "offset": 1},
    "rightFileEnd": {"line": 42, "offset": 1}
  }
}
```

**Update thread status:**

```bash
PATCH .../threads/{threadId}?api-version=7.1
Body: {"status": "fixed"}
```

Thread status values (strings): `active`, `fixed`, `wontFix`, `closed`, `byDesign`, `pending`

### Comment Operations

**Reply to thread:**

```bash
POST .../threads/{threadId}/comments?api-version=7.1
Body: {"parentCommentId": 1, "content": "...", "commentType": 1}
```

**Update comment:**

```bash
PATCH .../threads/{threadId}/comments/{commentId}?api-version=7.1
Body: {"content": "Updated text"}
```

**Delete comment (soft-delete):**

```bash
DELETE .../threads/{threadId}/comments/{commentId}?api-version=7.1
```

Returns HTTP 200.

### Comment Types

| String in response | Integer on create | Description                     |
| ------------------ | ----------------- | ------------------------------- |
| `text`             | `1`               | Regular comment                 |
| `codeChange`       | `2`               | Code change                     |
| `system`           | `3`               | System-generated (auto threads) |

### Code Suggestions

Use a regular comment with a ` ```suggestion ` markdown block and `threadContext`. ADO renders these as applicable diffs:

````markdown
Consider:

```suggestion
data "azurerm_resource_group" "example" {
  name = var.rg_name
}
```
````

### Limits

- Max 500 comments per thread

## Work Items — az boards Reference

### --project flag support

Not all `az boards` commands accept `--project`. This is an important gotcha:

| Command                   | `--org` | `--project` | Notes                                |
| ------------------------- | ------- | ----------- | ------------------------------------ |
| `work-item show`          | Yes     | **No**      | Org-scoped (ID is globally unique)   |
| `work-item update`        | Yes     | **No**      | Org-scoped                           |
| `work-item create`        | Yes     | Yes         | Needs project to create in           |
| `work-item relation add`  | Yes     | **No**      | Org-scoped                           |
| `work-item relation show` | Yes     | **No**      | Org-scoped                           |
| `query`                   | Yes     | Yes         | Needed for WIQL area/iteration paths |
| `devops team list`        | Yes     | Yes         |                                      |
| `devops team list-member` | Yes     | Yes         |                                      |

### Custom Fields (Example)

| Field Reference Name | Type     | Values                                      |
| -------------------- | -------- | ------------------------------------------- |
| `Custom.Reviewer1`   | Identity | `{displayName, uniqueName, id, descriptor}` |
| `Custom.Reviewer2`   | Identity | `{displayName, uniqueName, id, descriptor}` |
| `Custom.Blocked`     | String   | `"Yes"` / `"No"`                            |

Some projects use non-standard work item types (e.g. `Custom User Story` instead of `User Story`)

### Setting Identity Fields via CLI

When setting identity fields (Reviewer1/Reviewer2) via `az boards work-item update -f`, pass the email:

```bash
az boards work-item update --id <ID> -f "Custom.Reviewer1=user@email.com" --org "$ADO_ORG" --detect false
```

### Reading Identity Fields

Identity fields in JSON output are objects, not strings:

```bash
# Extract Reviewer1 email from work item
az boards work-item show --id <ID> --org "$ADO_ORG" --detect false \
  --query "fields.\"Custom.Reviewer1\".uniqueName" -o tsv

# Extract both reviewer emails
az boards work-item show --id <ID> --org "$ADO_ORG" --detect false -o json \
  | python3 -c "
import sys, json
fields = json.load(sys.stdin)['fields']
for rev in ['Custom.Reviewer1', 'Custom.Reviewer2']:
    v = fields.get(rev, {})
    if v:
        print(f'{rev}: {v.get(\"uniqueName\", \"?\")} ({v.get(\"displayName\", \"?\")})')
"
```

### Parsing Parent from Relations

```bash
# Get parent work item ID from relations
az boards work-item show --id <ID> --expand relations --org "$ADO_ORG" --detect false -o json \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for rel in data.get('relations', []):
    if rel.get('attributes', {}).get('name') == 'Parent':
        parent_id = rel['url'].rstrip('/').split('/')[-1]
        print(parent_id)
        break
"
```

### WIQL Query Examples

```bash
# Active tasks in an area
az boards query --wiql "SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo] FROM workitems WHERE [System.AreaPath] UNDER 'MyOrg\MyTeam' AND [System.State] = 'Active' AND [System.WorkItemType] = 'Task'" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Children of a specific work item
az boards query --wiql "SELECT [System.Id], [System.Title], [System.State] FROM workitems WHERE [System.Parent] = <PARENT_ID>" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Unassigned tasks in current sprint
az boards query --wiql "SELECT [System.Id], [System.Title] FROM workitems WHERE [System.IterationPath] = 'MyOrg\MyTeam\Sprint 1 2025' AND [System.AssignedTo] = '' AND [System.WorkItemType] = 'Task'" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false

# Work items linked to a specific user
az boards query --wiql "SELECT [System.Id], [System.Title], [System.State] FROM workitems WHERE [System.AssignedTo] = 'user@email.com' AND [System.State] <> 'Closed'" --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false
```

### Relation Types

| Relation Type | `--relation-type` value | Description                   |
| ------------- | ----------------------- | ----------------------------- |
| Parent        | `parent`                | Make target the parent        |
| Child         | `child`                 | Make target a child           |
| Related       | `related`               | General relation              |
| Predecessor   | `predecessor`           | Target must finish first      |
| Successor     | `successor`             | This must finish after target |

### Linking Work Item to PR (REST fallback)

If `az repos pr work-item add` doesn't work, use REST:

```bash
AUTH="Authorization: Basic $(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64 | tr -d '\n')"
# Get repo ID and project ID first
REPO_ID=$(az repos show -r <repo> --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false --query id -o tsv)
PROJECT_ID=$(curl -s -H "$AUTH" "${ADO_ORG}/_apis/projects/${ADO_PROJECT}?api-version=7.1" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Add ArtifactLink relation
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json-patch+json" \
  -d "[{\"op\":\"add\",\"path\":\"/relations/-\",\"value\":{\"rel\":\"ArtifactLink\",\"url\":\"vstfs:///Git/PullRequestId/${PROJECT_ID}/${REPO_ID}/<PR_ID>\",\"attributes\":{\"name\":\"Pull Request\"}}}]" \
  "${ADO_ORG}/_apis/wit/workitems/<WI_ID>?api-version=7.1"
```

## Policy Type GUIDs

| Type                 | GUID                                   | Notes                                                            |
| -------------------- | -------------------------------------- | ---------------------------------------------------------------- |
| Build validation     | `0609b952-1397-4640-95ec-e00a01b2c241` | Requires `buildDefinitionId` in settings                         |
| Minimum reviewers    | `fa4e907d-c16b-4a4c-9dfa-4906e5d171dd` | `minimumApproverCount`, `creatorVoteCounts`, `resetOnSourcePush` |
| Required reviewers   | `fd2167ab-b0be-447a-8ec8-39368250530e` | `requiredReviewerIds` (array of GUIDs)                           |
| Comment requirements | `c6a1889d-b943-4856-b76f-9e46bb6b0df2` | Requires all threads resolved before PR completion               |
| Work item linking    | `40e92b44-2fe1-4dd6-b3d8-74a9c21d0c6e` |                                                                  |
| Merge strategy       | `fa4e907d-c16b-4a4c-9dfa-4916e5d171ab` |                                                                  |

## Identity Resolution (create-policy script)

The `ado-create-policy.sh` script resolves reviewer identities through this cascade:

1. **Raw GUID** — 36-char hex-and-dash pattern, used as-is
2. **Email/display name** — Queries VSSPS Graph Users API, matches email or display name, converts descriptor to storage key GUID via Storage Keys API
3. **Team name** — Queries Teams API, matches team name, returns team ID (already a GUID)

VSSPS base URL: `https://vssps.dev.azure.com/<org_name>`

```bash
# Graph users endpoint
GET https://vssps.dev.azure.com/{org}/_apis/graph/users?api-version=7.1-preview.1

# Storage key from descriptor
GET https://vssps.dev.azure.com/{org}/_apis/graph/storagekeys/{descriptor}?api-version=7.1-preview.1

# Teams endpoint
GET https://dev.azure.com/{org}/_apis/projects/{project}/teams?api-version=7.1
```

## Policy Evaluation (Requeue BVP)

```bash
# Get project ID (needed for artifact ID)
PROJECT_ID=$(curl -s -H "$AUTH" "${ADO_ORG}/_apis/projects/${ADO_PROJECT}?api-version=7.1" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Build artifact reference
ARTIFACT="vstfs:///CodeReview/CodeReviewId/${PROJECT_ID}/<PR_ID>"

# List evaluations
curl -s -H "$AUTH" \
  "$BASE/policy/evaluations?artifactId=$(python3 -c "import urllib.parse;print(urllib.parse.quote('${ARTIFACT}'))")&api-version=7.1-preview.1"

# Requeue a specific evaluation
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" -d '{}' \
  "$BASE/policy/evaluations/<EVAL_ID>?api-version=7.1-preview.1"
```
