<template>
  <div class="home-view">
    <div class="home-header">
      <h3>设备列表</h3>
      <div class="header-actions">
        <el-button
          size="small"
          :disabled="androidOnlineCount === 0"
          @click="mirrorAllByPlatform('android')"
        >
          Android 全部投屏 ({{ androidOnlineCount }})
        </el-button>
        <el-button
          size="small"
          :disabled="iosOnlineCount === 0"
          @click="mirrorAllByPlatform('ios')"
        >
          iOS 全部投屏 ({{ iosOnlineCount }})
        </el-button>
        <el-button type="primary" :icon="Refresh" @click="onRefresh" :loading="refreshing">
          刷新
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="device-tabs">
      <el-tab-pane :label="`全部 (${devices.length})`" name="all" />
      <el-tab-pane :label="`Android (${androidDevices.length})`" name="android" />
      <el-tab-pane :label="`iOS (${iosDevices.length})`" name="ios" />
    </el-tabs>

    <div v-if="filteredDevices.length" class="device-grid">
      <DeviceCard v-for="d in filteredDevices" :key="d.id" :device="d" />
    </div>
    <el-empty v-else description="暂无已连接设备" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import { Refresh } from "@element-plus/icons-vue"
import { useDevices } from "@/composables/useDevices"
import DeviceCard from "@/components/DeviceCard.vue"

const router = useRouter()
const { devices, connect, disconnect, fetchDevices } = useDevices()
const refreshing = ref(false)
const activeTab = ref("all")

const androidDevices = computed(() => devices.value.filter(d => d.platform === "android"))
const iosDevices = computed(() => devices.value.filter(d => d.platform !== "android"))

const filteredDevices = computed(() => {
  if (activeTab.value === "android") return androidDevices.value
  if (activeTab.value === "ios") return iosDevices.value
  return devices.value
})

const androidOnlineCount = computed(() =>
  androidDevices.value.filter(d => d.status === "online").length
)
const iosOnlineCount = computed(() =>
  iosDevices.value.filter(d => d.status === "online").length
)

function mirrorAllByPlatform(platform) {
  const ids = devices.value
    .filter(d => d.platform === (platform === "android" ? "android" : "ios") && d.status === "online")
    .map(d => d.id)
  if (ids.length === 0) return
  router.push({ path: "/mirror", query: { device: ids } })
}

async function onRefresh() {
  refreshing.value = true
  await fetchDevices()
  refreshing.value = false
}

onMounted(() => {
  connect()
  fetchDevices()
})

onUnmounted(() => {
  disconnect()
})
</script>

<style scoped>
.home-view {
  height: 100%;
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.home-header h3 {
  font-size: 18px;
  color: #e5eaf3;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.device-tabs {
  margin-bottom: 16px;
}

.device-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.device-tabs :deep(.el-tabs__item) {
  color: #909399;
}

.device-tabs :deep(.el-tabs__item.is-active) {
  color: #409eff;
}

.device-tabs :deep(.el-tabs__item:hover) {
  color: #66b1ff;
}

.device-tabs :deep(.el-tabs__active-bar) {
  background-color: #409eff;
}

.device-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: #333;
}

.device-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: stretch;
}
</style>
