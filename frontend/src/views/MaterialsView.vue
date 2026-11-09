<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import TextContent from '../components/TextContent.vue'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage, session } from '../api/session'
import { focusSection } from '../composables/focusSection'

interface Source { id: string; title: string; chapter_number: number; description: string; source_url: string; section: string; license: string; review_status: string }
interface Course { id: string; name: string; version: string; sources: Source[] }
const route = useRoute(), router = useRouter()
const courses = ref<Course[]>([]), selected = ref(typeof route.query.course === 'string' ? route.query.course : '')
const action = ref(''), busy = computed(() => Boolean(action.value)), editingId = ref('')
const error = ref(''), message = ref(''), warnings = ref<string[]>([]), filename = ref('')
const editorOpen = ref(false), editorVersion = ref(''), original = ref('')
const listHeading = ref<HTMLElement | null>(null), editorHeading = ref<HTMLElement | null>(null), errorPanel = ref<HTMLElement | null>(null)
const blankChapter = { source_id: null as string | null, chapter_number: 1, title: '', description: '', source_url: '', section: '', license: '', content: '', confirmed: false }
const form = reactive({ ...blankChapter })
const previewOpen = ref(true)
const fingerprint = () => JSON.stringify([form.chapter_number, form.title, form.description, form.source_url, form.section, form.license, form.content])
const dirty = computed(() => editorOpen.value && (!form.source_id || fingerprint() !== original.value || form.confirmed))
const course = computed(() => courses.value.find(c => c.id === selected.value))
const pendingCount = computed(() => course.value?.sources.filter(s => s.review_status !== 'approved').length ?? 0)
let disposed = false
const step = computed(() => route.params.step || 'list')
const newName = ref(''), newDescription = ref('')
async function createCourse() {
  action.value = 'create'; error.value = ''
  try {
    const { data } = await api.post('/admin/courses', { name: newName.value.trim(), description: newDescription.value.trim() })
    courses.value.push(data); selected.value = data.id; resetCourse()
    newName.value = ''; newDescription.value = ''
    await router.replace({ query: { course: data.id } })
    message.value = '课程已创建，请上传第一份教材。'
  } catch (e) { error.value = errorMessage(e) } finally { action.value = '' }
}
async function jump(target: 'list' | 'editor') {
  const path = '/admin/materials' + ({ list: '', editor: '/review' })[target]
  const result = await router.push({ path, query: { course: selected.value, source: target === 'editor' ? form.source_id || undefined : undefined } })
  if (result && route.path !== path) return
  await focusSection(() => ({ list: listHeading.value, editor: editorHeading.value })[target])
}
function canDiscard() { return !dirty.value || !session.user || window.confirm('教材有尚未保存的内容，确定离开并放弃这些修改？') }
function clearEditor() {
  previewOpen.value = true
  editorOpen.value = false
  Object.assign(form, blankChapter)
  warnings.value = []; filename.value = ''; editorVersion.value = ''; original.value = ''; error.value = ''; message.value = ''
}
function cancelEdit() { if (canDiscard()) { clearEditor(); void jump('list') } }
function resetCourse() { clearEditor() }
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
watch(fingerprint, () => { form.confirmed = false })
watch(error, value => { if (value && !disposed) void focusSection(() => errorPanel.value) })
onBeforeRouteLeave(canDiscard)
onBeforeRouteUpdate((to, from) => from.params.step !== 'review' || (to.fullPath === from.fullPath) || canDiscard())
watch(() => route.fullPath, async () => {
  if (step.value !== 'review') {
    if (editorOpen.value) clearEditor()
    return
  }
  if (!busy.value && typeof route.query.source === 'string' && form.source_id !== route.query.source) {
    const source = course.value?.sources.find(s => s.id === route.query.source)
    if (source) await edit(source)
  }
})
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value && session.user) { event.preventDefault(); event.returnValue = '' } }
async function reload() {
  courses.value = (await api.get('/admin/courses')).data
  if (!selected.value || !courses.value.some(c => c.id === selected.value)) { resetCourse(); selected.value = courses.value[0]?.id ?? '' }
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
    const lastNumber = course.value?.sources.at(-1)?.chapter_number ?? 0
    form.chapter_number = data.suggested_chapter_number ?? Math.min(999999, lastNumber + 1)
    form.title = file.name.replace(/\.[^.]+$/, ''); form.content = data.content
    warnings.value = data.warnings; editorOpen.value = true
    message.value = '已提取正文。请核对章号与名称，填写来源后保存。'
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
    Object.assign(form, { source_id: source.id, chapter_number: data.chapter_number, title: data.title, description: data.description, source_url: data.source_url, section: data.section, license: data.license, content: data.content, confirmed: false })
    original.value = fingerprint(); editorVersion.value = data.version; editorOpen.value = true
    await jump('editor')
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = ''; editingId.value = '' }
}
async function removeChapter(source: Source) {
  const current = course.value
  if (!current || busy.value || !window.confirm(`从《${current.name}》删除第 ${source.chapter_number} 章「${source.title}」？删除后，学生将无法再选择本章，已生成的资源仍可查看。`)) return
  action.value = 'delete'; error.value = ''; message.value = ''
  try {
    const { data } = await api.delete(`/admin/courses/${current.id}/materials/${source.id}`, { params: { expected_version: current.version } })
    current.sources = current.sources.filter(s => s.id !== source.id)
    current.version = data.version
    message.value = `已删除第 ${source.chapter_number} 章「${source.title}」。`
  } catch (e) { error.value = errorMessage(e) }
  finally { action.value = '' }
}
async function refreshDirectory() {
  action.value = 'load'; error.value = ''
  try { await reload() } catch (e) { error.value = errorMessage(e) } finally { action.value = '' }
}
async function save() {
  if (!course.value || !form.confirmed) return
  action.value = 'save'; error.value = ''; message.value = ''
  try {
    const result = await api.post(`/admin/courses/${selected.value}/materials`, { ...form, expected_version: editorVersion.value })
    if (disposed) return
    // Successful POST remains successful even if the following catalog refresh fails.
    if (course.value) { course.value.version = result.data.version }
    clearEditor(); message.value = '公共教材已保存，可在工作台选择本章。'
    await reload(); await jump('list')
  } catch (e) { if (!disposed) error.value = errorMessage(e) }
  finally { action.value = '' }
}
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload); action.value = 'load'
  try { await reload()
    if (step.value === 'review' && typeof route.query.source === 'string') {
      const source = course.value?.sources.find(s => s.id === route.query.source)
      if (source) await edit(source)
    }
  } catch (e) { error.value = errorMessage(e) }
  finally { action.value = '' }
})
onUnmounted(() => { disposed = true; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template><AppShell>
  <div class="page-heading"><h1>公共教材管理</h1><p class="muted">维护课程的章节目录。校对保存后，学生即可在工作台选择对应章节。</p></div>
  <nav class="material-steps" aria-label="教材管理步骤">
    <button class="secondary" :disabled="busy" @click="jump('list')"><span>1</span>选择 / 上传</button>
    <button class="secondary" :disabled="busy || !editorOpen" :aria-current="editorOpen ? 'step' : undefined" @click="jump('editor')"><span>2</span>校对 / 保存</button>
  </nav>
  <p v-if="error" ref="errorPanel" tabindex="-1" class="error" role="alert">{{ error }}</p>
  <section v-if="step === 'list'" class="panel" :aria-busy="busy">
    <h2 ref="listHeading" tabindex="-1">1. 课程与教材</h2>
    <p v-if="action === 'load'" class="loading" role="status">正在读取课程教材…</p>
    <details><summary>新建课程</summary><form @submit.prevent="createCourse"><label>课程名称<input v-model="newName" required maxlength="100"></label><label>课程简介（选填）<input v-model="newDescription" maxlength="500"></label><button :disabled="busy || !newName.trim()">创建课程</button></form></details>
    <p v-if="message" class="success" role="status">{{ message }}</p>
    <label>教材所属课程<select :value="selected" :disabled="busy" @change="changeCourse"><option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>
    <p v-if="!courses.length && !busy" class="empty">暂无课程，点击“新建课程”即可添加。</p>
    <template v-if="course">
      <label class="upload-area">按章节上传教材
        <small>每次上传一章，每章一个文件。整本教材请先按章拆分；上传后可修改章号、名称、简介和正文。</small>
        <input type="file" accept=".md,.pdf,.docx" :disabled="busy" @change="upload">
        <small>支持 Word（.docx）、文字版 PDF、UTF-8 Markdown，每个文件最多 10 MB。扫描版 PDF 请先 OCR。</small>
      </label>
      <p v-if="action === 'preview'" class="loading" role="status">正在提取教材正文，请稍候…完成后将自动定位到校对区。</p>
      <div class="directory-heading"><div><h3>章节目录</h3><small class="muted">共 {{ course.sources.length }} 章 · {{ pendingCount }} 章待复核 · 按章号排列</small></div><button class="text-button" :disabled="busy" @click="refreshDirectory">刷新目录</button></div>
      <p v-if="!course.sources.length" class="empty">本课程暂无章节，请先上传第一章教材。</p>
      <ol class="material-list"><li v-for="s in course.sources" :key="s.id">
        <div class="source-description"><small class="chapter-label">第 {{ s.chapter_number }} 章 · {{ s.review_status === 'approved' ? '已校对' : '待复核' }}</small><strong>{{ s.title }}</strong><p v-if="s.description">{{ s.description }}</p><small class="muted">{{ s.section }}</small></div>
        <div class="chapter-actions"><button class="secondary" :disabled="busy" @click="edit(s)">{{ action === 'edit' && editingId === s.id ? '读取中…' : '编辑 / 校对' }}</button>
        <button class="delete-chapter" :aria-label="`删除章节：${s.title}`" :disabled="busy" @click="removeChapter(s)">删除</button></div>
      </li></ol>
    </template>
  </section>
  <form v-if="step === 'review' && editorOpen" class="panel material-editor" :aria-busy="action === 'save'" @submit.prevent="save">
    <div class="section-heading"><h2 ref="editorHeading" tabindex="-1">2. {{ form.source_id ? '校对已有教材' : '教材预览与来源' }}</h2><span class="badge">{{ dirty ? '尚未保存' : '正在查看' }}</span></div>
    <p class="muted">{{ course?.name }}<span v-if="filename"> · {{ filename }}</span> · 核对正文、公式和来源后确认保存。</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>
    <p v-for="warning in warnings" :key="warning" class="notice">{{ warning }}</p>
    <fieldset :disabled="busy">
      <div class="material-fields">
        <label>章号<input type="number" v-model.number="form.chapter_number" required min="1" max="999999" step="1"><small>目录按数字升序展示。</small></label>
        <label>章节名称<input v-model="form.title" required v-codepoints="500"></label>
        <label class="chapter-intro">章节简介（选填）<textarea v-model="form.description" v-codepoints="500" rows="2" placeholder="这章介绍哪些概念？学生会学到什么？"></textarea></label>
        <label>来源网址<input v-model="form.source_url" type="url" required v-codepoints="2000" placeholder="出版社或原始资料的 HTTP(S) 地址"></label>
        <label>章节 / 页码<input v-model="form.section" required v-codepoints="500"></label>
        <label>授权或使用依据<input v-model="form.license" required v-codepoints="500"></label>
      </div>
      <div class="actions editor-mode"><strong>教材正文</strong><button type="button" class="secondary" :aria-expanded="previewOpen" @click="previewOpen = !previewOpen">{{ previewOpen ? '编辑正文' : '预览 Markdown' }}</button></div>
      <section v-if="previewOpen" class="chapter-preview" aria-label="正文预览"><TextContent v-if="form.content.trim()" :text="form.content" /><p v-else class="muted">暂无正文。</p></section>
      <label v-else>提取正文（可校正）<textarea v-model="form.content" rows="18" required v-codepoints="500000" class="material-content" spellcheck="false" /></label>
      <label class="check-line"><input v-model="form.confirmed" type="checkbox">我已核对正文与来源，有权将这些内容作为公共教材供所有用户使用。</label>
      <div class="actions editor-actions"><button :disabled="!form.confirmed || !form.content.trim()">{{ action === 'save' ? '正在保存…' : '确认并保存公共教材' }}</button><button type="button" class="secondary" @click="cancelEdit">取消</button><span class="muted">修改正文或来源后，需重新确认。</span></div>
    </fieldset>
  </form>
  <section v-if="step === 'review' && !editorOpen && !busy" class="panel"><h2>校对教材</h2><p>请先选择教材。未保存的上传预览刷新后需要重新上传。</p><button @click="jump('list')">返回课程与教材</button></section>
</AppShell></template>

<style scoped>
.panel { margin-bottom: 1.5rem; }
.material-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 24px; }
.material-steps button { text-align: left; display: flex; align-items: center; gap: 10px; }
.material-steps span { border: 1px solid #a9bfb3; border-radius: 50%; width: 28px; height: 28px; display: inline-grid; place-items: center; flex-shrink: 0; }
.material-summary, .section-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.section-heading h2 { margin: 0; }
.material-list { padding: 0; list-style: none; }
.material-list li { display: flex; gap: 1rem; align-items: center; justify-content: space-between; padding: 1rem .5rem; border-bottom: 1px solid #e3e7ed; }
.source-description { min-width: 0; overflow-wrap: anywhere; }
.source-description small { display: block; margin-top: 4px; }
.source-description strong { display: block; font-size: 1.06rem; }
.source-description p { margin: .25rem 0; white-space: pre-line; }
.chapter-label { color: #37654e; }
.directory-heading, .chapter-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.directory-heading h3 { margin: 0; }
.chapter-actions { flex-shrink: 0; }
.delete-chapter { color: #963f34; background: transparent; padding: 8px; }
.delete-chapter:hover { background: #fff1ed; }
.chapter-intro { grid-column: 1 / -1; }
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
