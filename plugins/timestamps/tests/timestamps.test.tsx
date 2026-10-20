import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { formatStamp } from '../hooks/register'

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

// Runs first and continues past every user-tier plugin, as a plugin in a
// managed seat does on the classic events and on the doors the transcript
// does not draw, and logs which plugins that skipped.
const passOn = {
  name: 'pass-on',
  tier: 'prepend' as const,
  register(on: any) {
    on(
      'session.append',
      { door: ['attachment', 'hook-context', 'compaction'] },
      async ($: any, e: any, next: any) => {
        const r = await next.to(e, 'append')
        $.ui.log(JSON.stringify(next.trace.filter((t: any) => t.reason).map((t: any) => t.plugin)))
        return r
      },
    )
    on('classic.*', async ($: any, e: any, next: any) => {
      const r = await next.to(e, 'append')
      $.ui.log(JSON.stringify(next.trace.filter((t: any) => t.reason).map((t: any) => t.plugin)))
      return r
    })
  },
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

  test(
    'a plugin that runs first and passes events on skips no timestamps hook',
    { plugins: [passOn] },
    async ($, on) => {
      const skipped: string[][] = []
      mock.clock(on, { now: NOON })
      on('ui.log', ($, e: any) => {
        skipped.push(JSON.parse(e.text))
        return { value: undefined }
      })
      on('classic.SessionStart', () => ({}))

      await $.session.append({
        door: 'hook-context',
        origin: { kind: 'engine' },
        uuid: 'ctx-1',
        message: {
          type: 'attachment',
          name: 'hook_additional_context',
          content: [{ type: 'text', text: 'ctx' }],
        },
      } as never)
      await $.classic.SessionStart({ source: 'startup' } as never)

      expect(skipped.length).toBe(2)
      expect(skipped.flat()).not.toContain('timestamps')
    },
  )

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
})
