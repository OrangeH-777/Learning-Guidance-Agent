import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles/main.css'
import { codepoints } from './codepoints'

createApp(App).directive('codepoints', codepoints).use(router).mount('#app')
