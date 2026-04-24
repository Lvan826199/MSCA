<template>
  <div class="home-view">
    <div class="home-header">
      <h3>设备列表</h3>
      <el-button type="primary" :icon="Refresh" @click="onRefresh" :loading="refreshing">
        刷新
      </el-button>
    </div>

    <div v-if="devices.length" class="device-grid">
      <DeviceCard v-for="d in devices" :key="d.id" :device="d" />
    </div>
    <el-empty v-else description="暂无已连接设备" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue"
import { Refresh } from "@element-plus/icons-vue"
import { useDevices } from "@/composables/useDevices"
import DeviceCard from "@/components/DeviceCard.vue"

const { devices, connect, disconnect, fetchDevices } = useDevices()
const refreshing = ref(false)

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
  margin-bottom: 20px;
}

.home-header h3 {
  font-size: 18px;
  color: #e5eaf3;
}

.device-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
</style>
