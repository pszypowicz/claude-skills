import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { formatStamp, parseStamps } from '../hooks/register'

const SURFACES = ['terminal', 'desktop'] as const
const NOON = new Date(2026, 9, 15, 12, 34, 56).getTime()

const TOOL_ROW = {
  tool_use_id: 'toolu_1',
  tool: 'Bash',
  input: { command: 'ls' },
  isRunning: false,
  isErrored: false,
  isInterrupted: false,
}

// Stands in for the engine's own drawing of each row.
const engineRows = (on: On) => {
  on('ui.render', { component: 'ToolUse' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>row</Text>
  })
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>row</Text>
  })
}

describe('timestamps', () => {
  test('a tool row shows when the model produced its call', async ($, on) => {
    mock.clock(on, { now: NOON })
    engineRows(on)

    await $.session.append({
      door: 'response',
      origin: { kind: 'model', model: 'test' },
      uuid: 'row-1',
      message: {
        type: 'assistant',
        role: 'assistant',
        content: [{ type: 'tool_use', id: 'toolu_1', name: 'Bash', input: { command: 'ls' } }],
      },
    } as never)

    for (const surface of SURFACES) {
      const ui = await $.ui.mount({
        plugin: 'timestamps',
        surface,
        component: 'ToolUse',
        requestId: 'toolu_1',
        props: TOOL_ROW,
      })
      expect(await ui.find({ type: 'Text', text: formatStamp(NOON, NOON) })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'row' })).toBeDefined()
    }
  })

  test('rows already in the transcript get the time the file records', async ($, on) => {
    mock.clock(on, { now: NOON })
    engineRows(on)
    on('process.run', () => ({
      value: {
        exitCode: 0,
        stdout: `${new Date(NOON - 60_000).toISOString()}\tolder-row\n`,
        stderr: '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }))
    on('classic.UserPromptSubmit', () => ({}))

    await $.classic.UserPromptSubmit({ prompt: 'hi', transcript_path: '/t.jsonl' } as never)

    for (const surface of SURFACES) {
      const ui = await $.ui.mount({
        plugin: 'timestamps',
        surface,
        component: 'AssistantMessage',
        requestId: 'older-row',
        props: { text: 'hello', isFirstOfReply: true },
      })
      expect(
        await ui.find({ type: 'Text', text: formatStamp(NOON - 60_000, NOON) }),
      ).toBeDefined()
    }
  })

  test('a row with no recorded time is drawn as the engine drew it', async ($, on) => {
    mock.clock(on, { now: NOON })
    engineRows(on)

    for (const surface of SURFACES) {
      const ui = await $.ui.mount({
        plugin: 'timestamps',
        surface,
        component: 'ToolUse',
        requestId: 'toolu_unknown',
        props: { ...TOOL_ROW, tool_use_id: 'toolu_unknown' },
      })
      expect(await ui.find({ type: 'Text', text: 'row' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /\d\d:\d\d/ })).toBeUndefined()
    }
  })

  test('a time from an earlier day shows its date', () => {
    expect(formatStamp(NOON, NOON)).toBe('12:34:56')
    expect(formatStamp(NOON - 86_400_000, NOON)).toBe('10-14 12:34')
  })

  test('the first stamp of an id wins and bad lines are skipped', () => {
    expect(
      parseStamps('2026-10-15T10:00:00.000Z\ta\nnot a line\n2026-10-15T11:00:00.000Z\ta\n'),
    ).toEqual({ a: Date.parse('2026-10-15T10:00:00.000Z') })
  })
})
