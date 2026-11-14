import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  issue: vi.fn(),
  taskLinks: vi.fn(),
  routeQuery: {}
}))

vi.mock('../api', () => ({
  api: { github: { issue: mocks.issue, taskLinks: mocks.taskLinks } }
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery })
}))

import TaskIssuePanel from '../components/TaskIssuePanel.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = {
  global: { stubs: { RouterLink: RouterLinkStub, AgentPanel: { template: '<div class="agent-stub" />' } } }
}

const task = {
  id: 't1',
  title: 'Fix the login bug',
  associations: [
    {
      id: 'a1',
      item: {
        id: 'i1',
        source: 'github',
        kind: 'issue',
        url: 'https://github.com/acme/api/issues/7',
        title: 'Stored title',
        content: 'stored body',
        metadata_json: { state: 'OPEN', author: 'bob', created_at: '2026-01-01T00:00:00Z' }
      }
    }
  ]
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.people = []
  mocks.routeQuery = {}
  mocks.taskLinks.mockResolvedValue({ issues: [], pulls: [] })
  mocks.issue.mockResolvedValue({
    number: 7,
    title: 'Broken thing',
    url: 'https://github.com/acme/api/issues/7',
    state: 'OPEN',
    author: 'alice',
    labels: ['bug'],
    body: 'It **fails**.'
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TaskIssuePanel', () => {
  it('reads the linked issue from GitHub and shows it with the agent panel', async () => {
    const wrapper = mount(TaskIssuePanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()

    expect(mocks.issue).toHaveBeenCalledWith('https://github.com/acme/api/issues/7')
    expect(wrapper.text()).toContain('acme/api#7')
    expect(wrapper.text()).toContain('Broken thing')
    expect(wrapper.text()).toContain('bug')
    expect(wrapper.text()).toContain('Open')
    // The body is rendered as Markdown.
    expect(wrapper.get('.task-item-body').html()).toContain('<strong>fails</strong>')
    // The Agent panel is the interface for acting on the issue.
    expect(wrapper.get('.agent-stub').exists()).toBe(true)
  })

  it('falls back to the stored item when GitHub cannot be read', async () => {
    mocks.issue.mockRejectedValue(new Error('ghx failed'))
    const wrapper = mount(TaskIssuePanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()

    expect(wrapper.text()).toContain('Could not read the issue from GitHub')
    expect(wrapper.text()).toContain('Stored title')
    expect(wrapper.text()).toContain('stored body')
    // The agent panel still renders, so the issue can be worked on.
    expect(wrapper.get('.agent-stub').exists()).toBe(true)
  })

  it('links the author to their person page when one carries the login', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice'] }]
    const wrapper = mount(TaskIssuePanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()

    expect(wrapper.get('.task-item-meta a[href="/person/p1"]').text()).toBe('alice')
  })

  it('links an author nobody carries to the prefilled creation page, kept grey', async () => {
    const wrapper = mount(TaskIssuePanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()

    const link = wrapper.get('.task-item-meta a[href="/person/new?name=alice&alias=alice"]')
    expect(link.text()).toBe('alice')
    expect(link.classes()).toContain('faint')
  })

  it('lists every linked issue and renders only the selected one', async () => {
    const second = {
      id: 'a2',
      item: {
        id: 'i2',
        source: 'github',
        kind: 'issue',
        url: 'https://github.com/acme/api/issues/8',
        title: 'Second issue',
        content: '',
        metadata_json: { state: 'OPEN' }
      }
    }
    const multi = { ...task, associations: [...task.associations, second] }
    mocks.taskLinks.mockResolvedValue({
      issues: [
        { number: 7, title: 'Broken thing', url: 'https://github.com/acme/api/issues/7', state: 'OPEN' },
        { number: 8, title: 'Second issue', url: 'https://github.com/acme/api/issues/8', state: 'CLOSED' }
      ],
      pulls: []
    })
    mocks.issue.mockImplementation(async (url) => ({
      number: Number(url.split('/').pop()),
      title: url.includes('/8') ? 'Second issue' : 'Broken thing',
      url,
      state: url.includes('/8') ? 'CLOSED' : 'OPEN',
      author: 'alice',
      labels: [],
      body: ''
    }))
    mocks.routeQuery = { view: 'issue', item: 'acme/api/8' }

    const wrapper = mount(TaskIssuePanel, { props: { task: multi, harnesses: [], selected: 'acme/api/8' }, ...stub })
    await flushPromises()

    // The task links two issues, so they are listed with their states.
    expect(wrapper.findAll('.task-link')).toHaveLength(2)
    expect(wrapper.get('.task-link.active').text()).toContain('#8')
    expect(wrapper.get('.task-link.active').text()).toContain('Closed')
    // Only the selected issue is read and rendered, and the task page stays put.
    expect(mocks.issue).toHaveBeenCalledWith('https://github.com/acme/api/issues/8')
    expect(mocks.issue).not.toHaveBeenCalledWith('https://github.com/acme/api/issues/7')
    expect(wrapper.findAll('.task-item-panel')).toHaveLength(1)
    expect(wrapper.text()).toContain('Second issue')
  })

  it('says so when the task links no issue', async () => {
    const wrapper = mount(TaskIssuePanel, { props: { task: { id: 't1', associations: [] }, harnesses: [] }, ...stub })
    await flushPromises()
    expect(wrapper.text()).toContain('not linked to an issue')
    expect(mocks.issue).not.toHaveBeenCalled()
  })
})
