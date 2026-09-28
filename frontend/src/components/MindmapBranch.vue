<script setup lang="ts">
import type { MindmapNode } from '../types/resources'
defineProps<{ node: MindmapNode }>()
</script>
<template><li><span class="resource-text">{{ node.label }}</span><ul v-if="node.children?.length"><MindmapBranch v-for="(child, index) in node.children" :key="index" :node="child" /></ul></li></template>
