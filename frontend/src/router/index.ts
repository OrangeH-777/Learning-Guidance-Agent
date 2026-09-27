import { createRouter, createWebHistory } from 'vue-router'
import ScaffoldView from '../views/ScaffoldView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', name: 'scaffold', component: ScaffoldView }],
})
