<template>
  <div class="mirror-view">
    <div class="mirror-toolbar">
      <div class="toolbar-left">
        <el-button :icon="ArrowLeft" @click="goBack">返回</el-button>
        <span class="device-name">{{ deviceId }}</span>
        <el-tag v-if="mirroring" type="success" size="small" effect="dark">投屏中</el-tag>
        <el-tag v-else-if="starting" type="warning" size="small" effect="dark">启动中...</el-tag>
        <el-tag v-else type="info" size="small" effect="dark">未投屏</el-tag>
      </div>
      <div class="toolbar-right">
        <span v-if="mirroring" class="fps-info">{{ fps }} FPS</span>
        <span v-if="videoWidth" class="resolution-info">{{ videoWidth }}x{{ videoHeight }}</span>
        <el-button v-if="mirroring" type="danger" size="small" @click="stopMirror">停止投屏</el-button>
      </div>
    </div>

    <div class="mirror-content">
      <div v-if="errorMsg" class="mirror-error">
        <el-result icon="error" :sub-title="errorMsg">
          <template #extra>
            <el-button type="primary" @click="startMirror">重试</el-button>
            <el-button @click="goBack">返回</el-button>
          </template>
        </el-result>
      </div>

      <div v-else-if="starting" class="mirror-loading">
        <el-icon class="is-loading" :size="48"><Loading /></el-icon>
        <p>正在启动投屏...</p>
      </div>

      <div v-else class="canvas-wrapper">
        <canvas ref="canvasEl" class="mirror-canvas" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ArrowLeft, Loading } from "@element-plus/icons-vue"
import { useConnection } from "@/composables/useConnection"
import { useVideoDecoder } from "@/composables/useVideoDecoder"

const route = useRoute()
const router = useRouter()
const deviceId = route.query.device || ""

const starting = ref(false)
const mirroring = ref(false)
const errorMsg = ref("")
const canvasEl = ref(null)

const { connected, videoWidth, videoHeight, fps, error: decoderError, start: startDecoder, stop: stopDecoder } = useVideoDecoder(deviceId)

function getApiBase() {
  const { getBackendUrl } = useConnection()
  return getBackendUrl()
}

async function startMirror() {
  if (!deviceId) {
    errorMsg.value = "未指定设备 ID"
    return
  }

  starting.value = true
  errorMsg.value = ""

  try {
    const res = await fetch(`${getApiBase()}/api/mirror/${deviceId}/start`, {
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

    // 等待 canvas 渲染后启动解码
    await nextTick()
    if (canvasEl.value) {
      startDecoder(canvasEl.value)
    }
  } catch (e) {
    starting.value = false
    errorMsg.value = `启动投屏失败: ${e.message}`
  }
}

async function stopMirror() {
  stopDecoder()
  mirroring.value = false

  try {
    await fetch(`${getApiBase()}/api/mirror/${deviceId}/stop`, { method: "POST" })
  } catch { /* ignore */ }
}

function goBack() {
  stopMirror()
  router.push("/")
}

onMounted(() => {
  startMirror()
})

onUnmounted(() => {
  stopDecoder()
})
</script>

<style scoped>
.mirror-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.mirror-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0 16px;
  border-bottom: 1px solid #333;
  margin-bottom: 16px;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-name {
  font-size: 15px;
  font-weight: 500;
  color: #e5eaf3;
}

.fps-info, .resolution-info {
  font-size: 13px;
  color: #909399;
  font-family: monospace;
}

.mirror-content {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

.mirror-loading {
  text-align: center;
  color: #909399;
}

.mirror-loading p {
  margin-top: 16px;
  font-size: 14px;
}

.mirror-error {
  width: 100%;
}

.canvas-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
}

.mirror-canvas {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  background: #000;
  border-radius: 4px;
}
</style>
