<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
    <el-aside width="260px" class="app-aside">
      <div class="app-logo">
        <h2>MSCA</h2>
        <span class="app-version">v0.1.0</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="app-menu"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>设备管理</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
      <div class="connection-status">
        <el-tag :type="connectionTag" size="small" effect="dark">
          {{ connectionText }}
        </el-tag>
      </div>
    </el-aside>
    <el-main class="app-main">
      <router-view />
    </el-main>
    </el-container>
  </el-config-provider>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import { Monitor, Setting } from "@element-plus/icons-vue"
import zhCn from "element-plus/es/locale/lang/zh-cn"
import { useWebSocket } from "@/composables/useWebSocket"

const route = useRoute()
const { status } = useWebSocket()

const connectionTag = computed(() => {
  if (status.value === "connected") return "success"
  if (status.value === "connecting") return "warning"
  return "danger"
})

const connectionText = computed(() => {
  if (status.value === "connected") return "已连接"
  if (status.value === "connecting") return "连接中..."
  return "未连接"
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.app-container {
  height: 100%;
}

.app-aside {
  background: #1d1e1f;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #333;
}

.app-logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #333;
}

.app-logo h2 {
  color: #409eff;
  font-size: 22px;
  letter-spacing: 2px;
}

.app-version {
  color: #909399;
  font-size: 12px;
}

.app-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: #262727;
  --el-menu-active-color: #409eff;
  --el-menu-text-color: #c0c4cc;
}

.app-menu .el-menu-item {
  color: #c0c4cc;
}

.app-menu .el-menu-item:hover {
  background: #262727;
}

.app-menu .el-menu-item.is-active {
  color: #409eff;
  background: #262727;
}

.connection-status {
  padding: 16px;
  text-align: center;
  border-top: 1px solid #333;
}

.app-main {
  background: #141414;
  color: #e5eaf3;
  padding: 20px;
}
</style>
