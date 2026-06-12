<template>
  <div class="logs-view">
    <div class="logs-header">
      <h3>运行日志</h3>
      <div class="logs-actions">
        <el-switch
          v-model="autoRefresh"
          active-text="自动刷新"
          size="small"
        />
        <el-button size="small" :loading="loading" @click="fetchLogs">刷新</el-button>
        <el-button size="small" @click="copyLogs">复制全部</el-button>
      </div>
    </div>
    <div v-if="logFile" class="logs-file-path">日志文件：{{ logFile }}</div>
    <div v-if="error" class="logs-error">{{ error }}</div>
    <div ref="logBodyRef" class="logs-body" @scroll="onScroll">
      <el-empty v-if="!lines.length && !error" description="暂无日志" />
      <pre v-else class="logs-pre">{{ lines.join("\n") }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted } from "vue"
import { ElMessage } from "element-plus/es/components/message/index"
import { useConnection } from "@/composables/useConnection"

const REFRESH_INTERVAL_MS = 2000
const FETCH_LINES = 1000

const lines = ref([])
const logFile = ref("")
const error = ref("")
const loading = ref(false)
const autoRefresh = ref(true)
const logBodyRef = ref(null)

let timer = null
// 用户停留在底部时跟随滚动，向上翻阅时不打扰
let stickToBottom = true

const { ready, getBackendUrl } = useConnection()

async function fetchLogs() {
  loading.value = true
  try {
    await ready
    const res = await fetch(`${getBackendUrl()}/api/logs?lines=${FETCH_LINES}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    lines.value = data.lines || []
    logFile.value = data.log_file || ""
    error.value = ""
    if (stickToBottom) {
      await nextTick()
      scrollToBottom()
    }
  } catch (e) {
    error.value = `日志获取失败：${e.message || e}`
  } finally {
    loading.value = false
  }
}

function scrollToBottom() {
  const el = logBodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function onScroll() {
  const el = logBodyRef.value
  if (!el) return
  stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
}

async function copyLogs() {
  if (!lines.value.length) return
  try {
    await navigator.clipboard.writeText(lines.value.join("\n"))
    ElMessage.success("日志已复制到剪贴板")
  } catch {
    ElMessage.error("复制失败，请手动选择文本复制")
  }
}

onMounted(() => {
  fetchLogs()
  timer = setInterval(() => {
    if (autoRefresh.value && !document.hidden) fetchLogs()
  }, REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.logs-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.logs-header h3 {
  margin: 0;
  font-size: 18px;
  color: #e5eaf3;
}

.logs-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logs-file-path {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  word-break: break-all;
}

.logs-error {
  color: #f56c6c;
  font-size: 13px;
  margin-bottom: 8px;
}

.logs-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: #141414;
  border: 1px solid #2b2b2c;
  border-radius: 6px;
  padding: 12px;
}

.logs-pre {
  margin: 0;
  font-family: Consolas, Monaco, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #c0c4cc;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
