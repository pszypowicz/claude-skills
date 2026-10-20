declare module 'claude-code' {
  interface PluginState {
    timestamps: {
      /** When a row or tool call was stored during this process, by its id. */
      at: StateFamily<number>
    }
  }
}
