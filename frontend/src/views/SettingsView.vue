<template>
  <div class="settings-view">
    <h3>设置</h3>
    <el-form label-width="120px" style="margin-top: 20px; max-width: 500px;">
      <!-- 连接模式 -->
      <el-divider content-position="left">连接</el-divider>
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

      <!-- 投屏参数 -->
      <el-divider content-position="left">投屏参数</el-divider>
      <el-form-item label="最大帧率">
        <el-select v-model="settings.mirror.maxFps">
          <el-option :value="15" label="15 fps" />
          <el-option :value="30" label="30 fps" />
          <el-option :value="60" label="60 fps" />
        </el-select>
      </el-form-item>
      <el-form-item label="码率">
        <el-select v-model="settings.mirror.bitrate">
          <el-option :value="2_000_000" label="2 Mbps" />
          <el-option :value="4_000_000" label="4 Mbps" />
          <el-option :value="8_000_000" label="8 Mbps（默认）" />
          <el-option :value="16_000_000" label="16 Mbps" />
        </el-select>
      </el-form-item>
      <el-form-item label="最大分辨率">
        <el-select v-model="settings.mirror.maxSize">
          <el-option :value="0" label="不限制" />
          <el-option :value="720" label="720p" />
          <el-option :value="1080" label="1080p" />
          <el-option :value="1440" label="1440p" />
        </el-select>
      </el-form-item>

      <!-- 布局 -->
      <el-divider content-position="left">布局</el-divider>
      <el-form-item label="网格列数">
        <el-select v-model="settings.layout.gridColumns">
          <el-option :value="0" label="自动" />
          <el-option :value="1" label="1 列" />
          <el-option :value="2" label="2 列" />
          <el-option :value="3" label="3 列" />
          <el-option :value="4" label="4 列" />
        </el-select>
      </el-form-item>

      <!-- 操作 -->
      <el-divider />
      <el-form-item>
        <el-button type="warning" @click="resetSettings">恢复默认设置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { useConnection } from "@/composables/useConnection"
import { useSettings } from "@/composables/useSettings"

const { mode: connectionMode, remoteUrl, setMode } = useConnection()
const { settings, resetToDefaults } = useSettings()

function onModeChange(val) {
  setMode(val)
}

function resetSettings() {
  resetToDefaults()
}
</script>

<style scoped>
.settings-view h3 {
  font-size: 18px;
  color: #e5eaf3;
}
</style>
