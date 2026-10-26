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

// An @ mention starts at the beginning of the text or after whitespace or
// opening punctuation.
const MENTION_BEFORE = /[\s([{"'“‘>]/
// And ends at the end of the text or before whitespace or trailing punctuation.
const MENTION_AFTER = /[\s.,;:!?)\]}>'"]/

// Turn a plain `@name` into a reference link when the name is a person or an
// item the caller supplied in `env.mentions` (see mentionTargets). The editor
// writes plain text, so this is where a reference becomes clickable; the source
// itself never carries the link syntax.
md.inline.ruler.before('emphasis', 'mention', (state, silent) => {
  const targets = state.env?.mentions
  if (!targets?.length) return false
  if (state.src.charCodeAt(state.pos) !== 0x40) return false
  // A link inside a link is invalid (and the mention rule must not fire in one).
  if (state.linkLevel > 0) return false
  if (state.pos > 0 && !MENTION_BEFORE.test(state.src[state.pos - 1])) return false
  const rest = state.src.slice(state.pos + 1)
  const target = targets.find((entry) => rest.startsWith(entry.name))
  if (!target) return false
  const next = rest[target.name.length]
  if (next !== undefined && !MENTION_AFTER.test(next)) return false
  if (!silent) {
    const open = state.push('link_open', 'a', 1)
    open.attrs = [['href', target.href]]
    const text = state.push('text', '', 0)
    text.content = `@${target.name}`
    state.push('link_close', 'a', -1)
  }
  state.pos += target.name.length + 1
  return true
})

// A task reference is a Markdown link to /task/<id>. Its label is the title at
// insert time, but the id is what identifies the task; when the caller passes
// the tasks in `env.tasks`, render the current title so renaming a task updates
// every reference to it. Only labels that start with `@` are treated as
// references, so a hand-written link keeps its own text.
md.core.ruler.after('inline', 'task-links', (state) => {
  const tasks = state.env?.tasks
  if (!tasks?.length) return
  const titles = new Map(tasks.filter((task) => task?.id).map((task) => [task.id, task.title || 'Untitled task']))
  for (const token of state.tokens) {
    const children = token.children
    if (!children) continue
    for (let i = 0; i < children.length; i++) {
      const open = children[i]
      if (open.type !== 'link_open') continue
      const match = /^\/task\/([A-Za-z0-9_-]+)$/.exec(open.attrGet('href') || '')
      if (!match || !titles.has(match[1])) continue
      let close = i + 1
      while (close < children.length && children[close].type !== 'link_close') close++
      if (close >= children.length) continue
      const label = children[i + 1]
      if (label?.type !== 'text' || !label.content.startsWith('@')) continue
      const text = new state.Token('text', '', 0)
      text.content = `@${titles.get(match[1])}`
      children.splice(i + 1, close - i - 1, text)
      i += 1
    }
  }
})

// External links open in a new tab so the app stays put. A reference to a
// person, task, or item stays in the app and gets the mention styling.
const defaultLinkOpen =
  md.renderer.rules.link_open || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const href = tokens[idx].attrGet('href') || ''
  if (/^\/(person|items|task)\//.test(href)) {
    tokens[idx].attrJoin('class', 'mention')
  } else {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener noreferrer')
  }
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
