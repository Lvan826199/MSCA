<template>
  <div class="settings-view">
    <h3>设置</h3>
    <el-form label-width="120px" style="margin-top: 20px; max-width: 500px;">
      <el-form-item label="连接模式">
        <el-select v-model="connectionMode" @change="onModeChange">
          <el-option label="自动" value="auto" />
          <el-option label="仅本地" value="local" />
          <el-option label="仅远程" value="remote" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="connectionMode === 'remote'" label="远程地址">
        <el-input v-model="remoteUrl" placeholder="wss://example.com" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { useConnection } from "@/composables/useConnection"

const { mode: connectionMode, remoteUrl, setMode } = useConnection()

function onModeChange(val) {
  setMode(val)
}
</script>

<style scoped>
.settings-view h3 {
  font-size: 18px;
  color: #e5eaf3;
}
</style>
