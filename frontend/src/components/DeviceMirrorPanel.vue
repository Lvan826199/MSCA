<template>
  <div class="mirror-panel" :class="{ fullscreen: isFullscreen }" @dblclick="toggleFullscreen">
    <div class="panel-header">
      <span class="panel-device-name">{{ deviceId }}</span>
      <div class="panel-status">
        <span v-if="mirroring" class="fps-badge">{{ fps }} FPS</span>
        <span v-if="videoWidth" class="res-badge">{{ videoWidth }}x{{ videoHeight }}</span>
        <el-button
          v-if="mirroring"
          type="danger"
          size="small"
          circle
          :icon="Close"
          @click.stop="stopMirror"
        />
      </div>
    </div>

    <div class="panel-canvas-area">
      <div v-if="errorMsg" class="panel-error">
        <p>{{ errorMsg }}</p>
        <el-button size="small" @click="startMirror">重试</el-button>
      </div>

      <div v-else-if="starting" class="panel-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>启动中...</p>
      </div>

      <canvas v-else ref="canvasEl" class="panel-canvas" />
    </div>

    <DeviceControlBar
      v-if="mirroring"
      @back="syncAction('sendBack')"
      @home="syncAction('sendHome')"
      @recents="syncAction('send', { type: 'key', action: 'down', keycode: 187 })"
      @volume-up="syncAction('sendVolumeUp')"
      @volume-down="syncAction('sendVolumeDown')"
      @power="syncAction('sendPower')"
      @expand-notification="syncAction('sendExpandNotification')"
      @expand-settings="syncAction('sendExpandSettings')"
      @collapse-panels="syncAction('sendCollapsePanels')"
      @rotate="syncAction('sendRotate')"
      @send-text="syncAction('sendText', $event)"
      @clipboard="(text) => syncAction('sendClipboard', text, true)"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from "vue"
import { Close, Loading } from "@element-plus/icons-vue"
import { useConnection } from "@/composables/useConnection"
import { useVideoDecoder } from "@/composables/useVideoDecoder"
import { useDeviceControl } from "@/composables/useDeviceControl"
import DeviceControlBar from "./DeviceControlBar.vue"

const props = defineProps({
  deviceId: { type: String, required: true },
  syncMode: { type: Boolean, default: false },
  syncBroadcast: { type: Function, default: null },
})

const emit = defineEmits(["started", "stopped", "error"])

const starting = ref(false)
const mirroring = ref(false)
const errorMsg = ref("")
const canvasEl = ref(null)
const isFullscreen = ref(false)

const {
  connected,
  videoWidth,
  videoHeight,
  fps,
  error: decoderError,
  start: startDecoder,
  stop: stopDecoder,
} = useVideoDecoder(props.deviceId)

const control = useDeviceControl(props.deviceId)

function getApiBase() {
  const { getBackendUrl } = useConnection()
  return getBackendUrl()
}

async function startMirror() {
  if (!props.deviceId) return

  starting.value = true
  errorMsg.value = ""

  try {
    const res = await fetch(`${getApiBase()}/api/mirror/${props.deviceId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_fps: 30, bitrate: 8000000, max_size: 0 }),
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${res.status}`)
    }

    mirroring.value = true
    starting.value = false
    emit("started", props.deviceId)

    // 启动控制连接
    control.connect()

    await nextTick()
    if (canvasEl.value) {
      startDecoder(canvasEl.value)
    }
  } catch (e) {
    starting.value = false
    errorMsg.value = e.message
    emit("error", props.deviceId, e.message)
  }
}

async function stopMirror() {
  control.unbindCanvas()
  control.disconnect()
  stopDecoder()
  mirroring.value = false
  controlBound = false
  emit("stopped", props.deviceId)

  try {
    await fetch(`${getApiBase()}/api/mirror/${props.deviceId}/stop`, { method: "POST" })
  } catch {
    /* ignore */
  }
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function sendRecents() {
  // Android KEYCODE_APP_SWITCH = 187
  control.send({ type: "key", action: "down", keycode: 187 })
}

/**
 * 执行控制操作并在同步模式下广播到其他面板
 */
function syncAction(method, ...args) {
  const fn = control[method]
  if (typeof fn === "function") fn(...args)
  if (props.syncMode && props.syncBroadcast) {
    props.syncBroadcast(props.deviceId, method, args)
  }
}

// 视频尺寸就绪/变化后绑定或更新触控事件
let controlBound = false
watch([videoWidth, videoHeight], ([w, h]) => {
  if (w && h && canvasEl.value) {
    if (!controlBound) {
      control.bindCanvas(canvasEl.value, w, h)
      controlBound = true
    } else {
      // 屏幕旋转导致尺寸变化，仅更新坐标映射
      control.updateVideoSize(w, h)
    }
  }
})

watch(decoderError, (err) => {
  if (err) {
    errorMsg.value = err
  }
})

onMounted(() => {
  startMirror()
})

onUnmounted(() => {
  control.unbindCanvas()
  control.disconnect()
  stopDecoder()
})

defineExpose({ startMirror, stopMirror, mirroring, control, deviceId: props.deviceId })
</script>

<style scoped>
.mirror-panel {
  display: flex;
  flex-direction: column;
  background: #141414;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
  min-height: 200px;
  transition: all 0.3s ease;
}

.mirror-panel.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  border-radius: 0;
  border: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #1d1e1f;
  border-bottom: 1px solid #333;
  min-height: 36px;
}

.panel-device-name {
  font-size: 13px;
  font-weight: 500;
  color: #e5eaf3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 50%;
}

.panel-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fps-badge,
.res-badge {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
}

.panel-canvas-area {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  position: relative;
}

.panel-loading {
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.panel-loading p {
  margin-top: 8px;
}

.panel-error {
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
  padding: 16px;
}

.panel-error p {
  margin-bottom: 8px;
}

.panel-canvas {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  background: #000;
  cursor: pointer;
}
</style>
