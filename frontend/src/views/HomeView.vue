<template>
  <div class="home-view">
    <div class="home-header">
      <h3>设备列表</h3>
      <el-button type="primary" :icon="Refresh" @click="refreshDevices">
        刷新
      </el-button>
    </div>
    <el-empty description="暂无已连接设备" />
  </div>
</template>

<script setup>
import { Refresh } from "@element-plus/icons-vue"

function refreshDevices() {
  // TODO: M2 阶段实现设备列表刷新
}
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
</style>
