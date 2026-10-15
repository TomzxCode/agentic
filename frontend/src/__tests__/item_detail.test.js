import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  itemsGet: vi.fn(),
  itemsUpdate: vi.fn(),
  itemsRefresh: vi.fn(),
  itemsRemove: vi.fn()
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
      remove: mocks.itemsRemove
    }
  }
}))

import ItemDetailView from '../views/ItemDetailView.vue'
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
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
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

  it('links the GitHub author to their person page', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice'] }]
    mocks.itemsGet.mockResolvedValue(item())
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('a[href="/person/p1"]').text()).toContain('@alice')
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

  it('renders a note body', async () => {
    mocks.itemsGet.mockResolvedValue(
      item({ source: 'note', kind: '', title: 'Remember', url: null, content: 'Rotate the token.' })
    )
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Note')
    expect(wrapper.text()).toContain('Rotate the token.')
    expect(wrapper.find('.task-actions a.btn').exists()).toBe(false)
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
})
