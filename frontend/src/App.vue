<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-container">
    <el-aside width="260px" class="app-aside">
      <div class="app-logo">
        <h2>MSCA</h2>
        <span class="app-version">v0.1.0</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :router="!isElectron"
        class="app-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>设备管理</span>
        </el-menu-item>
        <el-menu-item index="/mirror">
          <el-icon><VideoCamera /></el-icon>
          <span>投屏监控</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <span>运行日志</span>
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
      <MirrorView v-if="mirrorMounted" v-show="route.name === 'Mirror'" />
      <router-view v-if="route.name !== 'Mirror'" />
    </el-main>
    <transition name="log-drawer">
      <aside v-if="isElectron && logDrawerOpen" class="log-drawer">
        <div class="log-drawer-header">
          <div class="log-drawer-title">
            <el-icon><Document /></el-icon>
            <span>运行日志</span>
          </div>
          <el-button :icon="Close" size="small" circle @click="logDrawerOpen = false" />
        </div>
        <LogsView />
      </aside>
    </transition>
    </el-container>
  </el-config-provider>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Close, Document, Monitor, Setting, VideoCamera } from "@element-plus/icons-vue"
import zhCn from "element-plus/es/locale/lang/zh-cn"
import { useWebSocket } from "@/composables/useWebSocket"
import { useConnection } from "@/composables/useConnection"
import LogsView from "@/views/LogsView.vue"
import MirrorView from "@/views/MirrorView.vue"

const route = useRoute()
const router = useRouter()
const { status } = useWebSocket()
const { isElectron } = useConnection()
const mirrorMounted = ref(route.name === "Mirror")
const logDrawerOpen = ref(false)

const activeMenu = computed(() => {
  if (isElectron && logDrawerOpen.value) return "/logs"
  return route.path
})

watch(
  () => route.name,
  (name) => {
    if (name === "Mirror") mirrorMounted.value = true
  },
  { immediate: true }
)

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

function handleMenuSelect(index) {
  if (!isElectron) return
  if (index === "/logs") {
    logDrawerOpen.value = !logDrawerOpen.value
    return
  }
  logDrawerOpen.value = false
  if (route.path !== index) {
    router.push(index)
  }
}
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
  min-height: 0;
  overflow: hidden;
}

.log-drawer {
  width: min(560px, 44vw);
  min-width: 420px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #18191a;
  border-left: 1px solid #333;
  box-shadow: -10px 0 28px rgba(0, 0, 0, 0.28);
  padding: 14px;
  z-index: 20;
}

.log-drawer-header {
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.log-drawer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e5eaf3;
  font-size: 15px;
  font-weight: 500;
}

.log-drawer .logs-view {
  min-height: 0;
}

.log-drawer .logs-header h3 {
  display: none;
}

.log-drawer .logs-header {
  margin-bottom: 8px;
}

.log-drawer .logs-actions {
  width: 100%;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.log-drawer-enter-active,
.log-drawer-leave-active {
  transition: width 0.18s ease, opacity 0.18s ease, transform 0.18s ease;
}

.log-drawer-enter-from,
.log-drawer-leave-to {
  width: 0;
  min-width: 0;
  opacity: 0;
  transform: translateX(24px);
  padding-left: 0;
  padding-right: 0;
}
</style>
