import { describe, expect, it } from 'vitest'

import { renderMarkdown } from '../markdown'

describe('renderMarkdown', () => {
  it('renders headings, emphasis, and lists', () => {
    const html = renderMarkdown('# Verdict\n\n**Approved**\n\n- one\n- two\n')
    expect(html).toContain('<h1>Verdict</h1>')
    expect(html).toContain('<strong>Approved</strong>')
    expect(html).toContain('<li>one</li>')
  })

  it('renders a table', () => {
    const html = renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |\n')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>a</th>')
    expect(html).toContain('<td>1</td>')
  })

  it('keeps safe raw HTML like a details section', () => {
    const html = renderMarkdown('<details><summary>More</summary>body</details>')
    expect(html).toContain('<details>')
    expect(html).toContain('<summary>More</summary>')
  })

  it('strips scripts and inline event handlers', () => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n<div onclick="alert(2)">hi</div>')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onclick')
    expect(html).toContain('hi')
  })

  it('drops javascript: link targets', () => {
    const markdownLink = renderMarkdown('[click](javascript:alert(1))')
    expect(markdownLink).not.toContain('href="javascript:')
    // Raw HTML links are sanitized the same way.
    const rawLink = renderMarkdown('<a href="javascript:alert(2)">x</a>')
    expect(rawLink).not.toContain('href="javascript:')
  })

  it('opens links in a new tab', () => {
    const html = renderMarkdown('[docs](https://example.com/x)')
    expect(html).toContain('href="https://example.com/x"')
    expect(html).toContain('target="_blank"')
  })

  it('keeps person and item references in the app, styled as mentions', () => {
    const html = renderMarkdown('[@Ada](/person/p1) and [@Fix](/items/i1)')
    expect(html.match(/class="mention"/g)).toHaveLength(2)
    expect(html).not.toContain('target="_blank"')
  })

  it('keeps task references in the app, styled as mentions', () => {
    const html = renderMarkdown('see [@Fix login](/task/t1)')
    expect(html).toContain('class="mention"')
    expect(html).toContain('href="/task/t1"')
    expect(html).not.toContain('target="_blank"')
  })

  it("renders a task reference with the task's current title", () => {
    const tasks = [{ id: 't1', title: 'Fix login timeout' }]
    const html = renderMarkdown('see [@Old title](/task/t1)', { tasks })
    expect(html).toContain('@Fix login timeout')
    expect(html).not.toContain('Old title')
  })

  it('keeps a task reference label when the task is not loaded', () => {
    const html = renderMarkdown('see [@Old title](/task/missing)', { tasks: [{ id: 't1', title: 'Other' }] })
    expect(html).toContain('@Old title')
  })

  it('keeps a hand-written task link label', () => {
    const html = renderMarkdown('[read this first](/task/t1)', { tasks: [{ id: 't1', title: 'Fix login timeout' }] })
    expect(html).toContain('read this first')
  })

  it('links a plain @ name to the person or item it names', () => {
    const html = renderMarkdown('ask @Ada Lovelace to review', {
      mentions: [{ name: 'Ada Lovelace', href: '/person/p1' }]
    })
    expect(html).toContain('href="/person/p1"')
    expect(html).toContain('class="mention"')
    expect(html).toContain('@Ada Lovelace')
    expect(html).not.toContain('target="_blank"')
  })

  it('uses the longest matching name and respects word boundaries', () => {
    const mentions = [
      { name: 'Ada Lovelace', href: '/person/p1' },
      { name: 'Ada', href: '/person/p2' }
    ]
    const longest = renderMarkdown('hi @Ada Lovelace', { mentions })
    expect(longest).toContain('href="/person/p1"')
    expect(renderMarkdown('hi @Ada', { mentions })).toContain('href="/person/p2"')
    expect(renderMarkdown('mail@Ada', { mentions })).not.toContain('href="/person')
    expect(renderMarkdown('@Adax', { mentions })).not.toContain('href="/person')
  })

  it('does not link a mention inside inline code or another link label', () => {
    const mentions = [{ name: 'Ada', href: '/person/p1' }]
    expect(renderMarkdown('`@Ada`', { mentions })).not.toContain('href="/person')
    const nested = renderMarkdown('[see @Ada](/x)', { mentions })
    expect(nested.match(/<a /g)).toHaveLength(1)
  })

  it('renders a task list with checkboxes disabled by default', () => {
    const html = renderMarkdown('- [ ] one\n- [x] two\n')
    expect(html).toContain('class="task-list-item"')
    expect(html).toContain('type="checkbox"')
    expect(html).toContain('checked')
    expect(html).toContain('disabled')
  })

  it('leaves task-list checkboxes enabled when interactive', () => {
    const html = renderMarkdown('- [ ] one', { taskListInteractive: true })
    expect(html).toContain('type="checkbox"')
    expect(html).not.toContain('disabled')
  })

  it('has no trailing whitespace, so the last block keeps no bottom margin', () => {
    expect(renderMarkdown('hello')).toBe('<p>hello</p>')
    expect(renderMarkdown('- one\n- two')).toBe('<ul>\n<li>one</li>\n<li>two</li>\n</ul>')
  })
})
