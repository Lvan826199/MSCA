<template>
  <el-card class="device-card" shadow="hover">
    <div class="device-header">
      <div class="device-status">
        <span class="status-dot" :class="statusClass" />
        <span class="device-model">{{ device.model || device.id }}</span>
      </div>
      <div class="platform-badge" :class="platformBadgeClass">
        <span class="platform-icon">{{ device.platform === 'android' ? 'A' : 'i' }}</span>
        <span class="platform-name">{{ device.platform === 'android' ? 'Android' : 'iOS' }}</span>
      </div>
    </div>

    <div class="device-info">
      <div class="info-row">
        <span class="info-label">状态</span>
        <span class="info-value status-text" :class="statusTextClass">{{ statusText }}</span>
      </div>
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
      <el-dropdown
        v-if="device.platform === 'android'"
        trigger="click"
        @command="onMoreAction"
      >
        <el-button size="small" :icon="MoreFilled" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="install">安装 APK</el-dropdown-item>
            <el-dropdown-item command="screenshot">截图</el-dropdown-item>
            <el-dropdown-item command="shell">ADB Shell</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { MoreFilled } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"

const props = defineProps({
  device: { type: Object, required: true },
})

const router = useRouter()

const statusClass = computed(() => ({
  online: props.device.status === "online",
  mirroring: props.device.status === "mirroring",
  offline: props.device.status === "offline",
}))

const statusText = computed(() => {
  const map = { online: "在线", mirroring: "投屏中", offline: "离线" }
  return map[props.device.status] || "未知"
})

const statusTextClass = computed(() => ({
  "text-online": props.device.status === "online",
  "text-mirroring": props.device.status === "mirroring",
  "text-offline": props.device.status === "offline",
}))

const platformBadgeClass = computed(() => ({
  "badge-android": props.device.platform === "android",
  "badge-ios": props.device.platform !== "android",
}))

function onMirror() {
  router.push({ path: "/mirror", query: { device: props.device.id } })
}

function onMoreAction(command) {
  ElMessage.info(`「${command}」功能开发中`)
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
  animation: pulse 1.5s infinite;
}

.status-dot.offline {
  background: #909399;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.device-model {
  font-size: 15px;
  font-weight: 500;
  color: #e5eaf3;
}

.platform-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.badge-android {
  background: rgba(61, 220, 132, 0.15);
  color: #3ddc84;
  border: 1px solid rgba(61, 220, 132, 0.3);
}

.badge-ios {
  background: rgba(147, 147, 149, 0.15);
  color: #a0a0a2;
  border: 1px solid rgba(147, 147, 149, 0.3);
}

.platform-icon {
  font-weight: 700;
  font-size: 13px;
}

.platform-name {
  letter-spacing: 0.5px;
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

.status-text {
  font-family: inherit;
  font-weight: 500;
}

.text-online {
  color: #67c23a;
}

.text-mirroring {
  color: #409eff;
}

.text-offline {
  color: #909399;
}

.device-actions {
  display: flex;
  gap: 8px;
}
</style>
