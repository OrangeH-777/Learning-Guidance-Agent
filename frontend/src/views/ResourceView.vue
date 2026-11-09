<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import MindmapBranch from '../components/MindmapBranch.vue'
import GenerationProcessDetails from '../components/GenerationProcessDetails.vue'
import TextContent from '../components/TextContent.vue'
import { api, errorMessage } from '../api/session'
import type { LearningResource, Source } from '../types/resources'
import { markdownFilename, resourceMarkdown } from '../composables/resourceMarkdown'
const transferStatus = ref('')
const route = useRoute(), resource = ref<LearningResource | null>(null), sources = ref<Source[]>([]), error = ref(''), sourceError = ref(''), loading = ref(false)
const markdown = computed(() => resource.value ? resourceMarkdown(resource.value, sources.value) : '')
async function copyResource() {
  const id = route.params.id
  try {
    await navigator.clipboard.writeText(markdown.value)
    if (route.params.id === id) transferStatus.value = '已复制 Markdown 全文。'
  } catch {
    if (route.params.id === id) transferStatus.value = '浏览器未允许复制，可以下载 Markdown 文件。'
  }
}
function exportResource() {
  if (!resource.value) return
  const url = URL.createObjectURL(new Blob([markdown.value], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = markdownFilename(resource.value.content.title)
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  transferStatus.value = '已发起 Markdown 文件下载。'
}
const historyLocation = computed(() => {
  const value = route.query.returnTo
  return typeof value === 'string' && (value === '/history' || value.startsWith('/history?')) ? value : '/history'
})
watch(() => route.params.id, async (id, _previous, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  transferStatus.value = ''; loading.value = true; error.value = ''; sourceError.value = ''; resource.value = null; sources.value = []
  try {
    const result: LearningResource = (await api.get(`/resources/${id}`, { signal: controller.signal })).data
    if (controller.signal.aborted) return
    resource.value = result
    const settled = await Promise.allSettled(result.content.source_ids.map(source => api.get(`/courses/${result.course_id}/sources/${source}`, { signal: controller.signal })))
    if (controller.signal.aborted) return
    for (const item of settled) {
      if (item.status === 'fulfilled') sources.value.push(item.value.data)
      else sourceError.value = '部分来源读取失败或已不可用，请勿将缺失来源视为有效依据。'
    }
  } catch (e) { if (!controller.signal.aborted) error.value = errorMessage(e) } finally { if (!controller.signal.aborted) loading.value = false }
}, { immediate: true })
</script>
<template><AppShell>
  <RouterLink :to="historyLocation">← 返回学习历史</RouterLink><p v-if="loading" class="loading" role="status">正在读取资源…</p><p v-if="error" class="error" role="alert">{{ error }}</p>
  <article v-if="resource" class="panel resource-body">
    <p class="eyebrow">{{ { lecture: '概念讲解', exercise: '巩固练习', mindmap: '文本思维导图' }[resource.content.resource_type] }}</p><h1><TextContent :text="resource.content.title" inline /></h1>
    <div class="resource-tools"><button type="button" :disabled="loading" @click="copyResource">复制全文</button><button type="button" class="secondary" :disabled="loading" @click="exportResource">导出 Markdown</button><span class="muted" role="status">{{ transferStatus }}</span></div>
    <p class="notice">{{ resource.notice }} · 自动核验已通过 · {{ resource.human_pass ? '已获人工复核' : '尚未人工复核' }}</p>
    <p class="muted">{{ resource.course_id }} · {{ resource.topic }} · 画像 v{{ resource.metadata.profile.version }} · {{ new Date(resource.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}（北京时间）</p>
    <GenerationProcessDetails :process="resource.process" :kind="resource.content.resource_type" />
    <details><summary>生成时的配置</summary><p>模型：{{ resource.metadata.model.model_id }} / {{ resource.metadata.model.protocol }}</p><p>知识版本：{{ resource.metadata.knowledge_version }}</p><p>提示词版本：{{ resource.metadata.prompt_version }}</p></details>
    <template v-if="resource.content.resource_type === 'lecture'">
      <h2>学习目标</h2><ul><li v-for="(text, i) in resource.content.learning_objectives" :key="i"><TextContent :text="text" inline /></li></ul><h2>先修知识</h2><ul><li v-for="(text, i) in resource.content.prerequisites" :key="i"><TextContent :text="text" inline /></li></ul>
      <section v-for="(section, i) in resource.content.sections" :key="i"><h2><TextContent :text="section.heading" inline /></h2><TextContent :text="section.explanation" /></section><h2>示例</h2><section v-for="(example, i) in resource.content.examples" :key="i"><h3><TextContent :text="example.title" inline /></h3><TextContent :text="example.content" /></section><h2>小结</h2><TextContent :text="resource.content.summary" />
    </template>
    <template v-else-if="resource.content.resource_type === 'exercise'"><section v-for="question in resource.content.questions" :key="question.question_id"><h2>{{ question.question_id }}</h2><TextContent :text="question.prompt" /><ul v-if="question.options"><li v-for="option in question.options" :key="option.label">{{ option.label }}. <TextContent :text="option.content" inline /></li></ul><details><summary>查看答案与解析</summary><h3>答案</h3><TextContent :text="question.answer" /><h3>解析</h3><TextContent :text="question.analysis" /></details></section></template>
    <template v-else><h2>知识结构</h2><ul><MindmapBranch :node="resource.content.root" /></ul></template>
    <h2>来源与依据</h2><p v-if="sourceError" role="alert" class="error">{{ sourceError }}</p><details v-for="source in sources" :key="source.id"><summary>{{ source.title }} · {{ source.locator }}</summary><TextContent :text="source.content" /><p class="muted">来源：{{ source.source }}</p><small>{{ source.license }}</small></details>
  </article>
</AppShell></template>
