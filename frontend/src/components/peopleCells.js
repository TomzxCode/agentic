import { defineComponent, h } from 'vue'

// The cell renderer for the people list grid: the person's name, linking to
// their detail page. The router-link comes through `params.context`, so the cell
// stays presentation-only.

export const NameCell = defineComponent({
  props: { params: { type: Object, required: true } },
  setup: (props) => () => {
    const row = props.params.data
    return h(props.params.context.RouterLink, { to: `/person/${row.id}`, class: 'title' }, () => row.name)
  }
})
