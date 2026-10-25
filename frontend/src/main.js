import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import TasksView from './views/TasksView.vue'
import TaskView from './views/TaskView.vue'
import IssueView from './views/IssueView.vue'
import PullRequestView from './views/PullRequestView.vue'
import ItemsView from './views/ItemsView.vue'
import ItemDetailView from './views/ItemDetailView.vue'
import PeopleView from './views/PeopleView.vue'
import PersonView from './views/PersonView.vue'
import PersonCreateView from './views/PersonCreateView.vue'
import RepositoriesView from './views/RepositoriesView.vue'
import RepositoryDetailView from './views/RepositoryDetailView.vue'
import GanttView from './views/GanttView.vue'
import DependencyGraphView from './views/DependencyGraphView.vue'
import EventsView from './views/EventsView.vue'
import MetricsView from './views/MetricsView.vue'
import ProcessView from './views/ProcessView.vue'
import InboxView from './views/InboxView.vue'
import ReviewsView from './views/ReviewsView.vue'
import FeedbackView from './views/FeedbackView.vue'
import MyPullsView from './views/MyPullsView.vue'
import DecisionsView from './views/DecisionsView.vue'
import SchedulesView from './views/SchedulesView.vue'
import ExecutionGraphsView from './views/ExecutionGraphsView.vue'
import OnCallView from './views/OnCallView.vue'
import StackView from './views/StackView.vue'
import SettingsView from './views/SettingsView.vue'
import './styles/base.css'
import './styles/layout.css'
import './styles/controls.css'
import './styles/chips.css'
import './styles/items.css'
import './styles/reviews.css'
import './styles/feedback.css'
import './styles/myPulls.css'
import './styles/decisions.css'
import './styles/tasks.css'
import './styles/overlays.css'
import './styles/charts.css'
import './styles/process.css'
import './styles/events.css'
import './styles/responsive.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'tasks', component: TasksView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    { path: '/reviews', name: 'reviews', component: ReviewsView },
    { path: '/my-pulls', name: 'my-pulls', component: MyPullsView },
    { path: '/feedback', name: 'feedback', component: FeedbackView },
    { path: '/decisions', name: 'decisions', component: DecisionsView },
    { path: '/stack', name: 'stack', component: StackView },
    { path: '/task/:id', name: 'task', component: TaskView, props: true },
    { path: '/issue/:owner/:repo/:number', name: 'issue', component: IssueView, props: true },
    { path: '/pr/:owner/:repo/:number', name: 'pr', component: PullRequestView, props: true },
    { path: '/gantt', name: 'gantt', component: GanttView },
    { path: '/graph', name: 'graph', component: DependencyGraphView },
    { path: '/events', name: 'events', component: EventsView },
    { path: '/metrics', name: 'metrics', component: MetricsView },
    { path: '/process', name: 'process', component: ProcessView },
    { path: '/schedules', name: 'schedules', component: SchedulesView },
    { path: '/graphs', name: 'graphs', component: ExecutionGraphsView },
    { path: '/on-call', name: 'on-call', component: OnCallView },
    { path: '/oncall', name: 'oncall', component: OnCallView },
    { path: '/items', name: 'items', component: ItemsView },
    { path: '/items/:id', name: 'item', component: ItemDetailView, props: true },
    { path: '/people', name: 'people', component: PeopleView },
    { path: '/person/new', name: 'person-new', component: PersonCreateView },
    { path: '/person/:id', name: 'person', component: PersonView, props: true },
    { path: '/repositories', name: 'repositories', component: RepositoriesView },
    { path: '/repositories/:id', name: 'repository', component: RepositoryDetailView, props: true },
    { path: '/settings', name: 'settings', component: SettingsView }
  ]
})

createApp(App).use(router).mount('#app')
