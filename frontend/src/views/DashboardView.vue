<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage } from '../api/session'
import type { Course, ModelSettings, Profile, Task } from '../types/business'
const router = useRouter()
const courses = ref<Course[]>([]), courseId = ref(''), topic = ref(''), type = ref('lecture')
const profile = ref<Profile>({ version: 0, fields: null }), model = ref<ModelSettings>({ version: 0, configured: false })
const tasks = ref<Task[]>([]), error = ref(''), loading = ref(true), busy = ref(false), connection = ref('')
const profileLoading = ref(false)
let profileRequest = 0
let key = '', submittedParameters = '', disposed = false, timer: ReturnType<typeof setTimeout> | undefined
const controller = new AbortController()
const labels: Record<string, string> = { queued: '等待处理', planning: '规划中', generating: '生成中', validating: '核验中', formatting: '整理中', completed: '已完成', failed: '失败' }
async function loadProfile() {
  if (!courseId.value) return
  const requestId = ++profileRequest
  profileLoading.value = true
  profile.value = { version: 0, fields: null }
  try { const data = (await api.get(`/courses/${courseId.value}/profile`, { signal: controller.signal })).data; if (requestId === profileRequest) profile.value = data }
  catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { if (requestId === profileRequest) profileLoading.value = false }
}
async function refreshTasks() {
  clearTimeout(timer)
  try { tasks.value = (await api.get('/tasks', { signal: controller.signal })).data; connection.value = '' }
  catch (e) { if (!disposed) connection.value = '连接暂时失败，显示上次查询结果。服务端任务状态未改变。' }
  if (!disposed && (connection.value || tasks.value.some(t => !['completed', 'failed'].includes(t.status)))) timer = setTimeout(refreshTasks, 2000)
}
async function submit() {
  error.value = ''; busy.value = true
  const parameters = { course_id: courseId.value, topic: topic.value, resource_type: type.value, profile_version: profile.value.version, model_version: model.value.version }
  const signature = JSON.stringify(parameters)
  if (signature !== submittedParameters || !key) { key = crypto.randomUUID(); submittedParameters = signature }
  try { await api.post('/tasks', { ...parameters, request_key: key }); key = ''; await refreshTasks() }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
const retryKeys = new Map<string, string>()
async function retry(task: Task) {
  busy.value = true; error.value = ''
  if (!retryKeys.has(task.id)) retryKeys.set(task.id, crypto.randomUUID())
  try { await api.post(`/tasks/${task.id}/retry`, { request_key: retryKeys.get(task.id) }); retryKeys.delete(task.id); await refreshTasks() }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
watch(courseId, loadProfile)
onMounted(async () => {
  try {
    const [c, m] = await Promise.all([api.get('/courses'), api.get('/model-settings')])
    courses.value = c.data; model.value = m.data; courseId.value = courses.value.find(c => c.enabled)?.id ?? ''
    await refreshTasks()
  } catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
})
onUnmounted(() => { disposed = true; clearTimeout(timer); controller.abort() })
</script>
<template><AppShell>
  <div class="page-heading"><p class="eyebrow">YOUR LEARNING SPACE</p><h1>今天，想学懂什么？</h1><p class="muted">选择一个具体主题，生成与你的基础和目标相符的学习资源。</p></div>
  <p v-if="loading" class="loading" role="status">正在加载学习空间…</p>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <div class="grid">
    <form class="panel" @submit.prevent="submit"><h2>创建学习资源</h2>
      <label>课程<select v-model="courseId" :disabled="busy"><option v-for="c in courses" :key="c.id" :value="c.id" :disabled="!c.enabled">{{ c.name }}{{ c.knowledge_ready ? '' : ' · 知识索引待准备' }}</option></select></label>
      <label>学习主题<input v-model="topic" required v-codepoints="100" placeholder="例如：栈与括号匹配" :disabled="busy"></label>
      <label>资源类型<select v-model="type" :disabled="busy"><option value="lecture">概念讲解</option><option value="exercise">巩固练习</option><option value="mindmap">文本思维导图</option></select></label>
      <p v-if="!profile.version" class="notice">请先<RouterLink to="/profile">确认当前课程的学习画像</RouterLink>。</p>
      <p v-else class="muted">将使用画像版本 {{ profile.version }}：{{ profile.fields?.learning_goal }}</p>
      <p v-if="!model.tested_at" class="notice">请先<RouterLink to="/models">配置个人模型并测试连接</RouterLink>。</p>
      <p v-if="!courses.find(c => c.id === courseId)?.knowledge_ready" class="notice">课程知识索引尚未就绪。资料准备完成后可开始生成。</p>
      <button :disabled="busy || profileLoading || !profile.version || !model.tested_at || !courses.find(c => c.id === courseId)?.knowledge_ready">{{ busy ? '正在提交…' : '开始生成' }}</button>
    </form>
    <section class="panel"><div class="actions"><h2>最近任务</h2><button class="text-button" @click="refreshTasks">刷新</button></div>
      <p v-if="connection" class="error" role="status">{{ connection }}</p><p v-if="!tasks.length" class="empty">还没有生成任务。<br>从左侧选择一个主题开始。</p>
      <article v-for="task in tasks" :key="task.id" class="task-row"><div><strong>{{ task.topic }}</strong><p class="muted">{{ task.course_id }} · {{ new Date(task.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</p><p v-if="task.error_code" class="error">任务未完成：{{ task.error_code }}</p></div><div><span class="badge">{{ labels[task.status] ?? task.status }}</span><p><button v-if="task.resource_id" class="text-button" @click="router.push(`/resources/${task.resource_id}`)">查看资源</button><button v-if="task.status === 'failed'" class="text-button" :disabled="busy" @click="retry(task)">沿用原配置重试</button></p></div></article>
    </section>
  </div>
</AppShell></template>
