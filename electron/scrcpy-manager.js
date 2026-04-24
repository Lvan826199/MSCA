// ScrcpyManager - Scrcpy 子进程管理模块
// TODO: M3 阶段实现完整的 Scrcpy 子进程管理

class ScrcpyManager {
  constructor() {
    this._processes = new Map()
  }

  async startMirroring(deviceId, options = {}) {
    // TODO: M3.1 实现 scrcpy 子进程启动
    throw new Error("ScrcpyManager.startMirroring 尚未实现")
  }

  async stopMirroring(deviceId) {
    const proc = this._processes.get(deviceId)
    if (proc) {
      proc.kill("SIGTERM")
      this._processes.delete(deviceId)
    }
  }

  stopAll() {
    for (const [id, proc] of this._processes) {
      proc.kill("SIGTERM")
      this._processes.delete(id)
    }
  }
}

module.exports = ScrcpyManager
