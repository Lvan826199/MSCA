<template>
  <el-card class="device-card" shadow="hover">
    <div class="device-header">
      <div class="device-status">
        <span class="status-dot" :class="statusClass" />
        <span class="device-model">{{ device.model || device.id }}</span>
      </div>
      <el-tag :type="platformTag" size="small" effect="plain">
        {{ device.platform === 'android' ? 'Android' : 'iOS' }}
      </el-tag>
    </div>

    <div class="device-info">
      <div class="info-row">
        <span class="info-label">设备 ID</span>
        <span class="info-value">{{ device.id }}</span>
      </div>
      <div v-if="device.version" class="info-row">
        <span class="info-label">系统版本</span>
        <span class="info-value">{{ device.platform === 'android' ? 'Android ' : 'iOS ' }}{{ device.version }}</span>
      </div>
      <div v-if="device.resolution" class="info-row">
        <span class="info-label">分辨率</span>
        <span class="info-value">{{ device.resolution }}</span>
      </div>
    </div>

    <div class="device-actions">
      <el-button
        type="primary"
        size="small"
        :disabled="device.status !== 'online'"
        @click="onMirror"
      >
        投屏
      </el-button>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"

const props = defineProps({
  device: { type: Object, required: true },
})

const router = useRouter()

const statusClass = computed(() => ({
  online: props.device.status === "online",
  mirroring: props.device.status === "mirroring",
  offline: props.device.status === "offline",
}))

const platformTag = computed(() =>
  props.device.platform === "android" ? "success" : ""
)

function onMirror() {
  router.push({ path: "/mirror", query: { device: props.device.id } })
}
</script>
<style scoped>
.device-card {
  background: #1d1e1f;
  border: 1px solid #333;
  border-radius: 8px;
  width: 280px;
}

.device-card :deep(.el-card__body) {
  padding: 16px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.device-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
}

.status-dot.online {
  background: #67c23a;
}

.status-dot.mirroring {
  background: #409eff;
}

.status-dot.offline {
  background: #909399;
}

.device-model {
  font-size: 15px;
  font-weight: 500;
  color: #e5eaf3;
}

.device-info {
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}

.info-label {
  color: #909399;
}

.info-value {
  color: #c0c4cc;
  font-family: monospace;
}

.device-actions {
  display: flex;
  gap: 8px;
}
</style>
