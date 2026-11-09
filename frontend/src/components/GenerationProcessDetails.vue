<script setup lang="ts">
import type { Content, GenerationProcess } from '../types/resources'
import TextContent from './TextContent.vue'

defineProps<{ process?: GenerationProcess; kind: Content['resource_type'] }>()
const kinds = { lecture: '概念讲解', exercise: '巩固练习', mindmap: '文本思维导图' }
const checks: Record<string, string> = {
  structure: '内容结构', sources: '引用归属', relevant: '主题相关性',
  supported: '教材是否支持结论', facts_correct: '事实准确性',
  answers_consistent: '内容与答案一致性', safe: '内容安全',
}
</script>

<template>
  <details class="generation-process">
    <summary>生成过程</summary>
    <ol v-if="process" class="handoffs">
      <li>
        <strong>内容规划 · 模型</strong>
        <p>选用章节：{{ process.chapter || '该任务未记录章节标题' }}</p>
        <template v-if="process.planning">
          <h3>交给生成阶段的学习目标</h3>
          <ul><li v-for="(goal, i) in process.planning.objectives" :key="i"><TextContent :text="goal" inline /></li></ul>
          <h3>内容大纲</h3>
          <ol><li v-for="(item, i) in process.planning.outline" :key="i"><TextContent :text="item" inline /></li></ol>
        </template>
        <p v-else class="muted">此历史任务未保存规划目标和大纲。</p>
      </li>
      <li><strong>资源生成 · 模型</strong><p>交给核验阶段的资源：{{ kinds[kind] }}。</p>
        <p>{{ process.regenerations ? '根据核验反馈重新生成了 ' + process.regenerations + ' 次。' : '本次任务未发生内容重生成。' }}</p>
      </li>
      <li><strong>内容核验 · 程序检查与模型语义核验</strong>
        <p v-if="process.passed_checks.length">最终通过的自动检查</p>
        <ul v-if="process.passed_checks.length" class="check-list"><li v-for="key in process.passed_checks" :key="key">{{ checks[key] || key }}</li></ul>
        <p v-else class="muted">此任务未保存逐项核验记录。</p>
      </li>
      <li><strong>格式整理 · 程序</strong>
        <p>{{ process.format_unchanged ? '已核对整理前后的结构化正文一致，结果已保存。' : '已保存资源；此任务未记录格式一致性比对结果。' }}</p>
      </li>
    </ol>
    <p v-else class="muted">此资源暂无生成过程记录。</p>
  </details>
</template>

<style scoped>
.handoffs { padding-inline-start: 1.8rem; margin: 1rem 0 .25rem; }
.handoffs > li { padding: 0 0 .85rem .35rem; }
.handoffs > li + li { padding-top: .85rem; border-top: 1px solid var(--rule); }
.handoffs > li::marker { color: var(--pine); font-weight: 700; }
.handoffs p, .handoffs h3 { margin: .45rem 0; }
.handoffs h3 { font-size: 1rem; }
.check-list { list-style: none; display: flex; flex-wrap: wrap; gap: .4rem; padding: 0; }
.check-list > li { background: #edf4ee; color: #315847; border-radius: .45rem; padding: .2rem .65rem; }
</style>
