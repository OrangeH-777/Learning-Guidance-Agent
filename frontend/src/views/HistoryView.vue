<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage } from '../api/session'
import type { Course, HistoryItem } from '../types/business'
const route = useRoute(), router = useRouter()
const queryText = (name: string) => typeof route.query[name] === 'string' ? route.query[name] as string : ''
const initialPage = Number(queryText('page'))
const resourceLabels: Record<string, string> = { lecture: '讲解', exercise: '练习', mindmap: '文本导图' }
const items = ref<HistoryItem[]>([]), courses = ref<Course[]>([]), course = ref(queryText('course_id')), topic = ref(queryText('topic')), type = ref(['lecture', 'exercise', 'mindmap'].includes(queryText('resource_type')) ? queryText('resource_type') : ''), page = ref(Number.isSafeInteger(initialPage) && initialPage > 0 ? initialPage : 1), total = ref(0), error = ref(''), loading = ref(false)
async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true; error.value = ''
  try { await router.replace({ path: '/history', query: { course_id: course.value || undefined, topic: topic.value || undefined, resource_type: type.value || undefined, page: page.value > 1 ? String(page.value) : undefined } }); const data = (await api.get('/resources', { params: { course_id: course.value || undefined, topic: topic.value, resource_type: type.value || undefined, page: page.value, page_size: 10 } })).data; items.value = data.items; total.value = data.total }
  catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
}
onMounted(async () => { try { courses.value = (await api.get('/courses')).data } catch (e) { error.value = errorMessage(e) }; await load() })
</script>
<template><AppShell><div class="page-heading"><h1>你的学习历史</h1><p class="muted">这里只展示已通过自动核验并成功保存的资源。生成时的画像与来源版本会一直保留。</p></div>
  <form class="panel filters" @submit.prevent="load(true)"><label>课程<select v-model="course"><option value="">全部课程</option><option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option></select></label><label>主题<input v-model="topic" v-codepoints="100" placeholder="按主题筛选"></label><label>类型<select v-model="type"><option value="">全部类型</option><option value="lecture">讲解</option><option value="exercise">练习</option><option value="mindmap">文本导图</option></select></label><div><button :disabled="loading">筛选</button></div></form>
  <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="loading" class="loading" role="status">正在读取历史…</p>
  <p v-else-if="!items.length && !error" class="panel empty">{{ course || topic || type ? '没有符合筛选条件的资源。' : '还没有保存的资源，完成一次生成后会出现在这里。' }}</p>
  <div class="history-grid"><RouterLink v-for="item in items" :key="item.id" :to="{ path: `/resources/${item.id}`, query: { returnTo: route.fullPath } }" class="panel"><span class="badge">{{ resourceLabels[item.resource_type] ?? item.resource_type }}</span><h2>{{ item.title }}</h2><p>{{ item.topic }}</p><p class="muted">{{ courses.find(c => c.id === item.course_id)?.name ?? item.course_id }} · {{ new Date(item.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</p><span class="history-open">阅读资源 →</span></RouterLink></div>
  <div v-if="total" class="actions pagination"><button class="secondary" :disabled="loading || page <= 1" @click="page--; load()">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 条</span><button class="secondary" :disabled="loading || page * 10 >= total" @click="page++; load()">下一页</button></div>
</AppShell></template>
