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
})
