<script setup lang="ts">
import { ref } from 'vue'
import { getHealth } from '../api/client'

const checking = ref(false)
const status = ref('尚未检查后端连接。')

async function checkConnection() {
  checking.value = true
  try {
    const result = await getHealth()
    status.value = result.status === 'ok'
      ? '后端服务已连接。数据库和业务功能需单独验证。'
      : '后端返回了非正常状态，请检查服务。'
  } catch {
    status.value = '未能连接后端。请确认后端已在 8000 端口启动。'
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <main class="scaffold">
    <p class="eyebrow">Learning Guidance Agent · 项目骨架</p>
    <h1>个性化学习资源平台</h1>
    <p>根据学习基础、目标和偏好，通过多智能体协作生成课程讲解、练习题和文本思维导图。</p>
    <p>当前版本用于验证项目环境。账号、课程选择、画像、模型设置、知识检索和资源生成将在后续阶段实现。</p>
    <button type="button" :disabled="checking" @click="checkConnection">
      {{ checking ? '正在检查…' : '检查后端连接' }}
    </button>
    <p role="status" aria-live="polite">{{ status }}</p>
    <p class="hint">完整开发步骤与验收条件见项目根目录 plan.md，启动说明见 README.md。</p>
  </main>
</template>
