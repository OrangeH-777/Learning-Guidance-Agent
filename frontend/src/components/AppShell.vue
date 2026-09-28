<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage, session } from '../api/session'
const router = useRouter()
const error = ref(''), busy = ref(false)
watch(() => session.user, user => { if (!user) void router.replace('/login') })
async function logout() {
  busy.value = true; error.value = ''
  try { await api.post('/auth/logout'); session.user = null; session.csrf = ''; await router.replace('/login') }
  catch (e) { error.value = `${errorMessage(e)} 服务端退出尚未确认。` }
  finally { busy.value = false }
}
</script>
<template>
  <div class="app-layout">
    <header class="app-header">
      <RouterLink class="brand" to="/">知学 <small>学习资源工作台</small></RouterLink>
      <nav aria-label="主导航"><RouterLink to="/">工作台</RouterLink><RouterLink to="/profile">学习画像</RouterLink><RouterLink to="/models">模型设置</RouterLink><RouterLink to="/history">学习历史</RouterLink><RouterLink v-if="session.user?.is_admin" to="/admin/materials">公共教材管理</RouterLink></nav>
      <div class="account"><span>{{ session.user?.username }}</span><button class="secondary" :disabled="busy" @click="logout">退出</button></div>
    </header>
    <p v-if="error" class="error container" role="alert">{{ error }}</p>
    <main class="container"><slot /></main>
    <footer class="container muted">基于个人学习画像与课程资料生成 · AI 内容请结合教材核对</footer>
  </div>
</template>
