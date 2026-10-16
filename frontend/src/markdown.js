import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

// One shared renderer. Reports may carry raw HTML (a `<details>` section, a
// quoted PR body), so markdown-it is allowed to emit it and the result is then
// sanitized: scripts, event handlers, and `javascript:` URLs are stripped
// before the HTML reaches `v-html`.
const md = new MarkdownIt({ html: true, linkify: true })

// External links open in a new tab so the app stays put.
const defaultLinkOpen =
  md.renderer.rules.link_open || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(source) {
  // DOMPurify drops `target` by default; it is safe to keep for the new-tab
  // link behaviour the renderer adds.
  return DOMPurify.sanitize(md.render(String(source || '')), { ADD_ATTR: ['target'] })
}
