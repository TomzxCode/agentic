import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TasksView from './views/TasksView.vue'
import TaskView from './views/TaskView.vue'
import ItemsView from './views/ItemsView.vue'
import GanttView from './views/GanttView.vue'
import MetricsView from './views/MetricsView.vue'
import SettingsView from './views/SettingsView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'tasks', component: TasksView },
    { path: '/task/:id', name: 'task', component: TaskView, props: true },
    { path: '/gantt', name: 'gantt', component: GanttView },
    { path: '/metrics', name: 'metrics', component: MetricsView },
    { path: '/items', name: 'items', component: ItemsView },
    { path: '/settings', name: 'settings', component: SettingsView }
  ]
})

createApp(App).use(router).mount('#app')
