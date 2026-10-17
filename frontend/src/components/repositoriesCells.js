/* eslint-disable vue/one-component-per-file -- AG Grid resolves its cell renderers by name from one module. */
import { defineComponent, h } from 'vue'

// The cell renderers for the repositories list grid. AG Grid renders each cell
// with one of these and passes its `params` prop; the grid hands the shared
// router-link and the row's remove action through `params.context`, so these
// components stay presentation-only.

const params = { type: Object, required: true }

// The repository name, linking to its detail page.
export const NameCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    return h(
      props.params.context.RouterLink,
      { to: `/repositories/${row.id}`, class: 'title' },
      () => row.name || row.path
    )
  }
})

// The default branch, as a badge; nothing when the repository has none.
export const BranchCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const branch = props.params.data.default_branch
    return branch ? h('span', { class: 'badge' }, branch) : null
  }
})

// The row's remove action.
export const RemoveCell = defineComponent({
  props: { params },
  setup: (props) => () => {
    const row = props.params.data
    return h('div', { class: 'repo-actions' }, [
      h(
        'button',
        {
          class: 'btn sm danger',
          'aria-label': `Remove repository ${row.name}`,
          onClick: () => props.params.context.onRemove(row.raw)
        },
        'Remove'
      )
    ])
  }
})
