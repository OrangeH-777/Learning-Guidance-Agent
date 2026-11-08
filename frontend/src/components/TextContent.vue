<script lang="ts">
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, breaks: true }).disable('image')
markdown.validateLink = url => /^https?:\/\//i.test(url)
</script>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string; inline?: boolean }>()
const rendered = computed(() => props.inline ? markdown.renderInline(props.text) : markdown.render(props.text))
</script>

<template>
  <component :is="inline ? 'span' : 'div'" class="markdown" v-html="rendered" />
</template>
