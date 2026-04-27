<template>
  <div class="mirror-view">
    <div class="mirror-toolbar">
      <div class="toolbar-left">
        <el-button :icon="ArrowLeft" @click="goBack">返回</el-button>
        <span class="toolbar-title">投屏监控</span>
        <el-tag type="info" size="small" effect="dark">{{ devices.length }} 台设备</el-tag>
      </div>
      <div class="toolbar-right">
        <el-switch
          v-model="syncMode"
          active-text="同步"
          inactive-text=""
          size="small"
          style="margin-right: 8px;"
        />
        <el-select
          v-model="gridColumns"
          size="small"
          style="width: 90px; margin-right: 8px;"
          placeholder="列数"
        >
          <el-option label="自动" :value="0" />
          <el-option label="1 列" :value="1" />
          <el-option label="2 列" :value="2" />
          <el-option label="3 列" :value="3" />
          <el-option label="4 列" :value="4" />
        </el-select>
        <el-button size="small" :icon="Plus" @click="openAddDevice">添加设备</el-button>
        <el-button
          v-if="devices.length > 0"
          type="danger"
          size="small"
          @click="stopAll"
        >
          全部停止
        </el-button>
      </div>
    </div>

    <div v-if="devices.length === 0" class="mirror-empty">
      <el-empty description="暂无投屏设备">
        <el-button type="primary" @click="goBack">返回设备列表</el-button>
      </el-empty>
    </div>

    <div v-else class="mirror-grid" :class="gridClass">
      <DeviceMirrorPanel
        v-for="id in devices"
        :key="id"
        :device-id="id"
        :device-name="getDeviceName(id)"
        :sync-mode="syncMode"
        :sync-broadcast="broadcastControl"
        :ref="(el) => setPanelRef(id, el)"
        @stopped="onDeviceStopped"
      />
    </div>

    <!-- 添加设备对话框 -->
    <el-dialog v-model="showAddDevice" title="添加投屏设备" width="400px" append-to-body>
      <div v-if="availableDevices.length === 0" style="text-align: center; color: #909399; padding: 20px 0;">
        没有可用的在线设备
      </div>
      <el-checkbox-group v-else v-model="selectedDevices">
        <el-checkbox
          v-for="dev in availableDevices"
          :key="dev.id"
          :value="dev.id"
          :label="dev.model || dev.id"
          style="display: block; margin-bottom: 8px;"
        />
      </el-checkbox-group>
      <template #footer>
        <el-button @click="showAddDevice = false">取消</el-button>
        <el-button type="primary" :disabled="selectedDevices.length === 0" @click="addDevices">
          添加 ({{ selectedDevices.length }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ArrowLeft, Plus } from "@element-plus/icons-vue"
import { useConnection } from "@/composables/useConnection"
import { useSettings } from "@/composables/useSettings"
import { useDevices } from "@/composables/useDevices"
import DeviceMirrorPanel from "@/components/DeviceMirrorPanel.vue"

const route = useRoute()
const router = useRouter()
const { settings: appSettings } = useSettings()
const {
  devices: globalDevices,
  connect: connectDeviceWs,
  disconnect: disconnectDeviceWs,
  fetchDevices,
} = useDevices()

// 当前投屏设备列表
const devices = ref([])
const panelRefs = ref({})
const showAddDevice = ref(false)
const selectedDevices = ref([])
const syncMode = ref(false)
const gridColumns = ref(appSettings.value.layout.gridColumns)

// 同步 gridColumns 到持久化设置
watch(gridColumns, (val) => {
  appSettings.value.layout.gridColumns = val
})

// 根据设备数量或手动选择计算网格 class
const gridClass = computed(() => {
  if (gridColumns.value > 0) return `grid-manual-${gridColumns.value}`
  const count = devices.value.length
  if (count <= 1) return "grid-1"
  if (count <= 2) return "grid-2"
  if (count <= 4) return "grid-4"
  if (count <= 6) return "grid-6"
  return "grid-9"
})

// 可添加的设备（在线且未在投屏中）
const availableDevices = computed(() =>
  globalDevices.value.filter(
    (d) => d.status === "online" && !devices.value.includes(d.id)
  )
)

function setPanelRef(id, el) {
  if (el) {
    panelRefs.value[id] = el
  } else {
    delete panelRefs.value[id]
  }
}

function getDeviceName(deviceId) {
  const MAX_LEN = 18
  const dev = globalDevices.value.find((d) => d.id === deviceId)
  if (!dev) return ""
  if (dev.alias) {
    const model = dev.model || dev.id
    const full = `${dev.alias}(${model})`
    if (full.length <= MAX_LEN) return full
    const prefix = dev.alias
    const remain = MAX_LEN - prefix.length - 2
    if (remain >= 2) return `${prefix}(${model.slice(0, remain - 1)}…)`
    return full.slice(0, MAX_LEN - 1) + "…"
  }
  const name = dev.model || ""
  return name.length > MAX_LEN ? name.slice(0, MAX_LEN - 1) + "…" : name
}

function getApiBase() {
  const { getBackendUrl } = useConnection()
  return getBackendUrl()
}

async function openAddDevice() {
  await fetchDevices()
  selectedDevices.value = []
  showAddDevice.value = true
}

function addDevices() {
  for (const id of selectedDevices.value) {
    if (!devices.value.includes(id)) {
      devices.value.push(id)
    }
  }
  selectedDevices.value = []
  showAddDevice.value = false
}

function onDeviceStopped(deviceId) {
  devices.value = devices.value.filter((id) => id !== deviceId)
}

/**
 * 同步广播控制指令到所有投屏面板（排除发起者）
 * @param {string} sourceDeviceId - 发起操作的设备 ID
 * @param {string} method - 控制方法名（如 sendBack, sendHome 等）
 * @param {Array} args - 方法参数
 */
function broadcastControl(sourceDeviceId, method, args = []) {
  if (!syncMode.value) return
  for (const [id, panel] of Object.entries(panelRefs.value)) {
    if (id === sourceDeviceId || !panel?.control) continue
    const fn = panel.control[method]
    if (typeof fn === "function") {
      fn(...args)
    }
  }
}

async function stopAll() {
  // 前端先停止所有面板（断开 WS、停止解码）
  const panels = Object.values(panelRefs.value).filter((p) => p?.stopMirror)
  const withTimeout = (fn) =>
    Promise.race([fn(), new Promise((resolve) => setTimeout(resolve, 3000))])
  await Promise.all(panels.map((p) => withTimeout(() => p.stopMirror()).catch(() => {})))

  // 后端批量停止（确保 scrcpy 进程和端口转发释放）
  try {
    await fetch(`${getApiBase()}/api/mirror/stop-all`, { method: "POST" })
  } catch {
    /* ignore */
  }

  devices.value = []
  panelRefs.value = {}
}

async function goBack() {
  await stopAll()
  router.push("/")
}

onMounted(() => {
  // 订阅全局设备列表 WebSocket
  connectDeviceWs()
  fetchDevices()

  // 从 URL query 获取初始设备
  const deviceParam = route.query.device
  if (deviceParam) {
    const ids = Array.isArray(deviceParam) ? deviceParam : [deviceParam]
    devices.value = ids.filter(Boolean)
  }
})

let _cleaning = false

onUnmounted(() => {
  if (_cleaning) return
  _cleaning = true
  disconnectDeviceWs()
  for (const panel of Object.values(panelRefs.value)) {
    if (panel?.stopMirror) {
      panel.stopMirror().catch(() => {})
    }
  }
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
  padding: 8px 0 12px;
  border-bottom: 1px solid #333;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title {
  font-size: 15px;
  font-weight: 500;
  color: #e5eaf3;
}

.mirror-empty {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}

.mirror-grid {
  flex: 1;
  display: grid;
  gap: 8px;
  overflow: hidden;
}

.grid-1 {
  grid-template-columns: 1fr;
}

.grid-2 {
  grid-template-columns: repeat(2, 1fr);
}

.grid-4 {
  grid-template-columns: repeat(2, 1fr);
  grid-template-rows: repeat(2, 1fr);
}

.grid-6 {
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(2, 1fr);
}

.grid-9 {
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
}

.grid-manual-1 {
  grid-template-columns: 1fr;
}

.grid-manual-2 {
  grid-template-columns: repeat(2, 1fr);
}

.grid-manual-3 {
  grid-template-columns: repeat(3, 1fr);
}

.grid-manual-4 {
  grid-template-columns: repeat(4, 1fr);
}
</style>
