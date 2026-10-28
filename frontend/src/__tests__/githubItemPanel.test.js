import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  issue: vi.fn(),
  pullReviewers: vi.fn(),
  pokePull: vi.fn()
}))

vi.mock('../api', () => ({
  api: { github: { issue: mocks.issue, pullReviewers: mocks.pullReviewers, pokePull: mocks.pokePull } }
}))

import GithubItemPanel from '../components/GithubItemPanel.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

const mountPanel = (url, props = {}) =>
  mount(GithubItemPanel, { props: { url, ...props }, global: { stubs: { RouterLink: RouterLinkStub } } })

const prUrl = 'https://github.com/acme/api/pull/42'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.people = []
  mocks.issue.mockResolvedValue({
    number: 42,
    title: 'Do the thing',
    url: prUrl,
    state: 'OPEN',
    is_draft: false,
    created_at: '2026-01-10T00:00:00Z',
    author: 'alice',
    labels: ['enhancement'],
    body: 'It **adds** the thing.'
  })
  mocks.pullReviewers.mockResolvedValue({
    reviewers: [
      { login: 'alice', state: 'COMMENTED', submitted_at: '2026-01-01T00:00:00Z', requested: false },
      { login: 'carol', state: 'PENDING', submitted_at: null, requested: true }
    ],
    error: null
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('GithubItemPanel reviewers', () => {
  it('lists a pull request’s reviewers under its author', async () => {
    const wrapper = mountPanel(prUrl)
    await flushPromises()

    expect(mocks.pullReviewers).toHaveBeenCalledWith(prUrl)
    expect(wrapper.get('.task-item-meta').text()).toContain('by')
    expect(wrapper.get('.task-item-meta').text()).toContain('alice')
    // The reviewers come after the author line and before the description.
    const html = wrapper.html()
    expect(html.indexOf('task-item-meta')).toBeLessThan(html.indexOf('review-people'))
    expect(html.indexOf('review-people')).toBeLessThan(html.indexOf('task-item-body'))
    const rows = wrapper.findAll('.review-person')
    expect(rows.map((row) => row.get('a').text())).toEqual(['@carol', '@alice'])
    expect(rows[0].text()).toContain('Awaiting review')
    expect(rows[1].text()).toContain('Commented')
  })

  it('names the pull request by the title read from GitHub when poking', async () => {
    mocks.pokePull.mockResolvedValue({ login: 'carol', slack_user_id: 'U0123', name: 'Carol', ts: '1.2' })

    const wrapper = mountPanel(prUrl)
    await flushPromises()
    await wrapper.findAll('.review-poke')[0].trigger('click')
    await flushPromises()

    expect(mocks.pokePull).toHaveBeenCalledWith({ url: prUrl, title: 'Do the thing', login: 'carol' })
    expect(store.toast).toEqual({ message: 'Poked Carol on Slack', isError: false })
  })

  it('shows a failed reviewers read instead of reading as no reviewers', async () => {
    mocks.pullReviewers.mockResolvedValue({
      reviewers: [],
      error: 'Could not read this pull request’s reviewers (is `gh` installed and authenticated?)'
    })

    const wrapper = mountPanel(prUrl)
    await flushPromises()

    expect(wrapper.text()).toContain('is `gh` installed and authenticated?')
    expect(wrapper.text()).not.toContain('No reviewers yet.')
  })

  it('hides the reviewers when the host shows another pane', async () => {
    const wrapper = mountPanel(prUrl, { showReviewers: false })
    await flushPromises()

    expect(mocks.pullReviewers).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Reviewers')
  })

  it('does not look for reviewers on an issue', async () => {
    mocks.issue.mockResolvedValue({
      number: 7,
      title: 'A bug',
      url: 'https://github.com/acme/api/issues/7',
      state: 'OPEN',
      author: 'alice',
      labels: [],
      body: 'It broke.'
    })

    const wrapper = mountPanel('https://github.com/acme/api/issues/7')
    await flushPromises()

    expect(mocks.pullReviewers).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Reviewers')
  })
})
