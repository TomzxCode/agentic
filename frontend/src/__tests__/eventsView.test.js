import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({ eventsList: vi.fn() }))

vi.mock('../api', () => ({ api: { events: { list: mocks.eventsList } } }))

import EventsView from '../views/EventsView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

function event(overrides = {}) {
  return {
    id: 'e1',
    task_id: 't1',
    task_title: 'Task one',
    task_status: 'open',
    type: 'created',
    message: 'Task created: Task one',
    data_json: {},
    client: 'web',
    actor: 'human',
    created_at: new Date().toISOString(),
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

describe('EventsView', () => {
  it('streams events grouped by day and links each back to its task', async () => {
    const now = Date.now()
    mocks.eventsList.mockResolvedValue([
      event({ id: 'e1', created_at: new Date(now).toISOString() }),
      event({
        id: 'e2',
        type: 'run_started',
        message: 'Agent run: do the thing',
        client: 'cli',
        actor: 'agent',
        created_at: new Date(now - 86400000).toISOString()
      })
    ])

    const wrapper = mount(EventsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Today')
    expect(wrapper.text()).toContain('Yesterday')
    expect(wrapper.text()).toContain('Task created: Task one')
    expect(wrapper.text()).toContain('Agent run: do the thing')
    expect(wrapper.get('a[href="/task/t1"]').text()).toBe('Task one')
    // Each day renders the timeline component over that day's events.
    expect(wrapper.findAll('.timeline')).toHaveLength(2)
    expect(wrapper.findAll('.gantt')).toHaveLength(2)
    expect(wrapper.findAll('.panel-head')).toHaveLength(0)
    expect(wrapper.text()).toContain('Run started')
    expect(wrapper.text()).toContain('cli · agent')
    // The date leads, the human-readable age sits below it.
    expect(wrapper.findAll('.event-when').length).toBeGreaterThan(0)
    const when = wrapper.get('.event-when')
    expect(when.findAll('time')[0].classes()).toContain('event-at')
    expect(when.findAll('time')[1].classes()).toContain('event-ago')
    expect(wrapper.get('.event-at').text()).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/)
  })

  it('reloads from the server when the actor or client filter changes', async () => {
    mocks.eventsList.mockResolvedValue([event()])
    const wrapper = mount(EventsView, stub)
    await flushPromises()
    expect(mocks.eventsList).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50 }))

    await wrapper.get('select[aria-label="Filter by actor"]').setValue('agent')
    await flushPromises()
    expect(mocks.eventsList).toHaveBeenLastCalledWith(expect.objectContaining({ actor: 'agent' }))

    await wrapper.get('select[aria-label="Filter by client"]').setValue('cli')
    await flushPromises()
    expect(mocks.eventsList).toHaveBeenLastCalledWith(expect.objectContaining({ actor: 'agent', client: 'cli' }))
  })

  it('pages older events with the last row as the cursor', async () => {
    const firstPage = Array.from({ length: 50 }, (_, index) =>
      event({ id: `e${index}`, created_at: new Date(Date.now() - index * 1000).toISOString() })
    )
    mocks.eventsList
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce([
        event({ id: 'old', message: 'Much older', created_at: new Date(Date.now() - 86400000).toISOString() })
      ])

    const wrapper = mount(EventsView, stub)
    await flushPromises()
    const loadMore = wrapper.findAll('button').find((button) => button.text().includes('Load older events'))
    await loadMore.trigger('click')
    await flushPromises()

    const last = firstPage[firstPage.length - 1]
    expect(mocks.eventsList).toHaveBeenLastCalledWith(
      expect.objectContaining({ before: last.created_at, beforeId: last.id, limit: 50 })
    )
    expect(wrapper.text()).toContain('Much older')
    // The second page was short, so there is nothing older to load.
    expect(wrapper.text()).not.toContain('Load older events')
  })

  it('says so when there is no activity', async () => {
    mocks.eventsList.mockResolvedValue([])
    const wrapper = mount(EventsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('No activity yet.')
  })
})
