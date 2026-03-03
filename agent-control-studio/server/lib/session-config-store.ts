import type { SessionConfig } from '../../shared/types'

export class SessionConfigStore {
  private config: SessionConfig

  constructor(initialConfig: SessionConfig) {
    this.config = initialConfig
  }

  get() {
    return this.config
  }

  set(config: SessionConfig) {
    this.config = config
    return this.config
  }
}
