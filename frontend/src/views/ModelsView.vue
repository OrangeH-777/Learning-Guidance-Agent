<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage } from '../api/session'
import type { ModelSettings } from '../types/business'
const form = reactive({ protocol: 'chat_completions', base_url: '', model_id: '', api_key: '' })
const settings = ref<ModelSettings>({ version: 0, configured: false }), busy = ref(true), message = ref(''), error = ref('')
async function load() {
  try { settings.value = (await api.get('/model-settings')).data; Object.assign(form, { protocol: settings.value.protocol ?? 'chat_completions', base_url: settings.value.base_url ?? '', model_id: settings.value.model_id ?? '', api_key: '' }) }
  catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
async function save() {
  busy.value = true; error.value = ''; message.value = ''
  try { settings.value = (await api.put('/model-settings', { ...form, api_key: form.api_key || null, expected_version: settings.value.version })).data; form.api_key = ''; message.value = '设置已保存，请完成连接测试后再生成。' }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function test() {
  busy.value = true; error.value = ''; message.value = ''
  try { await api.post('/model-settings/test'); await load(); message.value = '连接测试成功。' }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function remove() {
  if (!window.confirm('移除当前模型设置？已受理任务仍使用原配置版本。')) return
  busy.value = true
  try { await api.delete('/model-settings'); await load(); message.value = '当前设置已移除。' }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
onMounted(load)
</script>
<template><AppShell>
  <div class="page-heading"><p class="eyebrow">PERSONAL MODEL</p><h1>个人模型设置</h1><p class="muted">选择你自己的模型服务。密钥只在后端加密保存，页面不会返回明文。</p></div>
  <form class="panel narrow" @submit.prevent="save">
    <fieldset :disabled="busy">
    <label>接口协议<select v-model="form.protocol"><option value="chat_completions">OpenAI Chat Completions / 兼容接口</option><option value="responses">OpenAI Responses</option><option value="messages">Anthropic Messages</option><option value="gemini">Gemini 原生接口</option></select></label>
    <label>Base URL<input v-model="form.base_url" type="url" required placeholder="https://api.example.com/v1"><small>填写协议根地址，包含 /v1 或 /v1beta，不包含具体方法路径。</small></label>
    <label>模型 ID<input v-model="form.model_id" required v-codepoints="200" placeholder="填写服务商提供的模型名称"></label>
    <label>API Key<input v-model="form.api_key" type="password" autocomplete="off" :required="!settings.configured" :placeholder="settings.has_key ? '已保存；留空保留现有密钥' : '输入 API Key'"></label>
    <p class="notice">连接测试会向你选择的模型发送一条简短请求，可能产生费用。生成时会发送所选课程材料及必要的学习画像。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="message" role="status" class="success">{{ message }}</p>
    <div class="actions"><button :disabled="busy">保存设置</button><button type="button" class="secondary" :disabled="busy || !settings.configured" @click="test">连接测试（可能计费）</button><button type="button" class="text-button" :disabled="busy || !settings.configured" @click="remove">移除设置</button></div>
    <p class="muted">状态：{{ settings.tested_at ? '已通过连接测试' : '尚未测试' }}</p>
    </fieldset>
  </form>
</AppShell></template>
