<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import TaskProgressPanel from '../components/TaskProgressPanel.vue'
import { api, errorMessage, session } from '../api/session'
import { focusSection } from '../composables/focusSection'
import type { Course, ModelSettings, Profile, Task } from '../types/business'
const router = useRouter()
const courses = ref<Course[]>([]), courseId = ref(''), topic = ref(''), type = ref('lecture')
const profile = ref<Profile>({ version: 0, fields: null }), model = ref<ModelSettings>({ version: 0, configured: false })
const tasks = ref<Task[]>([]), error = ref(''), loading = ref(true), busy = ref(false), connection = ref('')
const chapters = ref<{id: string; title: string; chapter_number: number; description: string}[]>([]), chapterId = ref('')
const selectedChapter = computed(() => chapters.value.find(c => c.id === chapterId.value))
const profileLoading = ref(false)
const currentTask = ref<Task | null>(null), historyError = ref(''), submissionError = ref('')
const progressRegion = ref<HTMLElement | null>(null)
const storageKey = `workspace-task:${session.user?.id}`
const terminal = (task: Task) => task.status === 'completed' || task.status === 'failed'
const processing = computed(() => currentTask.value !== null && !terminal(currentTask.value))
const submissionLocked = computed(() => busy.value || loading.value || processing.value)
const history = computed(() => tasks.value.filter(terminal))
const resourceTypes = { lecture: '概念讲解', exercise: '巩固练习', mindmap: '文本思维导图' }
const courseName = (id: string) => courses.value.find(c => c.id === id)?.name ?? id
let profileRequest = 0
let key = '', submittedParameters = '', disposed = false, timer: ReturnType<typeof setTimeout> | undefined
const controller = new AbortController()
async function loadProfile() {
  if (!courseId.value) return
  const requestId = ++profileRequest
  profileLoading.value = true
  profile.value = { version: 0, fields: null }
  chapters.value = []; chapterId.value = ''
  try {
    const base = `/courses/${courseId.value}`
    const [current, list] = await Promise.all([api.get(base + '/profile'), api.get(base + '/chapters')])
    if (requestId === profileRequest) { profile.value = current.data; chapters.value = list.data }
  }
  catch (e) { if (!disposed && requestId === profileRequest) error.value = errorMessage(e) }
  finally { if (requestId === profileRequest) profileLoading.value = false }
}
function remember(task: Task) {
  tasks.value = [task, ...tasks.value.filter(t => t.id !== task.id)].slice(0, 10)
}
async function poll(id: string) {
  try {
    const { data } = await api.get<Task>(`/tasks/${id}`, { signal: controller.signal })
    if (disposed || currentTask.value?.id !== id) return
    currentTask.value = data
    connection.value = ''
    if (terminal(data)) {
      remember(data)
      const openResult = sessionStorage.getItem(storageKey) === id
      if (data.status === 'failed' || data.resource_id) {
        if (openResult) sessionStorage.removeItem(storageKey)
        if (openResult && data.resource_id) await router.push(`/resources/${data.resource_id}`)
        return
      }
    }
  } catch (e) {
    if (disposed || currentTask.value?.id !== id) return
    if (isAxiosError(e) && [401, 403, 404].includes(e.response?.status ?? 0)) {
      sessionStorage.removeItem(storageKey)
      currentTask.value = null; connection.value = errorMessage(e)
      return
    }
    connection.value = '进度连接暂时中断，正在重新连接。'
  }
  if (!disposed && currentTask.value?.id === id) timer = setTimeout(() => poll(id), 1500)
}
async function loadTasks() {
  historyError.value = ''
  try {
    const { data } = await api.get<Task[]>('/tasks', { signal: controller.signal })
    if (disposed) return
    tasks.value = data
    if (!currentTask.value && !busy.value) {
      const saved = sessionStorage.getItem(storageKey)
      const task = data.find(t => t.id === saved) ?? data.find(t => !terminal(t))
      if (task) { currentTask.value = task; void poll(task.id) }
    }
  } catch (e) { if (!disposed) historyError.value = errorMessage(e) }
}
function beginSubmission() {
  busy.value = true; submissionError.value = ''; connection.value = ''
  if (window.matchMedia('(max-width: 850px)').matches) void focusSection(() => progressRegion.value)
}
function track(task: Task) {
  if (disposed) return
  clearTimeout(timer)
  remember(task)
  currentTask.value = task
  sessionStorage.setItem(storageKey, task.id)
  void poll(task.id)
}
async function submit() {
  if (submissionLocked.value) return
  beginSubmission()
  const parameters = { course_id: courseId.value, chapter_id: chapterId.value, topic: topic.value, resource_type: type.value, profile_version: profile.value.version, model_version: model.value.version }
  const signature = JSON.stringify(parameters)
  if (signature !== submittedParameters || !key) { key = crypto.randomUUID(); submittedParameters = signature }
  try { const { data } = await api.post<Task>('/tasks', { ...parameters, request_key: key }); key = ''; track(data) }
  catch (e) { submissionError.value = errorMessage(e) } finally { busy.value = false }
}
const retryKeys = new Map<string, string>()
async function retry(task: Task) {
  if (submissionLocked.value) return
  beginSubmission()
  if (!retryKeys.has(task.id)) retryKeys.set(task.id, crypto.randomUUID())
  try { const { data } = await api.post<Task>(`/tasks/${task.id}/retry`, { request_key: retryKeys.get(task.id) }); retryKeys.delete(task.id); track(data) }
  catch (e) { submissionError.value = errorMessage(e) } finally { busy.value = false }
}
watch(courseId, loadProfile)
onMounted(async () => {
  try {
    const [c, m] = await Promise.all([api.get('/courses'), api.get('/model-settings')])
    courses.value = c.data; model.value = m.data; courseId.value = courses.value.find(c => c.enabled)?.id ?? ''
    await loadTasks()
  } catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
})
onUnmounted(() => { disposed = true; clearTimeout(timer); controller.abort(); sessionStorage.removeItem(storageKey) })
</script>
<template><AppShell>
  <div class="page-heading"><h1>今天，想学懂什么？</h1><p class="muted">选择一个具体主题，生成与你的基础和目标相符的学习资源。</p></div>
  <p v-if="loading" class="loading" role="status">正在加载学习空间…</p>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <div class="grid workspace">
    <form class="panel" @submit.prevent="submit"><h2>创建学习资源</h2>
      <div class="field-pair"><label>课程<select v-model="courseId" :disabled="busy"><option v-for="c in courses" :key="c.id" :value="c.id" :disabled="!c.enabled">{{ c.name }}</option></select></label>
      <label>教材章节<select v-model="chapterId" required :disabled="busy || profileLoading"><option disabled value="">请选择已校对章节</option><option v-for="c in chapters" :key="c.id" :value="c.id">第 {{ c.chapter_number }} 章 · {{ c.title }}</option></select></label>
      </div>
      <p v-if="selectedChapter?.description" class="muted">{{ selectedChapter.description }}</p>
      <label>学习需求<textarea rows="3" v-model="topic" required v-codepoints="100" placeholder="例如：用括号匹配的例子解释栈的入栈和出栈。" :disabled="busy"></textarea></label>
      <fieldset class="resource-types" :disabled="busy"><legend>资源类型</legend><div>
        <label v-for="(name, value) in resourceTypes" :key="value"><input type="radio" v-model="type" :value="value" name="resource-type">{{ name }}</label>
      </div></fieldset>
      <template v-if="!loading && !profileLoading"><p v-if="!profile.version" class="notice">请先<RouterLink to="/profile">确认当前课程的学习画像</RouterLink>。</p>
      <p v-else class="muted">将使用画像版本 {{ profile.version }}：{{ profile.fields?.learning_goal }}</p>
      <p v-if="!model.tested_at" class="notice">请先<RouterLink to="/models">配置个人模型并测试连接</RouterLink>。</p>
      <p v-if="!loading && !profileLoading && !chapters.length" class="notice">本课程暂无已校对章节，请联系管理员校对并保存教材。</p>
      </template>
      <div class="submit-row"><button :disabled="submissionLocked || profileLoading || !profile.version || !model.tested_at || !chapterId || !topic.trim()">{{ busy ? '正在提交…' : processing ? '任务进行中' : '开始生成' }}</button>
      <small class="muted">所选章节正文与学习需求将发送至你的模型。</small></div>
    </form>
    <div ref="progressRegion" tabindex="-1" class="progress-region">
      <p v-if="submissionError" role="alert" class="error">{{ submissionError }}</p>
      <TaskProgressPanel :task="busy ? null : currentTask" :submitting="busy" :connection="connection" :course="currentTask ? courseName(currentTask.course_id) : ''" @retry="retry" />
    </div>
  </div>
  <details class="panel task-history"><summary>最近生成记录</summary>
    <p v-if="historyError" class="notice">{{ historyError }} <button class="text-button" @click="loadTasks">重新读取</button></p>
    <p v-else-if="!history.length" class="muted">暂无已结束的生成任务。</p>
    <article v-for="task in history" :key="task.id" class="task-row"><div><strong>{{ task.topic }}</strong><p class="muted">{{ courseName(task.course_id) }} · {{ new Date(task.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</p></div>
      <div><RouterLink v-if="task.resource_id" :to="`/resources/${task.resource_id}`">查看资源</RouterLink>
        <template v-else-if="task.status === 'failed'"><small>未完成 · {{ task.error_code }}</small><button class="text-button" :disabled="submissionLocked" @click="retry(task)">沿用原配置重试</button></template></div>
    </article>
    <RouterLink to="/history">查看全部学习资源 →</RouterLink>
  </details>
</AppShell></template>
<style scoped>
.workspace { grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); }
.resource-types { margin-bottom: 20px; }
.resource-types legend { margin-bottom: 8px; padding: 0; font-weight: 600; }
.resource-types > div { display: flex; gap: 8px; flex-wrap: wrap; }
.resource-types label { display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--rule); border-radius: 8px; padding: 8px 12px; font-size: .9rem; margin: 0; cursor: pointer; }
.resource-types label:has(:checked) { background: #edf5ef; border-color: #658d79; color: #245840; }
.resource-types input { width: 1em; height: 1em; margin: 0; accent-color: #256a57; }
.submit-row { border-top: 1px solid var(--rule); padding-top: 16px; display: flex; gap: 10px 16px; align-items: center; flex-wrap: wrap; }
.submit-row small { font-size: .82rem; }
.task-history { margin-top: 20px; padding-block: 14px; }
.task-history summary { font-weight: 650; color: var(--pine); }
.task-history .task-row { align-items: center; }
.task-row small { display: block; }
@media(max-width: 850px) { .workspace { grid-template-columns: minmax(0, 1fr); gap: 16px; } }
@media(max-width: 520px) { .resource-types label { padding: 7px 9px; } .task-row { flex-wrap: wrap; } }
</style>
