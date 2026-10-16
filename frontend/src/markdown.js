import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

// One shared renderer. Reports may carry raw HTML (a `<details>` section, a
// quoted PR body), so markdown-it is allowed to emit it and the result is then
// sanitized: scripts, event handlers, and `javascript:` URLs are stripped
// before the HTML reaches `v-html`.
const md = new MarkdownIt({ html: true, linkify: true })

// GitHub-style task lists: a list item whose text starts with `[ ]` or `[x]`
// renders a checkbox. By default the box is disabled, so read-only Markdown (a
// PR body, a review report) shows a task list without pretending it is
// clickable. Passing `env.taskListInteractive` leaves the box enabled, which the
// next-steps field uses to tick a step.
md.core.ruler.after('block', 'task-lists', (state) => {
  const interactive = Boolean(state.env && state.env.taskListInteractive)
  for (let i = 2; i < state.tokens.length; i++) {
    const inline = state.tokens[i]
    if (inline.type !== 'inline') continue
    // Only the item's first paragraph, i.e. the item text itself.
    if (state.tokens[i - 1].type !== 'paragraph_open' || state.tokens[i - 2].type !== 'list_item_open') continue
    const match = /^\[([ xX])\]\s+/.exec(inline.content)
    if (!match) continue
    const checked = match[1].toLowerCase() === 'x'
    const attrs = `type="checkbox" class="task-list-item-checkbox"${checked ? ' checked' : ''}${interactive ? '' : ' disabled'}`
    // Rewrite the item as `<input> rest`; the inline rule parses the raw HTML.
    inline.content = `<input ${attrs}> ` + inline.content.slice(match[0].length)
    state.tokens[i - 2].attrJoin('class', 'task-list-item')
  }
})

// External links open in a new tab so the app stays put.
const defaultLinkOpen =
  md.renderer.rules.link_open || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(source, env) {
  // DOMPurify drops `target` by default; it is safe to keep for the new-tab
  // link behaviour the renderer adds. The trailing newline markdown-it leaves
  // is trimmed so a container's `> :last-child` margin reset matches the last
  // block instead of a stray text node (which would leave it with its bottom
  // margin, reading as a blank line).
  return DOMPurify.sanitize(md.render(String(source || ''), env || {}), { ADD_ATTR: ['target'] }).trim()
}
