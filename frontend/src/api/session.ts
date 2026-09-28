import { reactive } from 'vue'
import axios from 'axios'
import type { User } from '../types/business'

export const session = reactive<{ user: User | null; csrf: string; checked: boolean }>({ user: null, csrf: '', checked: false })
export const api = axios.create({ baseURL: '/api', timeout: 65000 })
api.interceptors.request.use(config => {
  if (session.csrf && config.method !== 'get') config.headers.set('X-CSRF-Token', session.csrf)
  return config
})
api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) {
    session.user = null
    session.csrf = ''
  }
  return Promise.reject(error)
})
export function applySession(data: { user: User; csrf_token: string }) {
  session.user = data.user; session.csrf = data.csrf_token; session.checked = true
}
export async function restoreSession() {
  try { applySession((await api.get('/auth/session')).data) }
  catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) { session.user = null; session.checked = true }
    else { throw error }
  }
}
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) return error.response?.data?.error?.message ?? '连接失败，请检查网络后重试。'
  return '操作未完成，请稍后重试。'
}
