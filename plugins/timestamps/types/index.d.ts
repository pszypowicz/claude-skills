/** Epoch milliseconds by transcript row uuid or tool_use id. */
export type Stamps = Record<string, number>

/** Stamps read from a transcript file, and which file they came from. */
export type History = { path: string; stamps: Stamps }

declare module 'claude-code' {
  interface PluginState {
    timestamps: {
      /** When a row or tool call was stored during this process, by its id. */
      at: StateFamily<number>
      /** Stamps of the rows the transcript file held before they were seen live. */
      history: History
    }
  }
}
