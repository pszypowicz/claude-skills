# timestamps

Shows when each prompt, reply block, and tool call in the transcript was
produced. The time sits at the right edge of the row in dim text. A time from
today reads `14:32:07` and an earlier one reads `10-14 14:32`.

## Install

```
/plugin install timestamps --marketplace pszypowicz/claude-skills
```

On Claude Code 2.1.275 or later this adds the marketplace when it is missing
and installs the plugin in one step.

## How it works

Each prompt, slash command, reply, tool result, and delivered message passes
through the `session.append` hook as it is stored, and the plugin records the
time under the row's id and under the id of each tool call the row holds. The
transcript draws a message row under that same id and a tool row under its tool
call id, so the `ui.render` hooks on `UserMessage`, `AssistantMessage`, and
`ToolUse` look the time up and draw it beside the row Claude Code draws. The
hook leaves other rows alone, such as attachments and hook context, because the
transcript does not draw them as a message or tool row.

## Requirements

- Claude Code with function hooks. The plugin is tested with 2.1.304, and the
  function hooks API is early access, so it can change between releases.

## Limits

- A collapsed tool group, such as "Read 3 files", shows no time.
- A tool row shows when the model produced the call, which can be well before
  the call ran.
- Rows stored before the plugin loaded show no time, for example the earlier
  rows of a resumed session.

## Tests

```
claude plugin test plugins/timestamps
```

The tests run on the Claude Code test kit, so the repository's CI does not run
them.
