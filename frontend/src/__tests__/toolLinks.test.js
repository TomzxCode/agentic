import { describe, expect, it } from 'vitest'
import { ghxItemUrl, ghxRepoUrl, githubItemTarget, itemToolLinks, slackItemTarget, slackxItemUrl } from '../toolLinks'

describe('githubItemTarget', () => {
  it('reads an issue and a pull request URL, keeping their casing', () => {
    expect(githubItemTarget('https://github.com/Acme/Web/issues/42')).toEqual({
      owner: 'Acme',
      repo: 'Web',
      kind: 'issues',
      number: '42'
    })
    expect(githubItemTarget('https://github.com/Acme/Web/pull/7')).toMatchObject({ kind: 'pulls', number: '7' })
  })

  it('ignores anything that is not a GitHub issue or PR', () => {
    expect(githubItemTarget('https://github.com/Acme/Web')).toBeNull()
    expect(githubItemTarget(null)).toBeNull()
  })
})

describe('ghxItemUrl', () => {
  it('builds the ghx hash route for an issue and a PR', () => {
    expect(ghxItemUrl({ url: 'https://github.com/Acme/Web/issues/42' }, 'http://localhost:8080')).toBe(
      'http://localhost:8080/#/Acme/Web/issues/42'
    )
    expect(ghxItemUrl({ url: 'https://github.com/Acme/Web/pull/7' }, 'http://localhost:8080/')).toBe(
      'http://localhost:8080/#/Acme/Web/pulls/7'
    )
  })

  it('is null without a server URL or for a non-GitHub item', () => {
    expect(ghxItemUrl({ url: 'https://github.com/Acme/Web/issues/42' }, '')).toBeNull()
    expect(ghxItemUrl({ url: 'https://example.com/page' }, 'http://localhost:8080')).toBeNull()
  })
})

describe('ghxRepoUrl', () => {
  it('builds the ghx repository route from an https or ssh remote', () => {
    expect(ghxRepoUrl('https://github.com/Acme/Web.git', 'http://localhost:8080')).toBe(
      'http://localhost:8080/#/Acme/Web'
    )
    expect(ghxRepoUrl('git@github.com:Acme/Web.git', 'http://localhost:8080/')).toBe('http://localhost:8080/#/Acme/Web')
  })

  it('is null without a server URL or for a non-GitHub remote', () => {
    expect(ghxRepoUrl('https://github.com/Acme/Web.git', '')).toBeNull()
    expect(ghxRepoUrl('https://gitlab.com/Acme/Web.git', 'http://localhost:8080')).toBeNull()
  })
})

describe('slackItemTarget', () => {
  it('reads the channel and thread ts from a Slack permalink', () => {
    expect(slackItemTarget({ url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890123456' })).toEqual({
      channel: 'C0123ABCD',
      stamp: '1734567890123456',
      threadTs: '1734567890.123456'
    })
  })

  it('uses the thread_ts query of a reply permalink as the thread root', () => {
    expect(
      slackItemTarget({
        url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890999999?thread_ts=1734567890.123456&cid=C0123ABCD'
      })
    ).toEqual({ channel: 'C0123ABCD', stamp: '1734567890999999', threadTs: '1734567890.123456' })
  })

  it('falls back to the channel:ts external id', () => {
    expect(slackItemTarget({ external_id: 'C0123ABCD:1734567890123456' })).toEqual({
      channel: 'C0123ABCD',
      stamp: '1734567890123456',
      threadTs: '1734567890.123456'
    })
  })

  it('ignores anything that is not a Slack thread', () => {
    expect(slackItemTarget({ url: 'https://example.com/archives/nope' })).toBeNull()
  })
})

describe('slackxItemUrl', () => {
  it('builds the slackx archive route with the thread query', () => {
    expect(
      slackxItemUrl({ url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890123456' }, 'http://localhost:8280/')
    ).toBe('http://localhost:8280/archives/C0123ABCD/p1734567890123456?thread_ts=1734567890.123456')
  })

  it('is null without a server URL or for a non-Slack item', () => {
    expect(slackxItemUrl({ url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890123456' }, '')).toBeNull()
    expect(slackxItemUrl({ url: 'https://example.com' }, 'http://localhost:8280')).toBeNull()
  })
})

describe('itemToolLinks', () => {
  it('picks the link that matches the item source and the configured server', () => {
    expect(
      itemToolLinks(
        { source: 'github', url: 'https://github.com/Acme/Web/issues/42' },
        { ghx_url: 'http://ghx:8080', slackx_url: 'http://slackx:8280' }
      )
    ).toEqual([{ id: 'ghx', label: 'Open in ghx', url: 'http://ghx:8080/#/Acme/Web/issues/42' }])

    expect(
      itemToolLinks(
        { source: 'slack', url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890123456' },
        { ghx_url: 'http://ghx:8080', slackx_url: 'http://slackx:8280' }
      )
    ).toEqual([
      {
        id: 'slackx',
        label: 'Open in slackx',
        url: 'http://slackx:8280/archives/C0123ABCD/p1734567890123456?thread_ts=1734567890.123456'
      }
    ])
  })

  it('returns nothing when no server is configured', () => {
    expect(itemToolLinks({ source: 'github', url: 'https://github.com/Acme/Web/issues/42' }, {})).toEqual([])
  })
})
