<script>
import { h } from 'vue'
import { renderMarkdown } from '../markdown'

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
    const html = renderMarkdown(this.source, { taskListInteractive: this.taskLists })
    return h('div', { class: 'md', innerHTML: html })
  }
}
</script>
