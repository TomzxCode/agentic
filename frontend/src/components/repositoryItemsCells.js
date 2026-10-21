/* eslint-disable vue/one-component-per-file -- AG Grid resolves its cell renderers by name from one module. */
import { defineComponent, h } from 'vue'
import { statusLabel, timeAgo } from '../store'
import { changeStatusBadge } from '../changes'
import StatusIcon from './StatusIcon.vue'

// The cell renderers for the repository issues and PRs grid. AG Grid renders
// each cell with one of these and passes its `params` prop; the grid hands the
// shared router-link and the row actions through `params.context`, so these
// components stay presentation-only.
//
// AG Grid resolves them by name (the grid's `components` option), which is why
// they live in one module rather than as single-file components.

const params = { type: Object, required: true }

// A type badge ("issue" / "PR"), matching the badges used elsewhere.
export const KindCell = defineComponent({
  props: { params },
  setup: (props) => () => h('span', { class: 'badge' }, props.params.data.kind === 'pr' ? 'PR' : 'issue')
})

// The GitHub state badge (open / draft / merged / closed), omitted when no
// state is stored.
export const StateCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    if (!row.stateLabel) return null
    return h('span', { class: ['badge', row.stateClass] }, row.stateLabel)
  }
})

// The title, linking to the item on GitHub, with the ghx link after it when a
// local ghx server is configured, and the last-fetched time below it.
export const TitleCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    const label = row.title || row.url || '(untitled)'
    const title = row.url
      ? h('a', { class: 'title', href: row.url, target: '_blank', rel: 'noopener' }, label)
      : h('span', { class: 'title' }, label)
    const heading = row.ghxUrl
      ? h('div', { class: 'repo-name-cell' }, [
          title,
          h(
            'a',
            { class: 'btn sm ghost', href: row.ghxUrl, target: '_blank', rel: 'noopener', title: 'Open in ghx' },
            'ghx'
          )
        ])
      : title
    const children = [heading]
    if (row.fetched) children.push(h('div', { class: 'faint' }, row.fetched))
    return h('div', { class: 'repo-title-cell' }, children)
  }
})

// The author login, linked to the person carrying it as an alias when one does,
// or to the prefilled person-creation page (grey) when nobody does yet.
export const AuthorCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    if (!row.authorLabel) return null
    if (!row.authorPath) return h('span', { class: 'faint' }, row.authorLabel)
    return h(
      props.params.context.RouterLink,
      { to: row.authorPath, class: row.personId ? undefined : 'faint' },
      () => row.authorLabel
    )
  }
})

// The tasks each row is associated with, as the same chips the rest of the app
// uses.
export const TasksCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    if (!row.tasks.length) return null
    return h(
      'div',
      { class: 'repo-chips' },
      row.tasks.map((task) =>
        h(props.params.context.RouterLink, { key: task.id, to: `/task/${task.id}`, class: 'btn sm ghost' }, () => [
          h(StatusIcon, { status: task.status, label: statusLabel(task.status) }),
          ` ${task.title}`
        ])
      )
    )
  }
})

// The change records that reference a PR row.
export const ChangesCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    if (!row.changes.length) return null
    return h(
      'div',
      { class: 'change-lines' },
      row.changes.map((change) =>
        h('div', { key: change.id, class: 'change-line' }, [
          h('span', { class: changeStatusBadge(change.status) }, change.status),
          h(props.params.context.RouterLink, { to: `/task/${change.task_id}` }, () => change.title || change.id),
          h('span', { class: 'faint' }, change.change_class || ''),
          h('span', { class: 'faint' }, `· ${timeAgo(change.opened_at)}`)
        ])
      )
    )
  }
})

// The distinct statuses of the row's linked tasks, each as a status badge.
export const TaskStatusCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const statuses = props.params.data.statuses
    if (!statuses.length) return null
    return h(
      'span',
      { class: 'repo-statuses' },
      statuses.map((entry) =>
        h('span', { key: entry.status, class: 'badge' }, [
          h(StatusIcon, { status: entry.status, label: entry.label }),
          ` ${entry.label}`
        ])
      )
    )
  }
})

// The row's actions: create a task from an unlinked item, and record a change
// for a merged PR that qualifies.
export const ActionsCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    const context = props.params.context
    const buttons = []
    if (row.canCreate) {
      buttons.push(
        h(
          'button',
          {
            class: 'btn sm',
            disabled: row.busy,
            title: `Create a task from this ${row.kind === 'pr' ? 'pull request' : 'issue'}`,
            onClick: () => context.onNewTask(row.raw)
          },
          row.busy ? [h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' New task'] : 'New task'
        )
      )
    }
    if (row.canRecord) {
      buttons.push(
        h(
          'button',
          {
            class: 'btn sm',
            disabled: row.busy,
            title: 'Record a change for this PR',
            onClick: () => context.onRecordChange(row.raw)
          },
          row.busy ? [h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' Record change'] : 'Record change'
        )
      )
    }
    return h('div', { class: 'repo-actions' }, buttons)
  }
})
