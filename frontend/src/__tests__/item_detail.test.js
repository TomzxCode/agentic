import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  itemsGet: vi.fn(),
  itemsUpdate: vi.fn(),
  itemsRefresh: vi.fn(),
  itemsRemove: vi.fn(),
  reviewsGet: vi.fn(),
  reviewGet: vi.fn(),
  reviewersGet: vi.fn(),
  pathPreview: vi.fn(),
  poke: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush })
}))

vi.mock('../api', () => ({
  api: {
    items: {
      get: mocks.itemsGet,
      update: mocks.itemsUpdate,
      refresh: mocks.itemsRefresh,
      remove: mocks.itemsRemove,
      reviews: mocks.reviewsGet,
      review: mocks.reviewGet,
      reviewers: mocks.reviewersGet,
      pathPreview: mocks.pathPreview,
      poke: mocks.poke
    }
  }
}))

import ItemDetailView from '../views/ItemDetailView.vue'
import EditableText from '../components/EditableText.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const mountView = () =>
  mount(ItemDetailView, {
    props: { id: 'i1' },
    global: { stubs: { RouterLink: RouterLinkStub } }
  })

const item = (over = {}) => ({
  id: 'i1',
  source: 'github',
  kind: 'issue',
  title: 'Fix the bug',
  url: 'https://github.com/acme/api/issues/42',
  external_id: 'acme/api#42',
  metadata_json: { state: 'OPEN', author: 'alice' },
  content: 'The body of the issue.',
  fetched_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  task_ids: [],
  person_ids: [],
  ...over
})

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.tasks = []
  store.people = []
  store.settings = {}
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  mocks.reviewersGet.mockResolvedValue({ reviewers: [], error: null })
  mocks.reviewsGet.mockResolvedValue({ path: null, files: [] })
})

describe('ItemDetailView', () => {
  it('renders a GitHub issue with its state, author, repository, and body', async () => {
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Fix the bug')
    expect(wrapper.text()).toContain('acme/api')
    expect(wrapper.text()).toContain('@alice')
    expect(wrapper.get('.badge.st-open').text()).toBe('Open')
    expect(wrapper.text()).toContain('The body of the issue.')
    expect(wrapper.get('.task-actions a.btn').attributes('href')).toBe('https://github.com/acme/api/issues/42')
    expect(wrapper.get('.task-actions a.btn').text()).toBe('Open on GitHub')
  })

  it('links a GitHub item into the configured ghx server', async () => {
    store.settings = { ghx_url: 'http://localhost:8080' }
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()

    const link = wrapper.get('a[href="http://localhost:8080/#/acme/api/issues/42"]')
    expect(link.text()).toBe('Open in ghx')
  })

  it('links a Slack thread into the configured slackx server', async () => {
    store.settings = { slackx_url: 'http://localhost:8280' }
    mocks.itemsGet.mockResolvedValue(
      item({
        source: 'slack',
        kind: 'thread',
        title: 'Design chat',
        url: 'https://acme.slack.com/archives/C0123ABCD/p1734567890123456',
        external_id: 'C0123ABCD:1734567890123456'
      })
    )
    const wrapper = mountView()
    await flushPromises()

    const link = wrapper.get(
      'a[href="http://localhost:8280/archives/C0123ABCD/p1734567890123456?thread_ts=1734567890.123456"]'
    )
    expect(link.text()).toBe('Open in slackx')
  })

  it('renders a local path with its live preview and an editor link', async () => {
    store.settings = { editor_url_template: 'vscode://file{path}' }
    mocks.itemsGet.mockResolvedValue(
      item({
        source: 'file',
        kind: 'directory',
        title: 'project',
        url: null,
        external_id: '/tmp/project',
        metadata_json: {
          path: '/tmp/project',
          exists: true,
          kind: 'directory',
          size: 4096,
          modified_at: '2026-01-02T00:00:00Z'
        },
        // A path item never stores content.
        content: ''
      })
    )
    mocks.pathPreview.mockResolvedValue({
      path: '/tmp/project',
      exists: true,
      kind: 'directory',
      content: '/tmp/project\nmain.py\nsub/',
      truncated: false,
      error: null
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Directory')
    expect(wrapper.text()).toContain('/tmp/project')
    expect(wrapper.text()).toContain('main.py')
    expect(wrapper.get('.path-content').text()).toContain('sub/')
    expect(wrapper.text()).toContain('Preview read live from disk, not stored.')
    expect(wrapper.get('a[href="vscode://file/tmp/project"]').text()).toBe('Open in editor')
    // A path has no author, so it offers no person linker.
    expect(wrapper.text()).not.toContain('People')
  })

  it('renders a Markdown file in full as Markdown', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({
        source: 'file',
        kind: 'file',
        title: 'spec.md',
        url: null,
        external_id: '/tmp/spec.md',
        metadata_json: { path: '/tmp/spec.md', exists: true, kind: 'file', size: 40000 },
        content: ''
      })
    )
    const body = '# The spec\n\nA **bold** line.\n\n- one\n- two\n'
    mocks.pathPreview.mockResolvedValue({
      path: '/tmp/spec.md',
      exists: true,
      kind: 'file',
      content: body,
      truncated: false,
      error: null
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.path-markdown h1').text()).toBe('The spec')
    expect(wrapper.get('.path-markdown strong').text()).toBe('bold')
    expect(wrapper.findAll('.path-markdown li')).toHaveLength(2)
    // Text files and Markdown are shown whole, so no truncation notice.
    expect(wrapper.text()).not.toContain('Showing the first part of a large file.')
  })

  it('flags a local path that no longer exists', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({
        source: 'file',
        kind: 'file',
        title: 'gone.txt',
        url: null,
        external_id: '/tmp/gone.txt',
        metadata_json: { path: '/tmp/gone.txt', exists: false },
        content: ''
      })
    )
    mocks.pathPreview.mockResolvedValue({
      path: '/tmp/gone.txt',
      exists: false,
      content: '',
      truncated: false,
      error: '/tmp/gone.txt does not exist'
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('This path no longer exists')
  })

  it('renders the GitHub description as Markdown', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({ content: '## Steps\n\nRun **this** in `dir`:\n\n- one\n- two\n\n[docs](https://example.com/x)' })
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.md h2').text()).toBe('Steps')
    expect(wrapper.get('.md strong').text()).toBe('this')
    expect(wrapper.get('.md code').text()).toBe('dir')
    expect(wrapper.findAll('.md li')).toHaveLength(2)
    // Links open in a new tab; the raw Markdown is not shown.
    expect(wrapper.get('.md a').attributes('href')).toBe('https://example.com/x')
    expect(wrapper.get('.md a').attributes('target')).toBe('_blank')
    expect(wrapper.text()).not.toContain('**this**')
  })

  it('links the GitHub author to their person page', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice'] }]
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('a[href="/person/p1"]').text()).toContain('@alice')
  })

  it('links the GitHub author to the creation page when nobody carries the login', async () => {
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    const link = wrapper.get('a[href="/person/new?name=alice&alias=alice"]')
    expect(link.text()).toContain('@alice')
    expect(link.classes()).toContain('faint')
  })

  it('renders a Slack thread as a transcript', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({ source: 'slack', kind: 'thread', title: 'Design chat', content: 'ada: hello\nbob: hi' })
    )
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Thread')
    expect(wrapper.get('.slack-thread').text()).toContain('ada: hello')
    expect(wrapper.get('.task-actions a.btn').text()).toBe('Open in Slack')
  })

  it('marks a Slack conversation done, flags a later reply, and reopens it', async () => {
    const slack = item({ source: 'slack', kind: 'thread', title: 'Design chat', content: 'ada: hello' })
    mocks.itemsGet.mockResolvedValue(slack)
    mocks.itemsUpdate.mockResolvedValueOnce({
      ...slack,
      done: true,
      done_at: '2026-01-02T00:00:00Z',
      new_since_done: true,
      latest_message_at: '2026-01-03T00:00:00Z'
    })

    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Reopen this conversation"]').exists()).toBe(false)

    await wrapper.get('button[title="Mark this conversation done"]').trigger('click')
    await flushPromises()
    expect(mocks.itemsUpdate).toHaveBeenCalledWith('i1', { done: true })
    expect(wrapper.text()).toContain('done')
    expect(wrapper.text()).toContain('new messages')
    expect(wrapper.text()).toContain('A message arrived after this conversation was marked done')
    expect(store.toast).toEqual({ message: 'Marked done', isError: false })

    mocks.itemsUpdate.mockResolvedValueOnce({ ...slack, done: false, new_since_done: false })
    await wrapper.get('button[title="Reopen this conversation"]').trigger('click')
    await flushPromises()
    expect(mocks.itemsUpdate).toHaveBeenLastCalledWith('i1', { done: false })
    expect(wrapper.text()).not.toContain('new messages')
    expect(store.toast).toEqual({ message: 'Reopened', isError: false })
  })

  it('renders a note body', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({ source: 'note', kind: '', title: 'Remember', url: null, content: 'Rotate the token.' })
    )
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Note')
    expect(wrapper.text()).toContain('Rotate the token.')
    expect(wrapper.find('.task-actions a.btn').exists()).toBe(false)
    // A note has no source to re-fetch and no author, so neither is offered.
    expect(wrapper.find('button[aria-label="Refresh this item"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('People')
  })

  it('lists the linked tasks and people', async () => {
    store.tasks = [{ id: 't1', title: 'A task', status: 'open' }]
    store.people = [{ id: 'p1', name: 'Alice' }]
    mocks.itemsGet.mockResolvedValue(item({ task_ids: ['t1'], person_ids: ['p1'] }))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('a[href="/task/t1"]').text()).toContain('A task')
    expect(wrapper.get('a[href="/person/p1"]').text()).toContain('Alice')
  })

  it('shows a not-found state', async () => {
    mocks.itemsGet.mockRejectedValue(new Error('nope'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Item not found')
  })

  it('refreshes the item from its source', async () => {
    mocks.itemsGet.mockResolvedValue(item({ content: 'stale' }))
    mocks.itemsRefresh.mockResolvedValue(item({ content: 'fresh' }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('button[aria-label="Refresh this item"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('fresh')
    expect(store.toast).toEqual({ message: 'Refreshed', isError: false })
  })

  it('shows a failed refresh instead of a silent success', async () => {
    mocks.itemsGet.mockResolvedValue(item())
    mocks.itemsRefresh.mockResolvedValue(item({ fetch_error: 'slackx could not fetch the Slack thread' }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('button[aria-label="Refresh this item"]').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'slackx could not fetch the Slack thread', isError: true })
  })

  it('asks for the source title when the title is cleared', async () => {
    mocks.itemsGet.mockResolvedValue(item({ title_custom: true }))
    mocks.itemsUpdate.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(EditableText).vm.$emit('save', '')
    await flushPromises()
    expect(mocks.itemsUpdate).toHaveBeenCalledWith('i1', { title: '' })
  })

  it('offers a reset-title action only for a custom title', async () => {
    mocks.itemsGet.mockResolvedValue(item({ title_custom: true }))
    mocks.itemsUpdate.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    const reset = wrapper.get('button[aria-label="Reset this item\'s title"]')
    await reset.trigger('click')
    await flushPromises()
    expect(mocks.itemsUpdate).toHaveBeenCalledWith('i1', { title: '' })

    mocks.itemsGet.mockResolvedValue(item({ title_custom: false }))
    const plain = mountView()
    await flushPromises()
    expect(plain.find('button[aria-label="Reset this item\'s title"]').exists()).toBe(false)
  })

  it('deletes the item after confirmation and returns to resources', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.itemsGet.mockResolvedValue(item())
    mocks.itemsRemove.mockResolvedValue(null)
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('button[aria-label="Delete this item"]').trigger('click')
    expect(mocks.itemsRemove).toHaveBeenCalledWith('i1')
    expect(mocks.routerPush).toHaveBeenCalledWith('/items')
    vi.unstubAllGlobals()
  })

  it('groups a PR’s review reports by commit and opens the newest', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewsGet.mockResolvedValue({
      path: '/home/u/.sdlc/acme/api/pull-requests/42',
      files: [
        {
          name: 'review-pr.abc1234.md',
          skill: 'review-pr',
          commit: 'abc1234',
          size: 12,
          modified_at: '2026-01-03T00:00:00Z'
        },
        {
          name: 'validate-pr.abc1234.md',
          skill: 'validate-pr',
          commit: 'abc1234',
          size: 12,
          modified_at: '2026-01-02T00:00:00Z'
        },
        {
          name: 'review-pr.def5678.md',
          skill: 'review-pr',
          commit: 'def5678',
          size: 12,
          modified_at: '2026-01-01T00:00:00Z'
        }
      ]
    })
    mocks.reviewGet.mockResolvedValue({
      name: 'review-pr.abc1234.md',
      content: '<!-- {"step":"review-pr","sha":"abc1234"} -->\n# Verdict\n\nApproved.',
      truncated: false
    })

    const wrapper = mountView()
    await flushPromises()

    expect(mocks.reviewsGet).toHaveBeenCalledWith('i1')
    expect(mocks.reviewGet).toHaveBeenCalledWith('i1', 'review-pr.abc1234.md')
    expect(wrapper.text()).toContain('Review reports')
    expect(wrapper.text()).toContain('/home/u/.sdlc/acme/api/pull-requests/42')
    // One group per reviewed commit, newest commit first.
    const groups = wrapper.findAll('.review-group')
    expect(groups).toHaveLength(2)
    expect(groups[0].get('.review-commit').text()).toBe('abc1234')
    expect(groups[0].text()).toContain('2 reports')
    expect(groups[1].get('.review-commit').text()).toBe('def5678')
    // Reports are labelled by skill; the report itself is rendered as Markdown.
    expect(groups[0].findAll('.review-tabs button').map((b) => b.text())).toEqual(['review-pr', 'validate-pr'])
    expect(wrapper.get('.review-content h1').text()).toBe('Verdict')
    // The leading marker comment is stripped from the rendered body.
    expect(wrapper.get('.review-content').text()).not.toContain('step')
  })

  it('switches to another review report when its tab is clicked', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewsGet.mockResolvedValue({
      path: '/home/u/.sdlc/acme/api/pull-requests/42',
      files: [
        {
          name: 'review-pr.abc1234.md',
          skill: 'review-pr',
          commit: 'abc1234',
          size: 12,
          modified_at: '2026-01-03T00:00:00Z'
        },
        {
          name: 'validate-pr.abc1234.md',
          skill: 'validate-pr',
          commit: 'abc1234',
          size: 12,
          modified_at: '2026-01-02T00:00:00Z'
        }
      ]
    })
    mocks.reviewGet.mockImplementation((id, name) =>
      Promise.resolve({ name, content: `Body of ${name}`, truncated: false })
    )

    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.review-tabs button')[1].trigger('click')
    await flushPromises()

    expect(mocks.reviewGet).toHaveBeenLastCalledWith('i1', 'validate-pr.abc1234.md')
    expect(wrapper.get('.review-content').text()).toContain('Body of validate-pr.abc1234.md')
  })

  it('collects a commitless report under a No commit group', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewsGet.mockResolvedValue({
      path: '/home/u/.sdlc/acme/api/pull-requests/42',
      files: [{ name: 'gh-pr-view.md', skill: null, commit: null, size: 12, modified_at: '2026-01-03T00:00:00Z' }]
    })
    mocks.reviewGet.mockResolvedValue({ name: 'gh-pr-view.md', content: 'raw', truncated: false })

    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('.review-commit').text()).toBe('No commit')
    // With no skill, the tab falls back to the file name.
    expect(wrapper.get('.review-tabs button').text()).toBe('gh-pr-view')
  })

  it('does not look for review reports on an issue', async () => {
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    expect(mocks.reviewsGet).not.toHaveBeenCalled()
    expect(wrapper.find('.review-tabs').exists()).toBe(false)
  })

  it('lists a pull request’s reviewers, pending ones first and then newest', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewersGet.mockResolvedValue({
      reviewers: [
        { login: 'alice', state: 'COMMENTED', submitted_at: '2026-01-01T00:00:00Z', requested: false },
        { login: 'bob', state: 'APPROVED', submitted_at: '2026-01-03T00:00:00Z', requested: false },
        { login: 'carol', state: 'PENDING', submitted_at: null, requested: true }
      ],
      error: null
    })

    const wrapper = mountView()
    await flushPromises()

    expect(mocks.reviewersGet).toHaveBeenCalledWith('i1')
    expect(wrapper.text()).toContain('Reviewers')
    const rows = wrapper.findAll('.review-person')
    expect(rows.map((row) => row.get('a').text())).toEqual(['@carol', '@bob', '@alice'])
    expect(rows[0].text()).toContain('Awaiting review')
    expect(rows[0].text()).toContain('requested')
    expect(rows[1].text()).toContain('Approved')
    expect(rows[1].text()).toContain('last review')
    expect(rows[2].text()).toContain('Commented')
    // Every reviewer carries the poke action beside their name.
    expect(rows.map((row) => row.get('.review-poke').text())).toEqual(['👉', '👉', '👉'])
  })

  it('pokes a reviewer through Slack and reports who was reached', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewersGet.mockResolvedValue({
      reviewers: [{ login: 'alice', state: 'PENDING', submitted_at: null, requested: true }],
      error: null
    })
    mocks.poke.mockResolvedValue({ login: 'alice', slack_user_id: 'U0123ABCDEF', name: 'Alice', ts: '1.2' })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.review-poke').trigger('click')
    await flushPromises()

    expect(mocks.poke).toHaveBeenCalledWith('i1', 'alice')
    expect(store.toast).toEqual({ message: 'Poked Alice on Slack', isError: false })
  })

  it('shows why a poke could not be sent', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewersGet.mockResolvedValue({
      reviewers: [{ login: 'alice', state: 'PENDING', submitted_at: null, requested: true }],
      error: null
    })
    mocks.poke.mockRejectedValue(new Error('No person carries the GitHub login @alice.'))

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.review-poke').trigger('click')
    await flushPromises()

    expect(store.toast).toEqual({ message: 'No person carries the GitHub login @alice.', isError: true })
  })

  it('shows a failed reviewers read instead of reading as no reviewers', async () => {
    mocks.itemsGet.mockResolvedValue(item({ url: 'https://github.com/acme/api/pull/42', kind: 'pull_request' }))
    mocks.reviewersGet.mockResolvedValue({
      reviewers: [],
      error: 'Could not read this pull request’s reviewers (is `ghx` installed and authenticated?)'
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('is `ghx` installed and authenticated?')
    expect(wrapper.text()).not.toContain('No reviewers yet.')
  })

  it('does not ask GitHub for reviewers on an issue', async () => {
    mocks.itemsGet.mockResolvedValue(item())
    mountView()
    await flushPromises()
    expect(mocks.reviewersGet).not.toHaveBeenCalled()
  })
})
