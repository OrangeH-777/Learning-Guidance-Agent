<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string }>()
const pieces = computed(() => props.text.split(/```[^\n]*\n([\s\S]*?)```/g).map((text, index) => ({ text, code: index % 2 === 1 })))
</script>
<template><template v-for="(piece, index) in pieces" :key="index"><pre v-if="piece.code" class="code-block"><code>{{ piece.text }}</code></pre><p v-else-if="piece.text" class="resource-text">{{ piece.text }}</p></template></template>
