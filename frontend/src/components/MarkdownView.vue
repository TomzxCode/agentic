<script>
import { h } from 'vue'
import { renderMarkdown } from '../markdown'

// Renders a Markdown source as sanitized HTML (see markdown.js). A render
// function sets innerHTML directly, which keeps v-html out of the templates
// while still producing the shared `.md` styling.
export default {
  props: { source: { type: String, default: '' } },
  render() {
    return h('div', { class: 'md', innerHTML: renderMarkdown(this.source) })
  }
}
</script>
