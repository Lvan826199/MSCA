<template>
  <el-card class="device-card" :class="cardPlatformClass" shadow="hover">
    <div class="device-header">
      <div class="device-status">
        <span class="status-dot" :class="statusClass" />
        <span class="device-model" :title="displayName">{{ displayName }}</span>
      </div>
      <div class="platform-badge" :class="platformBadgeClass">
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
        <span class="info-value device-id-value" :title="device.id">
          {{ truncatedId }}
          <span class="copy-id-btn" @click.stop="copyDeviceId" title="复制设备 ID">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
          </span>
        </span>
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
      <el-button
        size="small"
        :disabled="device.status !== 'online' || installing"
        :loading="installing"
        @click="triggerInstall"
      >
        {{ installing ? '安装中' : '安装应用' }}
      </el-button>
      <input
        ref="fileInput"
        type="file"
        :accept="installAccept"
        style="display: none"
        @change="onFileSelected"
      />
    </div>

    <!-- AAB 签名配置对话框 -->
    <el-dialog
      v-model="showKeystoreDialog"
      title="AAB 签名配置"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top" size="default">
        <el-form-item label="签名密钥（可选，不选则使用 debug 签名）">
          <el-select
            v-model="selectedKeystore"
            placeholder="不使用签名"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="ks in keystoreList"
              :key="ks.name"
              :label="ks.name"
              :value="ks.path"
            />
          </el-select>
        </el-form-item>
        <template v-if="selectedKeystore">
          <el-form-item label="Keystore 密码">
            <el-input v-model="ksPass" type="password" show-password placeholder="请输入 keystore 密码" />
          </el-form-item>
          <el-form-item label="Key Alias">
            <el-input v-model="keyAlias" placeholder="请输入 key alias" />
          </el-form-item>
          <el-form-item label="Key 密码">
            <el-input v-model="keyPass" type="password" show-password placeholder="请输入 key 密码" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showKeystoreDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAabInstall">确认安装</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus/es/components/message/index"
import { useConnection } from "@/composables/useConnection"

const props = defineProps({
  device: { type: Object, required: true },
})

const router = useRouter()
const { getBackendUrl } = useConnection()

const installing = ref(false)
const fileInput = ref(null)

// AAB 签名相关
const showKeystoreDialog = ref(false)
const keystoreList = ref([])
const selectedKeystore = ref("")
const ksPass = ref("")
const keyAlias = ref("")
const keyPass = ref("")
const pendingAabFile = ref(null)

const displayName = computed(() => {
  const MAX_LEN = 18
  if (props.device.alias) {
    const model = props.device.model || props.device.id
    const full = `${props.device.alias}(${model})`
    if (full.length <= MAX_LEN) return full
    // 括号内容截断
    const prefix = props.device.alias
    const remain = MAX_LEN - prefix.length - 2 // 2 = '(' + ')'
    if (remain >= 2) {
      return `${prefix}(${model.slice(0, remain - 1)}…)`
    }
    // alias 本身就很长，直接截断
    return full.slice(0, MAX_LEN - 1) + "…"
  }
  const name = props.device.model || props.device.id
  return name.length > MAX_LEN ? name.slice(0, MAX_LEN - 1) + "…" : name
})

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

const truncatedId = computed(() => {
  const id = props.device.id || ""
  if (id.length > 16) {
    return id.slice(0, 6) + "..." + id.slice(-6)
  }
  return id
})

function copyDeviceId() {
  navigator.clipboard.writeText(props.device.id).then(() => {
    ElMessage.success("设备 ID 已复制")
  }).catch(() => {
    ElMessage.error("复制失败")
  })
}

const cardPlatformClass = computed(() => ({
  "card-android": props.device.platform === "android",
  "card-ios": props.device.platform !== "android",
}))

const platformBadgeClass = computed(() => ({
  "badge-android": props.device.platform === "android",
  "badge-ios": props.device.platform !== "android",
}))

function onMirror() {
  router.push({ path: "/mirror", query: { device: props.device.id } })
}

const installAccept = computed(() => {
  return props.device.platform === "android" ? ".apk,.apks,.aab" : ".ipa"
})

function triggerInstall() {
  fileInput.value?.click()
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  // 重置 input 以便重复选择同一文件
  e.target.value = ""

  // AAB 文件弹出签名配置对话框
  if (file.name.toLowerCase().endsWith(".aab")) {
    pendingAabFile.value = file
    await fetchKeystores()
    showKeystoreDialog.value = true
    return
  }

  await doInstall(file)
}

async function fetchKeystores() {
  try {
    const base = getBackendUrl()
    const res = await fetch(`${base}/api/install/keystores`)
    const data = await res.json()
    keystoreList.value = data.keystores || []
  } catch {
    keystoreList.value = []
  }
}

async function confirmAabInstall() {
  showKeystoreDialog.value = false
  const file = pendingAabFile.value
  pendingAabFile.value = null
  if (!file) return

  const signingOpts = selectedKeystore.value
    ? {
        keystore: selectedKeystore.value,
        ks_pass: ksPass.value,
        key_alias: keyAlias.value,
        key_pass: keyPass.value,
      }
    : null
  await doInstall(file, signingOpts)

  // 重置签名表单
  selectedKeystore.value = ""
  ksPass.value = ""
  keyAlias.value = ""
  keyPass.value = ""
}

async function doInstall(file, signingOpts = null) {
  installing.value = true
  try {
    const formData = new FormData()
    formData.append("file", file)

    if (signingOpts) {
      if (signingOpts.keystore) formData.append("keystore", signingOpts.keystore)
      if (signingOpts.ks_pass) formData.append("ks_pass", signingOpts.ks_pass)
      if (signingOpts.key_alias) formData.append("key_alias", signingOpts.key_alias)
      if (signingOpts.key_pass) formData.append("key_pass", signingOpts.key_pass)
    }

    const base = getBackendUrl()
    const res = await fetch(`${base}/api/install/${props.device.id}`, {
      method: "POST",
      body: formData,
    })

    const data = await res.json()
    if (data.success) {
      ElMessage.success(`${file.name} 安装成功`)
    } else {
      ElMessage.error(data.message || "安装失败")
    }
  } catch (err) {
    ElMessage.error(`安装出错: ${err.message}`)
  } finally {
    installing.value = false
  }
}
</script>
<style scoped>
.device-card {
  background: #1d1e1f;
  border: 1px solid #333;
  border-radius: 8px;
  width: 280px;
}

.device-card.card-android {
  border-left: 3px solid #3ddc84;
}

.device-card.card-ios {
  border-left: 3px solid #5ac8fa;
}

.device-card :deep(.el-card__body) {
  padding: 16px;
  display: flex;
  flex-direction: column;
  height: 100%;
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
  background: rgba(0, 122, 255, 0.15);
  color: #5ac8fa;
  border: 1px solid rgba(0, 122, 255, 0.3);
}

.platform-name {
  letter-spacing: 0.5px;
}

.device-info {
  margin-bottom: 12px;
  flex: 1;
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

.device-id-value {
  display: flex;
  align-items: center;
  gap: 4px;
}

.copy-id-btn {
  cursor: pointer;
  color: #909399;
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border-radius: 3px;
  transition: color 0.2s, background 0.2s;
}

.copy-id-btn:hover {
  color: #409eff;
  background: rgba(64, 158, 255, 0.1);
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
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid #2a2a2a;
}
</style>
