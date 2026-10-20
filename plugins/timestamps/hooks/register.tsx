import { memberOf, read } from 'claude-code'
import type { EngineInterface, Register, RenderElement, RenderInput } from 'claude-code'

const at = { plugin: 'timestamps', key: 'at' } as const

const pad = (n: number) => String(n).padStart(2, '0')

/** `HH:MM:SS` for a time on today's date, `MM-DD HH:MM` for an earlier one. */
export const formatStamp = (time: number, now: number): string => {
  const d = new Date(time)
  const today = new Date(now)
  const isToday =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()

  return isToday
    ? `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** The ids `session.append` stamps for a row: its own and each tool_use's. */
export const idsOf = (uuid: string, content: readonly { type: string; [field: string]: unknown }[]) => [
  uuid,
  ...content.flatMap(block =>
    block.type === 'tool_use' && typeof block.id === 'string' ? [block.id] : [],
  ),
]

type Stamped = RenderInput<'UserMessage' | 'AssistantMessage' | 'ToolUse'>

const stamped = async ($: EngineInterface, e: Stamped, row: RenderElement) => {
  const time = await read($, memberOf(at, e))
  if (time === undefined) {
    return row
  }
  const { Box, Text } = $.ui.resolve(e)

  return (
    <Box flexDirection="row" columnGap={1}>
      <Box flexGrow={1} flexShrink={1}>
        {row}
      </Box>
      <Text dimColor>{formatStamp(time, await $.clock.now())}</Text>
    </Box>
  )
}

export const register: Register = on => {
  // Only the doors of rows the transcript draws. A plugin in a managed seat can
  // continue past the user tier on the other doors, which skips this hook there
  // and reports the skip.
  on(
    'session.append',
    { door: ['prompt', 'command', 'response', 'tool-result', 'delivery'] },
    async ($, e, next) => {
      const time = await $.clock.now()
      const stored = await next(e)
      if (stored.deny === undefined) {
        await Promise.all(
          idsOf(stored.uuid, e.message.content).map(id => $.state.set({ ...at, id }, time)),
        )
      }

      return stored
    },
  )

  on('ui.render', { component: 'UserMessage' }, async ($, e, next) =>
    stamped($, e, await next(e)),
  )

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) =>
    stamped($, e, await next(e)),
  )

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) =>
    stamped($, e, await next(e)),
  )
}
