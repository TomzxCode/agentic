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
import TimeView from './views/TimeView.vue'
import SettingsView from './views/SettingsView.vue'
import { installPageTiming } from './pageTiming'
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
import './styles/time.css'
import './styles/responsive.css'

// Every route names its page, so the tab title and the Time page's visits read
// "Task" or "Review queue" rather than a route name.
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'tasks', component: TasksView, meta: { title: 'Tasks' } },
    { path: '/inbox', name: 'inbox', component: InboxView, meta: { title: 'Inbox' } },
    { path: '/reviews', name: 'reviews', component: ReviewsView, meta: { title: 'Review queue' } },
    { path: '/my-pulls', name: 'my-pulls', component: MyPullsView, meta: { title: 'My PRs' } },
    { path: '/feedback', name: 'feedback', component: FeedbackView, meta: { title: 'PR feedback' } },
    { path: '/decisions', name: 'decisions', component: DecisionsView, meta: { title: 'Decisions' } },
    { path: '/stack', name: 'stack', component: StackView, meta: { title: 'Stack' } },
    { path: '/task/:id', name: 'task', component: TaskView, props: true, meta: { title: 'Task' } },
    {
      path: '/issue/:owner/:repo/:number',
      name: 'issue',
      component: IssueView,
      props: true,
      meta: { title: 'Issue' }
    },
    {
      path: '/pr/:owner/:repo/:number',
      name: 'pr',
      component: PullRequestView,
      props: true,
      meta: { title: 'Pull request' }
    },
    { path: '/gantt', name: 'gantt', component: GanttView, meta: { title: 'Gantt' } },
    { path: '/graph', name: 'graph', component: DependencyGraphView, meta: { title: 'Graph' } },
    { path: '/events', name: 'events', component: EventsView, meta: { title: 'Events' } },
    { path: '/metrics', name: 'metrics', component: MetricsView, meta: { title: 'Metrics' } },
    { path: '/process', name: 'process', component: ProcessView, meta: { title: 'Process' } },
    { path: '/schedules', name: 'schedules', component: SchedulesView, meta: { title: 'Scheduled tasks' } },
    { path: '/graphs', name: 'graphs', component: ExecutionGraphsView, meta: { title: 'Execution graphs' } },
    { path: '/on-call', name: 'on-call', component: OnCallView, meta: { title: 'On call' } },
    { path: '/oncall', name: 'oncall', component: OnCallView, meta: { title: 'On call' } },
    { path: '/items', name: 'items', component: ItemsView, meta: { title: 'Items' } },
    { path: '/items/:id', name: 'item', component: ItemDetailView, props: true, meta: { title: 'Item' } },
    { path: '/people', name: 'people', component: PeopleView, meta: { title: 'People' } },
    { path: '/person/new', name: 'person-new', component: PersonCreateView, meta: { title: 'New person' } },
    { path: '/person/:id', name: 'person', component: PersonView, props: true, meta: { title: 'Person' } },
    { path: '/repositories', name: 'repositories', component: RepositoriesView, meta: { title: 'Repositories' } },
    {
      path: '/repositories/:id',
      name: 'repository',
      component: RepositoryDetailView,
      props: true,
      meta: { title: 'Repository' }
    },
    { path: '/time', name: 'time', component: TimeView, meta: { title: 'Time' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { title: 'Settings' } }
  ]
})

// Record where the app's time goes; the Time page reads it back.
installPageTiming(router)

createApp(App).use(router).mount('#app')
