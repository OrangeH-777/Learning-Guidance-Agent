<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '../types/business'

const props = defineProps<{ task: Task | null; submitting: boolean; connection: string; course: string }>()
defineEmits<{ retry: [task: Task] }>()
const stages = [
  { status: 'queued', title: '等待处理', detail: '任务已提交，等待执行。' },
  { status: 'planning', title: '规划学习内容', detail: '结合教材章节和你的画像，拟定目标与大纲。' },
  { status: 'generating', title: '生成学习资源', detail: '模型正在按大纲编写所选类型的学习材料。' },
  { status: 'validating', title: '核验内容', detail: '检查教材依据、内容结构与事实一致性。' },
  { status: 'formatting', title: '整理与保存', detail: '程序正在整理格式，保存后将打开结果。' },
]
const active = computed(() => props.task?.status === 'completed' ? stages.length : stages.findIndex(s => s.status === props.task?.status))
const status = computed(() => props.submitting ? '正在提交…' : props.task?.status === 'failed' ? '任务未完成'
  : props.task?.status === 'completed' ? '生成完成' : stages[active.value]?.title ?? '等待开始')
</script>
<template>
  <section class="panel progress-panel" aria-labelledby="progress-heading">
    <header><h2 id="progress-heading">生成过程</h2><span class="badge" :data-status="task?.status" role="status">{{ status }}</span></header>
    <p v-if="task" class="task-context"><small>{{ course }}</small><strong>{{ task.topic }}</strong></p>
    <p v-else class="muted">提交学习需求后，可在这里查看本次任务的进度。</p>
    <ol v-if="task?.status !== 'failed'" class="stages">
      <li v-for="(stage, index) in stages" :key="stage.status" :class="{ done: index < active, current: index === active }" :aria-current="index === active ? 'step' : undefined">
        <span class="marker" aria-hidden="true">{{ index < active ? '✓' : '' }}</span>
        <div>{{ stage.title }}<p v-if="index === active" class="stage-detail">{{ stage.detail }}</p></div>
      </li>
    </ol>
    <p v-if="task?.content_regenerations" class="muted">已根据核验结果重新生成 {{ task.content_regenerations }} 次。</p>
    <template v-if="task?.status === 'failed'">
      <p class="error" role="alert">{{ task.error_code === 'TASK_TIMEOUT' ? '生成超时。可以缩小学习需求后重新提交，或沿用原配置重试。' : '本次任务未能完成。' }} <small>{{ task.error_code }}</small></p>
      <button class="secondary" :disabled="submitting" @click="$emit('retry', task)">沿用原配置重试</button>
    </template>
    <RouterLink v-if="task?.resource_id" :to="`/resources/${task.resource_id}`">查看资源</RouterLink>
    <p v-if="connection" class="notice" role="status">{{ connection }}</p>
  </section>
</template>
<style scoped>
.progress-panel { border-top: 3px solid var(--pine); }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
h2, .stage-detail { margin: 0; }
.task-context { display: grid; gap: 2px; }
.task-context small { color: #64766e; }
.stages { list-style: none; padding: 0; margin: 16px 0 0; }
.stages li { display: grid; grid-template-columns: 18px 1fr; gap: 12px; position: relative; padding-bottom: 14px; color: #62746b; }
.stages li:last-child { padding-bottom: 0; }
.stages li:not(:last-child)::before { content: ''; position: absolute; left: 8px; top: 18px; bottom: -5px; width: 2px; background: var(--rule); }
.marker { z-index: 1; margin-top: 5px; width: 17px; height: 17px; border: 2px solid #c9d3ca; border-radius: 50%; background: white; display: grid; place-items: center; font: bold 11px/1 sans-serif; }
.current { font-weight: 650; }
.current .marker { border-color: #286752; box-shadow: inset 0 0 0 3px white; background: #286752; }
.done .marker { background: #286752; color: white; border-color: #286752; }
.stage-detail { font-size: .86rem; font-weight: 400; }
.notice { margin: 16px 0 0; }
</style>
