<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage, session } from '../api/session'
import { focusSection } from '../composables/focusSection'

interface Source { id: string; title: string; source_url: string; section: string; license: string; review_status: string }
interface Course { id: string; name: string; version: string; active_index_version: string | null; sources: Source[] }
interface Job { id: string; course_id: string; index_version: string; status: string; chunks: number; error: string | null }
const route = useRoute(), router = useRouter()
const courses = ref<Course[]>([]), selected = ref(typeof route.query.course === 'string' ? route.query.course : '')
const action = ref(''), busy = computed(() => Boolean(action.value)), editingId = ref('')
const error = ref(''), message = ref(''), warnings = ref<string[]>([]), filename = ref('')
const editorOpen = ref(false), editorVersion = ref(''), original = ref('')
const listHeading = ref<HTMLElement | null>(null), editorHeading = ref<HTMLElement | null>(null), indexHeading = ref<HTMLElement | null>(null), errorPanel = ref<HTMLElement | null>(null)
const job = ref<Job | null>(null), allowUnreviewed = ref(false), costs = ref(false)
const form = reactive({ source_id: null as string | null, title: '', source_url: '', section: '', license: '', content: '', confirmed: false })
const fingerprint = () => JSON.stringify([form.title, form.source_url, form.section, form.license, form.content])
const dirty = computed(() => editorOpen.value && (!form.source_id || fingerprint() !== original.value || form.confirmed))
const course = computed(() => courses.value.find(c => c.id === selected.value))
const pendingCount = computed(() => course.value?.sources.filter(s => s.review_status !== 'approved').length ?? 0)
const running = computed(() => job.value?.status === 'running')
const jobCourse = computed(() => courses.value.find(c => c.id === job.value?.course_id))
const outdatedJob = computed(() => ['indexed', 'unchanged'].includes(job.value?.status ?? '') && jobCourse.value?.active_index_version !== job.value?.index_version)
const jobLabels: Record<string, string> = { running: '正在建立索引', indexed: '索引已生效', unchanged: '索引已生效', failed: '索引失败', interrupted: '索引已中断' }
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const jump = (target: 'list' | 'editor' | 'index') => focusSection(() => ({ list: listHeading.value, editor: editorHeading.value, index: indexHeading.value })[target])
function canDiscard() { return !dirty.value || !session.user || window.confirm('教材有尚未保存的内容，确定离开并放弃这些修改？') }
function clearEditor() {
  editorOpen.value = false
  Object.assign(form, { source_id: null, title: '', source_url: '', section: '', license: '', content: '', confirmed: false })
  warnings.value = []; filename.value = ''; editorVersion.value = ''; original.value = ''; error.value = ''; message.value = ''
}
function cancelEdit() { if (canDiscard()) { clearEditor(); void jump('list') } }
function resetCourse() { clearEditor(); allowUnreviewed.value = false; costs.value = false }
async function changeCourse(event: Event) {
  const input = event.target as HTMLSelectElement, next = input.value
  if (!canDiscard()) { input.value = selected.value; return }
  resetCourse(); selected.value = next
  await router.replace({ query: { ...route.query, course: next } })
}
watch(() => route.query.course, value => {
  if (typeof value === 'string' && value !== selected.value && courses.value.some(c => c.id === value)) {
    resetCourse(); selected.value = value
  }
})
watch(() => [form.content, form.title, form.source_url, form.section, form.license], () => { form.confirmed = false })
watch(error, value => { if (value && !disposed) void focusSection(() => errorPanel.value) })
onBeforeRouteLeave(canDiscard)
onBeforeRouteUpdate((to, from) => to.query.course === from.query.course || canDiscard())
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value && session.user) { event.preventDefault(); event.returnValue = '' } }
async function reload() {
  courses.value = (await api.get('/admin/courses')).data
  if (!selected.value || !courses.value.some(c => c.id === selected.value)) { resetCourse(); selected.value = courses.value[0]?.id ?? '' }
}
async function poll() {
  clearTimeout(timer)
  try {
    job.value = (await api.get('/admin/index')).data
    if (disposed) return
    if (running.value) timer = setTimeout(() => { void poll() }, 1000)
    else await reload()
  } catch (e) { if (!disposed) error.value = errorMessage(e) + ' 请点击刷新状态。' }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file || !canDiscard()) return
  error.value = ''
  if (file.size > 10 * 1024 * 1024) { error.value = '单文件不能超过10 MB。'; return }
  if (!/\.(md|pdf|docx)$/i.test(file.name)) { error.value = '请选择 Markdown、PDF 或 Word .docx 文件。'; return }
  const version = course.value?.version ?? ''
  action.value = 'preview'
  try {
    const { data } = await api.post('/admin/materials/preview', file, { params: { filename: file.name }, headers: { 'Content-Type': 'application/octet-stream' } })
    if (disposed) return
    clearEditor(); editorVersion.value = version; filename.value = file.name
    form.title = file.name.replace(/\.[^.]+$/, ''); form.content = data.content
    warnings.value = data.warnings; editorOpen.value = true
    message.value = '正文已提取。请校对内容并填写来源，保存后再建立索引。'
    await jump('editor')
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = '' }
}
async function edit(source: Source) {
  if (!canDiscard()) return
  action.value = 'edit'; editingId.value = source.id; error.value = ''; message.value = ''
  try {
    const { data } = await api.get(`/admin/courses/${selected.value}/materials/${source.id}`)
    if (disposed) return
    clearEditor()
    Object.assign(form, { source_id: source.id, title: data.title, source_url: data.source_url, section: data.section, license: data.license, content: data.content, confirmed: false })
    original.value = fingerprint(); editorVersion.value = data.version; editorOpen.value = true
    if (course.value) course.value.version = data.version
    await jump('editor')
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = ''; editingId.value = '' }
}
async function save() {
  if (!course.value || !form.confirmed) return
  action.value = 'save'; error.value = ''; message.value = ''
  try {
    const result = await api.post(`/admin/courses/${selected.value}/materials`, { ...form, expected_version: editorVersion.value })
    if (disposed) return
    // Successful POST remains successful even if the following catalog refresh fails.
    if (course.value) { course.value.version = result.data.version; course.value.active_index_version = null }
    clearEditor(); message.value = '公共教材已保存，请建立索引后使用。'
    await reload(); await jump('index')
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = '' }
}
async function build() {
  if (!course.value || !costs.value || dirty.value) return
  action.value = 'index'; error.value = ''; message.value = ''
  try {
    job.value = (await api.post(`/admin/courses/${selected.value}/index`, { expected_version: course.value.version, acknowledge_costs: true, allow_unreviewed: allowUnreviewed.value })).data
    if (!disposed) { await jump('index'); void poll() }
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = '' }
}
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload); action.value = 'load'
  try { await reload(); await poll() } catch (e) { error.value = errorMessage(e) }
  finally { action.value = '' }
})
onUnmounted(() => { disposed = true; clearTimeout(timer); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template><AppShell>
  <div class="page-heading"><p class="eyebrow">PUBLIC KNOWLEDGE</p><h1>公共教材管理</h1><p class="muted">上传、校对、建立索引。公共教材供所有用户使用；保存正文后还需建立索引才能检索。</p></div>
  <nav class="material-steps" aria-label="教材管理步骤">
    <button class="secondary" @click="jump('list')"><span>1</span>选择 / 上传</button>
    <button class="secondary" :disabled="!editorOpen" :aria-current="editorOpen ? 'step' : undefined" @click="jump('editor')"><span>2</span>校对 / 保存</button>
    <button class="secondary" :disabled="!course" @click="jump('index')"><span>3</span>建立索引</button>
  </nav>
  <p v-if="error" ref="errorPanel" tabindex="-1" class="error" role="alert">{{ error }}</p>
  <section class="panel" :aria-busy="busy">
    <h2 ref="listHeading" tabindex="-1">1. 课程与教材</h2>
    <p v-if="action === 'load'" class="loading" role="status">正在读取课程教材…</p>
    <label>教材所属课程<select :value="selected" :disabled="busy || running" @change="changeCourse"><option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>
    <p v-if="!courses.length && !busy" class="empty">暂无课程，请先配置课程目录并执行导入。</p>
    <template v-if="course">
      <div class="material-summary"><span class="badge">{{ course.active_index_version ? '可检索' : '待建立索引' }}</span><span>{{ course.sources.length }} 份教材 · {{ pendingCount }} 份待复核</span></div>
      <p v-if="!course.sources.length" class="empty">本课程还没有教材，从下方上传第一份资料。</p>
      <ul class="material-list"><li v-for="s in course.sources" :key="s.id" :class="{ 'selected-material': form.source_id === s.id && editorOpen }"><div class="source-description"><span>{{ s.title }} · {{ s.review_status === 'approved' ? '已确认' : '待复核' }}</span><small class="muted">{{ s.section }}</small></div><button class="secondary" :disabled="busy || running" @click="edit(s)">{{ action === 'edit' && editingId === s.id ? '读取中…' : '查看 / 校对' }}</button></li></ul>
      <label class="upload-area">上传教材<input type="file" accept=".md,.pdf,.docx" :disabled="busy || running" @change="upload"><small>单文件最多10 MB。支持 UTF-8 Markdown、文字版 PDF 和 Word .docx；扫描件先 OCR，旧版 .doc 先另存。</small></label>
      <p v-if="action === 'preview'" class="loading" role="status">正在提取教材正文，请稍候…完成后将自动定位到校对区。</p>
    </template>
  </section>
  <form v-if="editorOpen" class="panel material-editor" :aria-busy="action === 'save'" @submit.prevent="save">
    <div class="section-heading"><h2 ref="editorHeading" tabindex="-1">2. {{ form.source_id ? '校对已有教材' : '教材预览与来源' }}</h2><span class="badge">{{ dirty ? '尚未保存' : '正在查看' }}</span></div>
    <p class="muted">{{ course?.name }}<span v-if="filename"> · {{ filename }}</span> · 核对正文、公式和来源后确认保存。</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>
    <p v-for="warning in warnings" :key="warning" class="notice">{{ warning }}</p>
    <fieldset :disabled="busy || running">
      <div class="material-fields">
        <label>教材标题<input v-model="form.title" required v-codepoints="500"></label>
        <label>来源网址<input v-model="form.source_url" type="url" required v-codepoints="2000" placeholder="出版社或原始资料的 HTTP(S) 地址"></label>
        <label>章节 / 页码<input v-model="form.section" required v-codepoints="500"></label>
        <label>授权或使用依据<input v-model="form.license" required v-codepoints="500"></label>
      </div>
      <label>提取正文（可校正）<textarea v-model="form.content" rows="18" required v-codepoints="500000" class="material-content" spellcheck="false" /></label>
      <label class="check-line"><input v-model="form.confirmed" type="checkbox">我已核对正文与来源，有权将这些内容作为公共教材供所有用户使用。</label>
      <div class="actions editor-actions"><button :disabled="!form.confirmed || !form.content.trim()">{{ action === 'save' ? '正在保存…' : '确认并保存公共教材' }}</button><button type="button" class="secondary" @click="cancelEdit">取消</button><span class="muted">修改正文或来源后，需重新确认。</span></div>
    </fieldset>
  </form>
  <section v-if="course" class="panel">
    <h2 ref="indexHeading" tabindex="-1">3. 建立课程索引</h2>
    <p v-if="message && !editorOpen" class="success" role="status">{{ message }}</p>
    <p class="muted">上传和校对不调用模型。建立索引使用已配置的统一嵌入服务，会发送课程正文，可能计费。</p>
    <p v-if="dirty" class="notice">有未保存的教材，请先保存或取消编辑。<button class="text-button" @click="jump('editor')">返回校对区</button></p>
    <p v-else-if="pendingCount" class="notice">还有 {{ pendingCount }} 份教材待复核。逐份校对并确认，或仅在本地流程测试时允许未复核示例。</p>
    <label class="check-line"><input v-model="allowUnreviewed" type="checkbox" :disabled="busy || running">仅本地测试：允许未复核示例进入公共索引</label>
    <label class="check-line"><input v-model="costs" type="checkbox" :disabled="busy || running">确认向配置的嵌入服务发送课程正文，并承担可能的调用费用</label>
    <div class="actions"><button :disabled="busy || running || dirty || !costs || !course.sources.length || (pendingCount > 0 && !allowUnreviewed)" @click="build">{{ running ? '正在建立索引…' : '建立索引' }}</button><button class="secondary" :disabled="busy" @click="poll">刷新状态</button></div>
    <div v-if="job" class="index-result" :class="{ 'index-failed': job.status === 'failed' || job.status === 'interrupted' }" role="status"><small class="muted">最近一次构建</small><p>{{ jobCourse?.name ?? job.course_id }}：{{ outdatedJob ? '上次构建成功，教材已更新，请重新建立索引' : jobLabels[job.status] ?? job.status }}<span v-if="!outdatedJob && (job.status === 'indexed' || job.status === 'unchanged')">，{{ job.chunks }} 个知识片段</span></p><p v-if="running" class="muted">可以离开页面，返回后查看结果。后端停止会中断任务。</p><p v-if="job.error" class="error">{{ job.error }}</p></div>
    <p v-if="course.active_index_version" class="muted next-step">索引就绪后，前往<RouterLink to="/">工作台</RouterLink>选择该课程并生成资源。</p>
  </section>
</AppShell></template>

<style scoped>
.panel { margin-bottom: 1.5rem; }
.material-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
.material-steps button { text-align: left; display: flex; align-items: center; gap: 10px; }
.material-steps span { border: 1px solid #a9bfb3; border-radius: 50%; width: 28px; height: 28px; display: inline-grid; place-items: center; flex-shrink: 0; }
.material-summary, .section-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.section-heading h2 { margin: 0; }
.material-list { padding: 0; list-style: none; }
.material-list li { display: flex; gap: 1rem; align-items: center; justify-content: space-between; padding: 1rem .5rem; border-bottom: 1px solid #e3e7ed; }
.source-description { min-width: 0; overflow-wrap: anywhere; }
.source-description small { display: block; margin-top: 4px; }
.material-list button { flex-shrink: 0; }
.selected-material { background: #f0f6f1; border-radius: 8px; }
.upload-area { padding: 20px; margin-top: 24px; background: #f8faf6; border: 1px dashed #a9bfb3; border-radius: 10px; }
.material-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; }
.material-content { font-family: ui-monospace, monospace; white-space: pre-wrap; line-height: 1.75; min-height: 260px; }
.material-editor { border-color: #a9c1b1; }
.editor-actions { padding-top: 12px; border-top: 1px solid #e3e7ed; }
.check-line { display: flex; align-items: flex-start; gap: .6rem; margin: 1rem 0; font-weight: 500; }
.check-line input { width: auto; margin-top: .3rem; flex-shrink: 0; }
.index-result { margin-top: 20px; padding: 16px; border-radius: 8px; background: #eef5ef; }
.index-result p:last-child { margin-bottom: 0; }
.index-failed { background: #fff6f1; }
.next-step { margin-top: 18px; }
@media (max-width: 600px) {
  .material-list li { align-items: flex-start; flex-direction: column; }
  .material-fields { grid-template-columns: 1fr; }
  .material-steps { gap: 6px; }
  .material-steps button { flex-direction: column; align-items: flex-start; gap: 6px; padding: 10px; font-size: .8rem; }
  .upload-area { padding: 14px; }
}
</style>
