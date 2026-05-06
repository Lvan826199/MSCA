<template>
  <div class="mirror-panel" :class="{ fullscreen: isFullscreen }" @dblclick="toggleFullscreen">
    <div class="panel-header">
      <span class="panel-device-name">{{ displayName }}</span>
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

      <div v-else class="panel-canvas-wrap">
        <canvas ref="canvasEl" class="panel-canvas" />
        <div v-if="controlError" class="panel-control-error">{{ controlError }}</div>
      </div>
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
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue"
import { Close, Loading } from "@element-plus/icons-vue"
import { useConnection } from "@/composables/useConnection"
import { useDeviceControl } from "@/composables/useDeviceControl"
import { useSettings } from "@/composables/useSettings"
import { createMirrorStartTimeout } from "@/utils/mirrorPanel"

const DeviceControlBar = defineAsyncComponent(() => import("./DeviceControlBar.vue"))

const props = defineProps({
  deviceId: { type: String, required: true },
  deviceName: { type: String, default: "" },
  syncMode: { type: Boolean, default: false },
  syncBroadcast: { type: Function, default: null },
})

const emit = defineEmits(["started", "stopped", "error"])

// 显示名称优先级：传入名称 > 设备 ID 截断
const displayName = computed(() => {
  if (props.deviceName) return props.deviceName
  // 截断长 ID
  return props.deviceId.length > 16
    ? props.deviceId.slice(0, 12) + "..."
    : props.deviceId
})

const starting = ref(false)
const mirroring = ref(false)
const errorMsg = ref("")
const canvasEl = ref(null)
const isFullscreen = ref(false)

const decoderRef = shallowRef(null)
const videoWidth = computed(() => decoderRef.value?.videoWidth.value ?? 0)
const videoHeight = computed(() => decoderRef.value?.videoHeight.value ?? 0)
const fps = computed(() => decoderRef.value?.fps.value ?? 0)
const decoderError = computed(() => decoderRef.value?.error.value ?? null)

const control = useDeviceControl(props.deviceId)
const controlError = computed(() => control.error.value)
const MIRROR_START_TIMEOUT_MS = 30_000

// 投屏参数从持久化设置读取
const { getMirrorOptions } = useSettings()

function getApiBase() {
  const { getBackendUrl } = useConnection()
  return getBackendUrl()
}

async function ensureDecoder() {
  if (!decoderRef.value) {
    const { useVideoDecoder } = await import("@/composables/useVideoDecoder")
    decoderRef.value = useVideoDecoder(props.deviceId)
  }
  return decoderRef.value
}

function stopDecoder() {
  decoderRef.value?.stop()
}

async function startMirror() {
  if (!props.deviceId) return

  starting.value = true
  errorMsg.value = ""

  const startTimeout = createMirrorStartTimeout(MIRROR_START_TIMEOUT_MS)

  try {
    const res = await fetch(`${getApiBase()}/api/mirror/${props.deviceId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: startTimeout.signal,
      body: JSON.stringify({
        max_fps: getMirrorOptions().maxFps,
        bitrate: getMirrorOptions().bitrate,
        max_size: getMirrorOptions().maxSize,
      }),
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

    // 等待 canvas 渲染就绪（v-else 条件切换需要 DOM 更新）
    await nextTick()
    // canvas 可能还未挂载（Vue 条件渲染延迟），重试几次
    let retries = 0
    while (!canvasEl.value && retries < 5) {
      await new Promise((r) => setTimeout(r, 50))
      retries++
    }
    if (canvasEl.value) {
      const decoder = await ensureDecoder()
      decoder.start(canvasEl.value)
    }
  } catch (e) {
    starting.value = false
    errorMsg.value = startTimeout.signal.aborted ? startTimeout.getErrorMessage() : e.message
    emit("error", props.deviceId, errorMsg.value)
  } finally {
    startTimeout.clear()
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

// 触控同步：在同步模式下将归一化触控事件广播到其他面板
control.setSyncCallback((evt) => {
  if (props.syncMode && props.syncBroadcast) {
    props.syncBroadcast(props.deviceId, "sendNormalizedTouch", [evt])
  }
})

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
  min-height: 0;
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

.panel-canvas-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.panel-canvas {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  background: #000;
  cursor: pointer;
}

.panel-control-error {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(245, 108, 108, 0.9);
  color: #fff;
  font-size: 12px;
  text-align: center;
  pointer-events: none;
}
</style>
