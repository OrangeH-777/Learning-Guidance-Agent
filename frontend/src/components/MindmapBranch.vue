<script setup lang="ts">
import TextContent from './TextContent.vue'
import type { MindmapNode } from '../types/resources'
defineProps<{ node: MindmapNode }>()
</script>
<template><li><TextContent :text="node.label" inline /><ul v-if="node.children?.length"><MindmapBranch v-for="(child, index) in node.children" :key="index" :node="child" /></ul></li></template>
