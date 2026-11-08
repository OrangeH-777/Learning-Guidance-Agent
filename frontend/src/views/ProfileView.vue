<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import TextContent from '../components/TextContent.vue'
import AppShell from '../components/AppShell.vue'
import { api, errorMessage } from '../api/session'
import type { Course, Profile, ProfileFields } from '../types/business'
const courses = ref<Course[]>([]), courseId = ref(''), version = ref(0), busy = ref(true), message = ref(''), error = ref('')
const form = reactive<ProfileFields>({ knowledge_base: '', learning_goal: '', preference: '' })
const statement = ref(''), draftRevision = ref(0), messages = ref<{ role: string; content: string }[]>([])
const draftFields = ref<Partial<ProfileFields>>({})
function applyDraft() {
  Object.assign(form, { knowledge_base: '', learning_goal: '', preference: '' }, draftFields.value)
  message.value = '已恢复对话草稿，请检查后确认保存。'
}
async function load() {
  message.value = ''; error.value = ''; busy.value = true
  try {
    const [confirmed, draft] = await Promise.all([api.get(`/courses/${courseId.value}/profile`), api.get(`/courses/${courseId.value}/profile/draft`)])
    const data: Profile = confirmed.data
    version.value = data.version; Object.assign(form, data.fields ?? { knowledge_base: '', learning_goal: '', preference: '' })
    draftRevision.value = draft.data.revision; draftFields.value = draft.data.fields; messages.value = draft.data.messages; statement.value = ''
  }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function converse() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    const data = (await api.post(`/courses/${courseId.value}/profile/conversation`, { content: statement.value, expected_revision: draftRevision.value })).data
    draftRevision.value = data.revision; draftFields.value = data.fields; messages.value = data.messages; applyDraft(); statement.value = ''
    message.value = '草稿已整理，请检查字段后确认保存。'
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function save() {
  busy.value = true; error.value = ''; message.value = ''
  try { const data: Profile = (await api.put(`/courses/${courseId.value}/profile`, { ...form, expected_version: version.value })).data; version.value = data.version; message.value = `画像已确认，版本 ${data.version}。` }
  catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
onMounted(async () => { try { courses.value = (await api.get('/courses')).data; courseId.value = courses.value.find(c => c.enabled)?.id ?? ''; if (courseId.value) await load() } catch (e) { error.value = errorMessage(e) } finally { busy.value = false } })
</script>
<template><AppShell>
  <div class="page-heading"><h1>学习画像</h1><p class="muted">每门课程独立保存画像。只有点击确认后，新画像才会用于后续任务。</p></div>
  <form class="panel profile-form" @submit.prevent="save">
    <fieldset :disabled="busy">
    <label>当前课程<select v-model="courseId" :disabled="busy" @change="load"><option v-for="c in courses" :key="c.id" :value="c.id" :disabled="!c.enabled">{{ c.name }}</option></select></label>
    <p v-if="!courseId" class="notice">暂无可用课程，请先导入课程目录。</p>
    <p v-if="draftRevision > 0" class="notice">本课程有已保存的对话草稿（第 {{ draftRevision }} 版）。<button type="button" class="secondary" @click="applyDraft">恢复对话草稿到表单</button></p>
    <details><summary>通过对话整理画像（使用已配置的模型）</summary><p class="muted">也可以直接填写下方字段。对话仅形成草稿，不会自动确认画像。</p><div class="conversation-turn" v-for="(turn, i) in messages" :key="i"><strong>{{ turn.role === 'user' ? '你' : '学习助手' }}</strong><TextContent :text="turn.content" /></div><label>描述你的学习情况<textarea v-model="statement" v-codepoints="1000" rows="3" placeholder="我已经学过…，希望…，更喜欢…"></textarea></label><button type="button" class="secondary" :disabled="busy || !courseId || !statement.trim()" @click="converse">发送并整理</button></details>
    <div class="field-pair"><label>知识基础<textarea v-model="form.knowledge_base" required v-codepoints="500" rows="3" placeholder="已经掌握什么？还有哪些难点？"></textarea></label>
    <label>学习目标<textarea v-model="form.learning_goal" required v-codepoints="500" rows="3" placeholder="希望理解的概念、解决的问题或备考目标"></textarea></label>
    </div><label>学习偏好<textarea v-model="form.preference" required v-codepoints="500" rows="3" placeholder="喜欢具体示例、逐步推导或练习巩固？"></textarea></label>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="message" role="status" class="success">{{ message }}</p>
    <div class="actions"><button :disabled="busy || !courseId">确认并保存画像</button><button type="button" class="secondary" :disabled="busy || !courseId" @click="load">取消修改</button><span class="muted">当前版本 {{ version }}</span></div>
    </fieldset>
  </form>
</AppShell></template>
