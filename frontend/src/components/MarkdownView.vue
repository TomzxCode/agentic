<script>
import { h } from 'vue'
import { renderMarkdown } from '../markdown'
import { mentionTargets } from '../mentions'
import { store } from '../store'

// Renders a Markdown source as sanitized HTML (see markdown.js). A render
// function sets innerHTML directly, which keeps v-html out of the templates
// while still producing the shared `.md` styling.
export default {
  props: {
    source: { type: String, default: '' },
    // Leave task-list checkboxes clickable rather than disabled.
    taskLists: { type: Boolean, default: false }
  },
  render() {
    const html = renderMarkdown(this.source, {
      taskListInteractive: this.taskLists,
      // A plain @name in the text links to the person or item it names.
      mentions: mentionTargets({ people: store.people, items: store.items })
    })
    return h('div', { class: 'md', innerHTML: html })
  }
}
</script>
