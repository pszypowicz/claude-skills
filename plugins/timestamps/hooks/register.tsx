import { atom, memberOf, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderElement, RenderInput } from 'claude-code'

import type { History, Stamps } from '../types'

const at = { plugin: 'timestamps', key: 'at' } as const
const history = atom({ plugin: 'timestamps', key: 'history' } as const, {
  path: '',
  stamps: {},
} as History)

// One "<ISO timestamp>\t<id>" line per transcript row uuid and per tool_use
// block the row holds. jq reads the file on the host, so a transcript past
// the 4 MiB limit of $.fs.read still loads.
const TRANSCRIPT_STAMPS = [
  'fromjson? | objects | select(.uuid and .timestamp)',
  '| .timestamp as $t',
  '| (.uuid, (.message.content? | arrays | .[] | objects | select(.type == "tool_use") | .id))',
  '| [$t, .] | @tsv',
].join(' ')

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

export const parseStamps = (tsv: string): Stamps => {
  const stamps: Stamps = {}
  for (const line of tsv.split('\n')) {
    const [iso, id] = line.split('\t')
    const time = iso ? Date.parse(iso) : NaN
    if (id && !Number.isNaN(time) && !(id in stamps)) {
      stamps[id] = time
    }
  }

  return stamps
}

const backfill = async ($: EngineInterface, path: string) => {
  if (!path || (await read($, history)).path === path) {
    return
  }
  // A missing jq or file leaves the stamps empty, so the next prompt does not retry.
  const stamps = await $.process
    .run(['jq', '-Rr', TRANSCRIPT_STAMPS, path])
    .then(({ exitCode, stdout }) => (exitCode === 0 ? parseStamps(stdout) : {}))
    .catch(() => ({}))
  await update($, history, () => ({ path, stamps }))
}

type Stamped = RenderInput<'UserMessage' | 'AssistantMessage' | 'ToolUse'>

const stamped = async ($: EngineInterface, e: Stamped, row: RenderElement) => {
  const time =
    (await read($, memberOf(at, e))) ?? (await read($, history)).stamps[e.requestId]
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
  on('session.append', async ($, e, next) => {
    const time = await $.clock.now()
    const stored = await next(e)
    if (stored.deny === undefined && e.door !== 'queue') {
      await Promise.all(
        idsOf(stored.uuid, e.message.content).map(id => $.state.set({ ...at, id }, time)),
      )
    }

    return stored
  })

  // Rows already in the transcript file (a resumed session, or the mod loaded
  // mid-session) get their stamps from the file's own timestamps.
  on('classic.SessionStart', async ($, e, next) => {
    const ran = await next(e)
    await backfill($, e.transcript_path)

    return ran
  })

  on('classic.UserPromptSubmit', async ($, e, next) => {
    await backfill($, e.transcript_path)

    return next(e)
  })

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
