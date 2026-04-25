<template>
  <div class="device-control-bar">
    <!-- 导航键 -->
    <el-tooltip content="返回" placement="top">
      <el-button size="small" circle :icon="Back" @click="$emit('back')" />
    </el-tooltip>
    <el-tooltip content="主页" placement="top">
      <el-button size="small" circle :icon="HomeFilled" @click="$emit('home')" />
    </el-tooltip>
    <el-tooltip content="最近任务" placement="top">
      <el-button size="small" circle :icon="Menu" @click="$emit('recents')" />
    </el-tooltip>

    <el-divider direction="vertical" />

    <!-- 音量与电源 -->
    <el-tooltip content="音量+" placement="top">
      <el-button size="small" circle @click="$emit('volumeUp')">
        <span style="font-size: 14px;">+</span>
      </el-button>
    </el-tooltip>
    <el-tooltip content="音量-" placement="top">
      <el-button size="small" circle @click="$emit('volumeDown')">
        <span style="font-size: 14px;">-</span>
      </el-button>
    </el-tooltip>
    <el-tooltip content="电源" placement="top">
      <el-button size="small" circle :icon="SwitchButton" @click="$emit('power')" />
    </el-tooltip>

    <el-divider direction="vertical" />

    <!-- 通知栏/设置/旋转 -->
    <el-tooltip content="通知栏" placement="top">
      <el-button size="small" circle :icon="Bell" @click="$emit('expandNotification')" />
    </el-tooltip>
    <el-tooltip content="快捷设置" placement="top">
      <el-button size="small" circle :icon="Setting" @click="$emit('expandSettings')" />
    </el-tooltip>
    <el-tooltip content="收起面板" placement="top">
      <el-button size="small" circle :icon="ArrowUp" @click="$emit('collapsePanels')" />
    </el-tooltip>
    <el-tooltip content="旋转屏幕" placement="top">
      <el-button size="small" circle :icon="RefreshRight" @click="$emit('rotate')" />
    </el-tooltip>

    <el-divider direction="vertical" />

    <!-- 文本输入 -->
    <div class="text-input-group">
      <el-input
        v-model="textInput"
        size="small"
        placeholder="输入文本..."
        clearable
        @keyup.enter="onSendText"
      />
      <el-button size="small" type="primary" @click="onSendText" :disabled="!textInput">
        发送
      </el-button>
    </div>

    <!-- 剪贴板 -->
    <el-tooltip content="粘贴到设备" placement="top">
      <el-button size="small" circle :icon="DocumentCopy" @click="onPasteClipboard" />
    </el-tooltip>
  </div>
</template>

<script setup>
import { ref } from "vue"
import {
  Back, HomeFilled, Menu, SwitchButton,
  Bell, Setting, ArrowUp, RefreshRight, DocumentCopy,
} from "@element-plus/icons-vue"

const emit = defineEmits([
  "back", "home", "recents",
  "volumeUp", "volumeDown", "power",
  "expandNotification", "expandSettings", "collapsePanels",
  "rotate", "sendText", "clipboard",
])

const textInput = ref("")

function onSendText() {
  if (!textInput.value) return
  emit("sendText", textInput.value)
  textInput.value = ""
}

async function onPasteClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) emit("clipboard", text)
  } catch {
    // 浏览器不支持或用户拒绝权限
  }
}
</script>

<style scoped>
.device-control-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  background: #1d1e1f;
  border-top: 1px solid #333;
  flex-wrap: wrap;
}

.el-divider--vertical {
  height: 20px;
  margin: 0 4px;
}

.text-input-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.text-input-group .el-input {
  width: 140px;
}
</style>
