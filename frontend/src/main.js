import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TasksView from './views/TasksView.vue'
import TaskView from './views/TaskView.vue'
import ItemsView from './views/ItemsView.vue'
import PeopleView from './views/PeopleView.vue'
import PersonView from './views/PersonView.vue'
import RepositoriesView from './views/RepositoriesView.vue'
import RepositoryDetailView from './views/RepositoryDetailView.vue'
import GanttView from './views/GanttView.vue'
import MetricsView from './views/MetricsView.vue'
import StackView from './views/StackView.vue'
import SettingsView from './views/SettingsView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'tasks', component: TasksView },
    { path: '/stack', name: 'stack', component: StackView },
    { path: '/task/:id', name: 'task', component: TaskView, props: true },
    { path: '/gantt', name: 'gantt', component: GanttView },
    { path: '/metrics', name: 'metrics', component: MetricsView },
    { path: '/items', name: 'items', component: ItemsView },
    { path: '/people', name: 'people', component: PeopleView },
    { path: '/person/:id', name: 'person', component: PersonView, props: true },
    { path: '/repositories', name: 'repositories', component: RepositoriesView },
    { path: '/repositories/:id', name: 'repository', component: RepositoryDetailView, props: true },
    { path: '/settings', name: 'settings', component: SettingsView }
  ]
})

createApp(App).use(router).mount('#app')
