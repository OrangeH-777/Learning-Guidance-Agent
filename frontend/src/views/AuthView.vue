<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, applySession, errorMessage } from '../api/session'
const router = useRouter()
const register = ref(false), busy = ref(false), error = ref('')
const username = ref(''), password = ref(''), confirmation = ref('')
async function submit() {
  error.value = ''; busy.value = true
  try {
    const payload = register.value ? { username: username.value, password: password.value, password_confirmation: confirmation.value } : { username: username.value, password: password.value }
    applySession((await api.post(`/auth/${register.value ? 'register' : 'login'}`, payload)).data)
    password.value = ''; confirmation.value = ''; await router.replace('/')
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
</script>
<template>
  <main class="auth-layout">
    <section class="auth-intro"><p class="eyebrow">LEARNING GUIDANCE</p><h1>从你的基础出发，<br>找到适合的学习方式。</h1><p>选择课程，确认画像，把可信的知识资料整理成讲解、练习与思维导图。</p><div class="tags"><span>课程知识</span><span>个性化资源</span><span>可追溯来源</span></div></section>
    <form class="panel auth-form" @submit.prevent="submit">
      <h2>{{ register ? '创建账号' : '欢迎回来' }}</h2><p class="muted">{{ register ? '建立你的个人学习空间' : '登录后继续你的学习进度' }}</p>
      <label>账号<input v-model="username" autocomplete="username" required pattern="[A-Za-z0-9_]{4,20}" minlength="4" v-codepoints="20" placeholder="4—20位字母、数字或下划线"></label>
      <label>密码<input v-model="password" type="password" :autocomplete="register ? 'new-password' : 'current-password'" required minlength="8" v-codepoints="64" placeholder="8—64个字符，包含字母和数字"></label>
      <label v-if="register">确认密码<input v-model="confirmation" type="password" autocomplete="new-password" required v-codepoints="64"></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p><button :disabled="busy">{{ busy ? '请稍候…' : register ? '注册并进入' : '登录' }}</button>
      <button type="button" class="text-button" :disabled="busy" @click="register = !register; error = ''">{{ register ? '已有账号？去登录' : '还没有账号？创建账号' }}</button>
    </form>
  </main>
</template>
