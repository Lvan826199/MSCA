<template>
  <div class="device-control-bar">
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
  </div>
</template>

<script setup>
import { Back, HomeFilled, Menu, SwitchButton } from "@element-plus/icons-vue"

defineEmits(["back", "home", "recents", "volumeUp", "volumeDown", "power"])
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
}

.el-divider--vertical {
  height: 20px;
  margin: 0 4px;
}
</style>
