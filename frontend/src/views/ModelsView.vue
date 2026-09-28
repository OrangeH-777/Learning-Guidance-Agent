<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage, session } from '../api/session'
import type { ModelSettings } from '../types/business'
const form = reactive({ protocol: 'chat_completions', base_url: '', model_id: '', api_key: '' })
const settings = ref<ModelSettings>({ version: 0, configured: false }), busy = ref(true), message = ref(''), error = ref('')
const revealKey = ref(false)
interface ConfigurationRecord extends ModelSettings { created_at: string }
const history = ref<ConfigurationRecord[]>([]), historyPage = ref(1), historyTotal = ref(0), historyBusy = ref(false), historyError = ref('')
let historyRequest = 0
const protocolLabels: Record<string, string> = { chat_completions: 'Chat Completions', responses: 'Responses', messages: 'Anthropic Messages', gemini: 'Gemini' }
async function loadHistory(page = historyPage.value) {
  const request = ++historyRequest
  historyBusy.value = true; historyError.value = ''
  try {
    const { data } = await api.get('/model-settings/history', { params: { page, page_size: 10 } })
    if (request !== historyRequest) return
    history.value = data.items; historyPage.value = data.page; historyTotal.value = data.total
  } catch (e) { if (request === historyRequest) historyError.value = errorMessage(e) }
  finally { if (request === historyRequest) historyBusy.value = false }
}
const savedFields = computed(() => settings.value.configured ? { protocol: settings.value.protocol ?? 'chat_completions', base_url: settings.value.base_url ?? '', model_id: settings.value.model_id ?? '' } : { protocol: 'chat_completions', base_url: '', model_id: '' })
const hasUnsaved = computed(() => form.protocol !== savedFields.value.protocol || form.base_url !== savedFields.value.base_url || form.model_id !== savedFields.value.model_id || Boolean(form.api_key))
async function load() {
  settings.value = (await api.get('/model-settings')).data
  Object.assign(form, savedFields.value, { api_key: '' }); revealKey.value = false
}
async function save() {
  busy.value = true; error.value = ''; message.value = ''
  try { settings.value = (await api.put('/model-settings', { ...form, api_key: form.api_key || null, expected_version: settings.value.version })).data; Object.assign(form, { protocol: settings.value.protocol, base_url: settings.value.base_url, model_id: settings.value.model_id, api_key: '' }); revealKey.value = false; message.value = '设置已保存，请完成连接测试后再生成。'; await loadHistory(1) }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function test() {
  if (hasUnsaved.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await api.post('/model-settings/test'); await load(); message.value = '连接测试成功。'; await loadHistory() }
  catch (e) { settings.value.tested_at = undefined; error.value = errorMessage(e); await loadHistory() } finally { busy.value = false }
}
async function remove() {
  if (!window.confirm('移除当前模型设置？已受理任务仍使用原配置版本。')) return
  busy.value = true; error.value = ''; message.value = ''
  try { await api.delete('/model-settings'); await load(); message.value = '当前设置已移除。'; await loadHistory(1) }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
onMounted(() => { void load().catch(e => { error.value = errorMessage(e) }).finally(() => { busy.value = false }); void loadHistory() })
</script>
<template><AppShell>
  <div class="page-heading"><p class="eyebrow">PERSONAL MODEL</p><h1>个人模型设置</h1><p class="muted">填写模型服务商提供的模型 ID 和 API Key，与本站登录账号、密码无关。配置仅属于你，密钥加密保存且不会回显。</p></div>
  <form class="panel narrow" autocomplete="off" data-lpignore="true" data-1p-ignore @submit.prevent="save">
    <fieldset :disabled="busy">
    <label>接口协议<select v-model="form.protocol"><option value="chat_completions">OpenAI Chat Completions / 兼容接口</option><option value="responses">OpenAI Responses</option><option value="messages">Anthropic Messages</option><option value="gemini">Gemini 原生接口</option></select></label>
    <label>Base URL<input v-model="form.base_url" name="model-provider-endpoint" type="url" autocomplete="off" spellcheck="false" required placeholder="https://api.example.com/v1"><small>填写协议根地址，包含 /v1 或 /v1beta，不包含具体方法路径。</small></label>
    <label>模型 ID<input v-model="form.model_id" :name="`provider-model-id-${session.user?.id}`" autocomplete="off" data-lpignore="true" data-1p-ignore autocapitalize="off" spellcheck="false" required v-codepoints="200" placeholder="手动填写服务商提供的模型名称"></label>
    <label for="provider-api-token">API Key</label>
    <div class="credential-entry"><input id="provider-api-token" v-model="form.api_key" :name="`provider-api-token-${session.user?.id}`" type="text" :class="{ 'masked-credential': !revealKey }" autocomplete="off" data-lpignore="true" data-1p-ignore autocapitalize="off" spellcheck="false" :required="!settings.configured" :placeholder="settings.has_key ? '已保存；留空保留现有密钥' : '手动填写或粘贴模型服务商的 API Key'"><button type="button" class="secondary" :aria-pressed="revealKey" aria-controls="provider-api-token" @click="revealKey = !revealKey">{{ revealKey ? '隐藏密钥' : '显示密钥' }}</button></div>
    <p class="muted">模型 ID 由你填写，API Key 不是本站登录密码。已保存的密钥只显示保存状态。</p>
    <p class="notice">连接测试会向你选择的模型发送一条简短请求，可能产生费用。生成时会发送所选课程材料及必要的学习画像。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="message" role="status" class="success">{{ message }}</p>
    <div class="actions"><button :disabled="busy">保存设置</button><button type="button" class="secondary" :disabled="busy || !settings.configured || hasUnsaved" @click="test">连接测试（可能计费）</button><button type="button" class="text-button" :disabled="busy || !settings.configured" @click="remove">移除设置</button></div>
    <p class="muted">状态：{{ hasUnsaved ? '有未保存修改，请先保存' : settings.tested_at ? '已通过连接测试' : '尚未测试或需要重新验证' }}</p>
    </fieldset>
  </form>
  <section class="panel model-history" aria-labelledby="model-history-heading" :aria-busy="historyBusy">
    <div class="history-heading"><h2 id="model-history-heading">我的配置记录</h2><button type="button" class="secondary" :disabled="historyBusy" @click="loadHistory()">刷新记录</button></div>
    <p class="muted">仅展示你本人保存过的模型配置，最新版本用于新任务。API Key 只显示保存状态，不显示明文；登录账号和密码不属于模型配置。</p>
    <p v-if="historyError" class="error" role="alert">{{ historyError }}</p>
    <p v-if="historyBusy" class="loading" role="status">正在读取配置记录…</p>
    <p v-else-if="!history.length && !historyError" class="empty">尚无配置记录。填写并保存上方表单后，会在这里保留记录。</p>
    <div v-if="history.length" class="configuration-table"><table><caption class="sr-only">当前用户的模型配置历史</caption><thead><tr><th scope="col">版本 / 保存时间</th><th scope="col">协议 / 模型 ID</th><th scope="col">服务地址</th><th scope="col">密钥 / 状态</th></tr></thead><tbody><tr v-for="entry in history" :key="entry.version"><td data-label="版本 / 保存时间"><strong>v{{ entry.version }}</strong><span v-if="entry.version === settings.version" class="badge">最新</span><small>{{ new Date(entry.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</small></td><td data-label="协议 / 模型 ID">{{ protocolLabels[entry.protocol ?? ''] ?? entry.protocol }}<strong>{{ entry.model_id }}</strong></td><td data-label="服务地址">{{ entry.base_url }}</td><td data-label="密钥 / 状态">{{ entry.has_key ? '密钥已加密保存' : '无密钥' }}<small>{{ !entry.configured ? '已移除' : entry.tested_at ? '曾通过连接测试' : '尚未通过连接测试' }}</small></td></tr></tbody></table></div>
    <div v-if="historyTotal > 10" class="actions pagination"><button class="secondary" :disabled="historyBusy || historyPage <= 1" @click="loadHistory(historyPage - 1)">上一页配置</button><span>第 {{ historyPage }} 页 · 共 {{ historyTotal }} 条</span><button class="secondary" :disabled="historyBusy || historyPage * 10 >= historyTotal" @click="loadHistory(historyPage + 1)">下一页配置</button></div>
  </section>
</AppShell></template>

<style scoped>
.credential-entry { display: flex; gap: 10px; align-items: center; margin: -15px 0 10px; }
.credential-entry input { min-width: 0; margin: 0; }
.credential-entry button { flex-shrink: 0; }
.masked-credential { -webkit-text-security: disc; }
.model-history { margin-top: 28px; }
.history-heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 16px; }
.history-heading h2 { margin: 0; }
.configuration-table table { width: 100%; border-collapse: collapse; text-align: left; table-layout: fixed; }
.configuration-table th, .configuration-table td { padding: 14px 12px; vertical-align: top; border-bottom: 1px solid #dce3da; overflow-wrap: anywhere; }
.configuration-table th { background: #f6f8f4; font-size: .85rem; }
.configuration-table td small, .configuration-table td:nth-child(2) strong { display: block; margin-top: 5px; }
.configuration-table .badge { margin-left: 8px; }
@media (max-width: 650px) {
  .configuration-table thead { display: none; }
  .configuration-table table, .configuration-table tbody, .configuration-table tr, .configuration-table td { display: block; width: 100%; }
  .configuration-table tr { border: 1px solid #dce3da; border-radius: 9px; margin-bottom: 14px; padding: 8px; }
  .configuration-table td { border: 0; padding: 8px; }
  .configuration-table td::before { content: attr(data-label); display: block; font-size: .8rem; color: #65776e; margin-bottom: 4px; }
}
@media (max-width: 480px) { .credential-entry { flex-wrap: wrap; } .credential-entry button { padding: 6px 12px; } }
</style>
