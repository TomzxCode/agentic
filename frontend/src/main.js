import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ProblemsView from './views/ProblemsView.vue'
import ProblemView from './views/ProblemView.vue'
import SettingsView from './views/SettingsView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'problems', component: ProblemsView },
    { path: '/p/:id', name: 'problem', component: ProblemView, props: true },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

createApp(App).use(router).mount('#app')
