# ADO Skill — Example Outputs

## az repos pr list -o table

```
ID    Created     Creator              Title                          Status    Repository
----  ----------  -------------------  -----------------------------  --------  -------------------
142   2026-03-05  user@example.com     Update terraform modules       Active    infra-config
139   2026-03-04  admin@example.com    Fix pipeline timeout           Active    deployment-params
137   2026-03-03  dev@example.com      Add staging environment        Active    infra-config
```

## az repos pr show --id 142 -o json (key fields)

```json
{
  "pullRequestId": 142,
  "title": "Update terraform modules",
  "status": "active",
  "createdBy": {
    "displayName": "User Name",
    "uniqueName": "user@example.com"
  },
  "sourceRefName": "refs/heads/feature/update-tf-modules",
  "targetRefName": "refs/heads/main",
  "mergeStatus": "succeeded",
  "isDraft": false,
  "autoCompleteSetBy": {
    "displayName": "User Name"
  },
  "completionOptions": {
    "mergeStrategy": "squash",
    "deleteSourceBranch": true
  },
  "reviewers": [
    {
      "displayName": "Reviewer One",
      "vote": 10,
      "isRequired": true
    }
  ]
}
```

Reviewer vote values: `10` = approved, `5` = approved with suggestions, `0` = no vote, `-5` = waiting for author, `-10` = rejected.

## az repos pr policy list --id 142 -o table

```
Evaluation ID                         Policy                                     Status       Blocking
------------------------------------  -----------------------------------------  -----------  --------
a1b2c3d4-...                          Build Validation - BVP                     Approved     True
e5f6g7h8-...                          Minimum number of reviewers                Approved     True
i9j0k1l2-...                          Required reviewers                         Running      True
m3n4o5p6-...                          Comment requirements                       Approved     False
```

## az pipelines list -o table

```
ID    Path    Name                        Default Queue
----  ------  --------------------------  ----------------
7     \       bvp-infra-config            Azure Pipelines
8     \       deploy-staging              Azure Pipelines
12    \       deploy-production           Azure Pipelines
15    \       nightly-tests               Azure Pipelines
```

## az pipelines runs list --pipeline-ids 8 --top 5 -o table

```
Run ID  Number      Status     Result     Pipeline ID  Source Branch
------  ----------  ---------  ---------  -----------  -------------------
45123   20260305.3  completed  succeeded  8            refs/heads/main
45100   20260305.2  completed  failed     8            refs/heads/main
45088   20260305.1  completed  succeeded  8            refs/heads/release/v2
45050   20260304.5  completed  succeeded  8            refs/heads/main
45032   20260304.4  completed  succeeded  8            refs/heads/main
```

## ado-get-run.sh --run-id 45100

```
[INFO]  Fetching run #45100...
Run #20260305.2   deploy-staging
  State:     completed
  Result:    failed
  Branch:    main
  Reason:    manual
  Started:   2026-03-05 14:22:31
  Finished:  2026-03-05 14:35:18
  Duration:  12m 47s

Stages/Jobs:
  [succeeded] Validate
    [succeeded] Job validate_config
  [failed   ] Deploy
    [succeeded] Job terraform_plan
    [failed   ] Job terraform_apply
  [skipped  ] Post_Deploy
    [skipped  ] Job smoke_tests
  Web: https://dev.azure.com/myorg/myproject/_build/results?buildId=45100
```

## az boards work-item show --id 12345 -o json (key fields)

```json
{
  "id": 12345,
  "fields": {
    "System.WorkItemType": "User Story",
    "System.State": "Active",
    "System.Title": "Implement caching for API responses",
    "System.AssignedTo": {
      "displayName": "Doe, Jane (EXTERN: ExampleCorp)",
      "uniqueName": "jane.doe@example.com"
    },
    "System.AreaPath": "MyOrg\\MyTeam",
    "System.IterationPath": "MyOrg\\MyTeam\\Sprint 1 2025",
    "Custom.Reviewer1": {
      "displayName": "Smith, Alex (EXTERN: ExampleCorp)",
      "uniqueName": "alex.smith@example.com",
      "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    },
    "Custom.Reviewer2": {
      "displayName": "Patel, Riya (Internal Engineering)",
      "uniqueName": "riya.patel@example.com",
      "id": "11111111-2222-3333-4444-555555555555"
    },
    "Custom.Blocked": "No"
  },
  "relations": [
    {
      "rel": "System.LinkTypes.Hierarchy-Reverse",
      "url": "https://dev.azure.com/org/_apis/wit/workItems/12300",
      "attributes": { "name": "Parent" }
    },
    {
      "rel": "System.LinkTypes.Hierarchy-Forward",
      "url": "https://dev.azure.com/org/_apis/wit/workItems/12346",
      "attributes": { "name": "Child" }
    }
  ]
}
```

Reviewer field values are identity objects — extract `uniqueName` for email, `displayName` for display, `id` for GUID.

To extract parent ID from relations: parse the URL tail (last segment after `/`).

## az boards query --wiql (child tasks)

```
ID      Title                                          State    Assigned To
------  ---------------------------------------------  -------  ---------------------------------
12346   Implement caching layer for GET endpoints      Active   Doe, Jane (EXTERN: ExampleCorp)
12347   Add cache invalidation on write operations     New      (unassigned)
```

## ado-pr-threads.sh --pr-id 142 --repo infra-config --status active

```
ID         Status     File:Line                           Author                    Replies  Comment
---------------------------------------------------------------------------------------------------------
496688     active     /src/main.tf:42                     Reviewer One              2        Should use a data source here ins...
496701     active     /modules/network.tf:15              Reviewer Two              0        Can we add a description to this ...
496715     active     -                                   Reviewer One              1        Overall LGTM, one question about ...
```

## PR thread JSON (single thread)

```json
{
  "id": 496688,
  "status": "active",
  "threadContext": {
    "filePath": "/src/main.tf",
    "rightFileStart": { "line": 42, "offset": 1 },
    "rightFileEnd": { "line": 42, "offset": 1 }
  },
  "comments": [
    {
      "id": 1,
      "parentCommentId": 0,
      "author": {
        "displayName": "Reviewer One",
        "uniqueName": "reviewer@example.com"
      },
      "content": "Should use a data source here instead of hardcoding the resource group name.",
      "commentType": "text",
      "publishedDate": "2026-03-05T10:22:00Z",
      "lastUpdatedDate": "2026-03-05T10:22:00Z"
    },
    {
      "id": 2,
      "parentCommentId": 1,
      "author": {
        "displayName": "User Name",
        "uniqueName": "user@example.com"
      },
      "content": "Good point, fixed in latest push.",
      "commentType": "text",
      "publishedDate": "2026-03-05T11:05:00Z",
      "lastUpdatedDate": "2026-03-05T11:05:00Z"
    }
  ]
}
```

## Work item comments JSON

```json
{
  "totalCount": 2,
  "count": 2,
  "comments": [
    {
      "id": 22763456,
      "workItemId": 12345,
      "text": "Started investigation. Root cause is missing RBAC assignment.",
      "createdBy": {
        "displayName": "User Name",
        "uniqueName": "user@example.com"
      },
      "createdDate": "2026-03-05T09:15:00Z",
      "format": "html"
    },
    {
      "id": 22763400,
      "workItemId": 12345,
      "text": "Assigned to team for triage.",
      "createdBy": {
        "displayName": "Admin User",
        "uniqueName": "admin@example.com"
      },
      "createdDate": "2026-03-04T16:30:00Z",
      "format": "html"
    }
  ]
}
```

## Code suggestion markdown format

When creating a PR comment with a code suggestion, use the ` ```suggestion ` block inside the comment content:

````
Consider:\n\n```suggestion\ndata "azurerm_resource_group" "example" {\n  name = var.rg_name\n}\n```
````

ADO renders this as an applicable diff that the PR author can accept with one click.

## ado-get-logs.sh --run-id 45100 --failed-only

```
[INFO]  Fetching timeline for run #45100...
[INFO]  Found 1 matching task(s). Fetching logs...

=== [failed] TerraformTaskV4 ===
--- last 50 lines ---
2026-03-05T14:33:45.123Z Terraform apply
2026-03-05T14:33:46.456Z Error: creating Resource Group "rg-staging-apps":
2026-03-05T14:33:46.789Z   AuthorizationFailed: The client does not have
2026-03-05T14:33:46.790Z   authorization to perform action
2026-03-05T14:33:46.791Z   'Microsoft.Resources/subscriptions/resourceGroups/write'
2026-03-05T14:33:47.000Z ##[error]Error: The process '/usr/bin/terraform' failed with exit code 1
```
