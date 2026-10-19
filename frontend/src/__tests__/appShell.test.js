import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksCreate: vi.fn(),
  githubIssues: vi.fn(),
  githubIssue: vi.fn()
}))

const route = reactive({ fullPath: '/', name: 'tasks', params: {}, query: {} })

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: mocks.push })
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.tasksUpdate, create: mocks.tasksCreate },
    github: { issues: mocks.githubIssues, issue: mocks.githubIssue }
  }
}))

import App from '../App.vue'
import { store } from '../store'
import { SIDEBAR_NAV_ITEMS } from '../sidebarNav'

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }
const SearchSelectStub = {
  props: ['modelValue', 'options', 'placeholder', 'sort', 'variant'],
  emits: ['update:modelValue'],
  template:
    '<div class="ss"><button v-for="o in options" :key="o.value" class="ss-opt" @click="$emit(\'update:modelValue\', o.value)">{{ o.label }}</button></div>'
}
const passthrough = { template: '<div><slot /></div>' }

const stubs = {
  RouterLink: RouterLinkStub,
  RouterView: true,
  SearchSelect: SearchSelectStub,
  RepositorySelect: passthrough,
  StatusIcon: true,
  PriorityIcon: true,
  CommandPalette: { props: ['items'], emits: ['select', 'close'], template: '<div class="palette-stub"></div>' }
}

function mountApp() {
  return mount(App, { attachTo: document.body, global: { stubs } })
}

// Same App, but with the real command palette so its items can be inspected.
function mountAppWithPalette() {
  const withoutPalette = { ...stubs }
  delete withoutPalette.CommandPalette
  return mount(App, { attachTo: document.body, global: { stubs: withoutPalette } })
}

beforeEach(() => {
  vi.clearAllMocks()
  route.fullPath = '/'
  route.name = 'tasks'
  route.params = {}
  store.tasks = []
  store.tags = []
  store.people = []
  store.items = []
  store.tagFilter = ''
  store.repositories = []
  store.groups = []
  store.settings = {}
  store.hintMode = false
  store.toast = null
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadTags').mockResolvedValue()
  vi.spyOn(store, 'loadGroups').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadItems').mockResolvedValue()
  vi.spyOn(store, 'loadSettings').mockResolvedValue()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('App', () => {
  it('loads the sidebar data and renders tasks', async () => {
    store.tasks = [
      { id: 't1', title: 'Task A', status: 'open', updated_at: null, next_steps: [], created_at: '2026-01-01' }
    ]
    const wrapper = mountApp()
    await flushPromises()
    expect(store.loadTasks).toHaveBeenCalled()
    expect(store.loadGroups).toHaveBeenCalled()
    expect(store.loadRepositories).toHaveBeenCalled()
    expect(store.loadSettings).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Task A')
  })

  it('hides done and archived tasks from the sidebar', async () => {
    store.tasks = [
      {
        id: 't1',
        title: 'In flight',
        status: 'in_progress',
        updated_at: null,
        next_steps: [],
        created_at: '2026-01-01'
      },
      { id: 't2', title: 'Finished', status: 'done', updated_at: null, next_steps: [], created_at: '2026-01-01' },
      { id: 't3', title: 'Stored away', status: 'archived', updated_at: null, next_steps: [], created_at: '2026-01-01' }
    ]
    const wrapper = mountApp()
    await flushPromises()
    const sidebar = wrapper.get('.side-scroll')
    expect(sidebar.text()).toContain('In flight')
    expect(sidebar.text()).not.toContain('Finished')
    expect(sidebar.text()).not.toContain('Stored away')
  })

  it('shows every in-flight task in the sidebar, with no tag filter', async () => {
    store.tags = [
      { name: 'bug', count: 1 },
      { name: 'ui', count: 1 }
    ]
    store.tasks = [
      { id: 't1', title: 'Bug task', status: 'open', updated_at: null, next_steps: [], tags: ['bug'] },
      { id: 't2', title: 'UI task', status: 'open', updated_at: null, next_steps: [], tags: ['ui'] }
    ]
    store.tagFilter = 'bug'
    const wrapper = mountApp()
    await flushPromises()
    expect(wrapper.find('.side-filters').exists()).toBe(false)
    expect(wrapper.get('.side-scroll').text()).toContain('Bug task')
    expect(wrapper.get('.side-scroll').text()).toContain('UI task')
  })

  it('creates a task with tags from the modal', async () => {
    mocks.tasksCreate.mockResolvedValue({ id: 'new3' })
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    await wrapper.get('input[placeholder="What needs to be solved?"]').setValue('Tagged')
    const entry = wrapper.get('.modal .tag-entry')
    await entry.setValue('bug')
    await entry.trigger('keydown', { key: 'Enter' })
    await wrapper.get('.modal .btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.tasksCreate).toHaveBeenCalledWith(expect.objectContaining({ title: 'Tagged', tags: ['bug'] }))
    expect(mocks.push).toHaveBeenCalledWith('/task/new3')
  })

  it('shows a caught-up message when every task is done', async () => {
    store.tasks = [
      { id: 't1', title: 'Finished', status: 'done', updated_at: null, next_steps: [], created_at: '2026-01-01' }
    ]
    const wrapper = mountApp()
    await flushPromises()
    expect(wrapper.get('.side-scroll').text()).toContain('All caught up')
    expect(wrapper.get('.side-scroll').text()).not.toContain('No tasks yet')
  })

  it('shows an empty state and a toast', async () => {
    store.toast = { message: 'hello', isError: false }
    const wrapper = mountApp()
    await flushPromises()
    expect(wrapper.text()).toContain('No tasks yet')
    expect(wrapper.get('.toast').text()).toBe('hello')
  })

  it('creates a task from the modal', async () => {
    mocks.tasksCreate.mockResolvedValue({ id: 'new1' })
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    const create = wrapper.get('.modal .btn.primary')
    expect(create.attributes('disabled')).toBeDefined()

    await wrapper.get('input[placeholder="What needs to be solved?"]').setValue('Do the thing')
    await create.trigger('click')
    await flushPromises()

    expect(mocks.tasksCreate).toHaveBeenCalledWith(expect.objectContaining({ title: 'Do the thing' }))
    expect(mocks.push).toHaveBeenCalledWith('/task/new1')
    expect(wrapper.find('.modal').exists()).toBe(false)
  })

  it('creates a task from a pasted Slack URL', async () => {
    mocks.tasksCreate.mockResolvedValue({ id: 'new2' })
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    const create = wrapper.get('.modal .btn.primary')
    expect(create.attributes('disabled')).toBeDefined()

    await wrapper
      .get('input[placeholder="Paste an issue, PR, or Slack thread URL…"]')
      .setValue('https://acme.slack.com/archives/C1/p2')
    expect(create.attributes('disabled')).toBeUndefined()

    await create.trigger('click')
    await flushPromises()

    expect(mocks.tasksCreate).toHaveBeenCalledWith(
      expect.objectContaining({ slack_url: 'https://acme.slack.com/archives/C1/p2' })
    )
    expect(mocks.push).toHaveBeenCalledWith('/task/new2')
  })

  it('previews a GitHub URL pasted into the same import field', async () => {
    mocks.githubIssue.mockResolvedValue({
      number: 7,
      title: 'Past bug',
      body: 'body',
      url: 'https://github.com/o/r/issues/7'
    })
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    await wrapper
      .get('input[placeholder="Paste an issue, PR, or Slack thread URL…"]')
      .setValue('https://github.com/o/r/issues/7')
    // The GitHub preview is debounced; wait past the 500 ms window.
    await new Promise((resolve) => setTimeout(resolve, 550))
    await flushPromises()

    expect(mocks.githubIssue).toHaveBeenCalledWith('https://github.com/o/r/issues/7')
    expect(wrapper.get('input[placeholder="What needs to be solved?"]').element.value).toBe('Past bug')
  })

  it('shows the repository group before the repositories in the modal', async () => {
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    const text = wrapper.get('.modal').text()
    expect(text.indexOf('Repository group')).toBeGreaterThan(-1)
    expect(text.indexOf('Repository group')).toBeLessThan(text.indexOf('Repositories (optional)'))
  })

  it('fills the repositories when a group is picked in the modal', async () => {
    store.repositories = [
      { id: 'r1', name: 'Repo One' },
      { id: 'r2', name: 'Repo Two' }
    ]
    store.groups = [{ id: 'g1', name: 'Frontend', repository_ids: ['r1', 'r2'] }]
    mocks.tasksCreate.mockResolvedValue({ id: 'new2' })
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    await wrapper
      .findAll('.ss-opt')
      .find((o) => o.text() === 'Frontend')
      .trigger('click')
    await wrapper.get('input[placeholder="What needs to be solved?"]').setValue('Grouped task')
    await wrapper.get('.modal .btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.tasksCreate).toHaveBeenCalledWith(
      expect.objectContaining({ group_id: 'g1', repository_ids: ['r1', 'r2'] })
    )
  })

  it('changes a task status from the sidebar and reverts on error', async () => {
    store.tasks = [{ id: 't1', title: 'Task A', status: 'open', updated_at: null, next_steps: [], created_at: 'x' }]
    mocks.tasksUpdate.mockResolvedValue({})
    const wrapper = mountApp()
    await flushPromises()

    await wrapper
      .findAll('.ss-opt')
      .find((o) => o.text() === 'Blocked')
      .trigger('click')
    await flushPromises()
    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { status: 'blocked' })

    mocks.tasksUpdate.mockRejectedValueOnce(new Error('nope'))
    store.tasks[0].status = 'open'
    await wrapper
      .findAll('.ss-opt')
      .find((o) => o.text() === 'Blocked')
      .trigger('click')
    await flushPromises()
    expect(store.tasks[0].status).toBe('open')
    expect(store.toast).toEqual({ message: 'nope', isError: true })
  })

  it('imports a GitHub issue through the modal', async () => {
    store.repositories = [{ id: 'r1', name: 'Repo One', remote_url: 'https://github.com/o/r' }]
    mocks.githubIssues.mockResolvedValue([
      { number: 2, title: 'Bug two', url: 'https://github.com/o/r/issues/2', state: 'open', author: 'a' }
    ])
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.new-task').trigger('click')
    await wrapper
      .findAll('.ss-opt')
      .find((o) => o.text() === 'Repo One')
      .trigger('click')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Load issues')
      .trigger('click')
    await flushPromises()
    expect(mocks.githubIssues).toHaveBeenCalledWith({ repository_id: 'r1', limit: 25 })

    await wrapper.get('.issue-row').trigger('click')
    await nextTick()
    expect(wrapper.get('input[placeholder="What needs to be solved?"]').element.value).toBe('Bug two')
  })

  it('toggles the command palette with the keyboard', async () => {
    const wrapper = mountApp()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    expect(wrapper.find('.palette-stub').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('.palette-stub').exists()).toBe(false)
  })

  it('opens the new task modal with Cmd/Ctrl+N', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const titleField = 'input[placeholder="What needs to be solved?"]'
    expect(wrapper.find(titleField).exists()).toBe(false)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', ctrlKey: true }))
    await nextTick()
    expect(wrapper.find(titleField).exists()).toBe(true)
  })

  it('offers tag filters in the command palette', async () => {
    store.tags = [{ name: 'bug', count: 2 }]
    store.tasks = [{ id: 't1', title: 'Task A', status: 'open', updated_at: null, next_steps: [], tags: ['bug'] }]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('bug')

    const tagItem = wrapper.findAll('.palette-item').find((i) => i.text().includes('Filter by tag: bug'))
    expect(tagItem).toBeTruthy()
    await tagItem.trigger('click')
    await flushPromises()
    expect(store.tagFilter).toBe('bug')
    expect(mocks.push).toHaveBeenCalledWith('/')
  })

  it('offers a clear-tag-filter action when a filter is active', async () => {
    store.tags = [{ name: 'bug', count: 1 }]
    store.tagFilter = 'bug'
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('clear')

    const clearItem = wrapper.findAll('.palette-item').find((i) => i.text().includes('Clear tag filter'))
    expect(clearItem).toBeTruthy()
    await clearItem.trigger('click')
    expect(store.tagFilter).toBe('')
  })

  it('offers people in the command palette and opens the picked one', async () => {
    store.people = [
      { id: 'p1', name: 'Ada Lovelace', aliases: ['ada', 'ada@example.com'] },
      { id: 'p2', name: 'Grace Hopper', aliases: [] }
    ]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('ada')

    const personItem = wrapper.findAll('.palette-item').find((i) => i.text().includes('Ada Lovelace'))
    expect(personItem).toBeTruthy()
    expect(personItem.text()).toContain('@ada · ada@example.com')
    await personItem.trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith('/person/p1')
  })

  it('offers items in the command palette and opens the picked one', async () => {
    store.items = [
      {
        id: 'i1',
        source: 'github',
        kind: 'issue',
        title: 'Fix login bug',
        url: 'https://github.com/acme/api/issues/1'
      },
      { id: 'i2', source: 'slack', kind: 'thread', title: 'Deploy thread', url: 'https://x.slack.com/archives/C1/p1' }
    ]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('deploy')

    const item = wrapper.findAll('.palette-item').find((i) => i.text().includes('Deploy thread'))
    expect(item).toBeTruthy()
    expect(item.text()).toContain('Slack')
    await item.trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith('/items/i2')
  })

  it('finds items by their source through the palette keywords', async () => {
    store.items = [
      {
        id: 'i1',
        source: 'github',
        kind: 'issue',
        title: 'Fix login bug',
        url: 'https://github.com/acme/api/issues/1'
      }
    ]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('github')

    const item = wrapper.findAll('.palette-item').find((i) => i.text().includes('Fix login bug'))
    expect(item).toBeTruthy()
  })

  it('offers repositories in the command palette and opens the picked one', async () => {
    store.repositories = [
      { id: 'r1', name: 'agents', path: '/home/tomzx/src/agents', remote_url: 'git@github.com:tomzx/agents.git' },
      { id: 'r2', name: 'scratch', path: '/home/tomzx/src/scratch', remote_url: null }
    ]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('agents')

    const repository = wrapper.findAll('.palette-item').find((i) => i.text().includes('agents'))
    expect(repository).toBeTruthy()
    expect(repository.text()).toContain('/home/tomzx/src/agents')
    await repository.trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith('/repositories/r1')
  })

  it('offers every settings section in the command palette and opens the picked one', async () => {
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await wrapper.get('.palette-input').setValue('settings')

    const labels = wrapper.findAll('.palette-item').map((item) => item.text())
    for (const section of [
      'Session links',
      'Identity',
      'Agent harnesses',
      'Agent prompts',
      'Refresh',
      'Repository groups',
      'Sidebar'
    ]) {
      expect(labels).toContain(section)
    }

    await wrapper.get('.palette-input').setValue('agent prompts')
    const section = wrapper.findAll('.palette-item').find((item) => item.text() === 'Agent prompts')
    expect(section).toBeTruthy()
    await section.trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith({ path: '/settings', query: { section: 'prompts' } })
  })

  it('shows an icon on every command palette item', async () => {
    store.tags = [{ name: 'bug', count: 1 }]
    store.tasks = [{ id: 't1', title: 'Task A', status: 'open', updated_at: null, next_steps: [], tags: ['bug'] }]
    const wrapper = mountAppWithPalette()
    await flushPromises()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()

    const items = wrapper.findAll('.palette-item')
    expect(items.length).toBeGreaterThan(0)
    for (const item of items) {
      expect(item.find('svg.palette-icon').exists()).toBe(true)
    }
  })

  it('enters focus-hint mode with f and focuses a control by letter', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const button = document.createElement('button')
    wrapper.get('.main').element.appendChild(button)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f' }))
    await nextTick()
    expect(store.hintMode).toBe(true)
    expect(wrapper.findAll('.hint-badge').length).toBeGreaterThan(0)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    await nextTick()
    expect(store.hintMode).toBe(false)
    expect(document.activeElement).toBe(button)
  })

  it('keeps short labels and dims non-matches past 26 entries', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const buttons = []
    for (let i = 0; i < 27; i += 1) {
      const button = document.createElement('button')
      wrapper.get('.main').element.appendChild(button)
      buttons.push(button)
    }

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f' }))
    await nextTick()
    const badges = wrapper.findAll('.hint-badge')
    expect(badges[0].text()).toBe('a')
    expect(badges[26].text()).toBe('aa')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    await nextTick()
    expect(store.hintMode).toBe(true)
    expect(badges[0].classes()).not.toContain('dimmed')
    expect(badges[26].classes()).not.toContain('dimmed')
    expect(badges[1].classes()).toContain('dimmed')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await nextTick()
    expect(store.hintMode).toBe(false)
    expect(document.activeElement).toBe(buttons[0])
  })

  it('undoes the last hint keystroke with backspace', async () => {
    const wrapper = mountApp()
    await flushPromises()

    for (let i = 0; i < 27; i += 1) {
      wrapper.get('.main').element.appendChild(document.createElement('button'))
    }

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f' }))
    await nextTick()
    const badges = wrapper.findAll('.hint-badge')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    await nextTick()
    expect(badges[1].classes()).toContain('dimmed')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace' }))
    await nextTick()
    expect(store.hintMode).toBe(true)
    expect(badges[1].classes()).not.toContain('dimmed')
  })

  it('focuses the two-letter hint when both letters are typed', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const buttons = []
    for (let i = 0; i < 27; i += 1) {
      const button = document.createElement('button')
      wrapper.get('.main').element.appendChild(button)
      buttons.push(button)
    }

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f' }))
    await nextTick()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    await nextTick()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    await nextTick()
    expect(store.hintMode).toBe(false)
    expect(document.activeElement).toBe(buttons[26])
  })

  it('toggles the mobile sidebar', async () => {
    window.innerWidth = 375
    const wrapper = mountApp()
    await flushPromises()
    await wrapper.get('.menu-btn').trigger('click')
    expect(wrapper.get('.app').classes()).toContain('sidebar-open')
    await wrapper.get('.sidebar-close').trigger('click')
    expect(wrapper.get('.app').classes()).not.toContain('sidebar-open')
    window.innerWidth = 1024
  })

  describe('sidebar nav configuration', () => {
    beforeEach(() => {
      localStorage.clear()
      window.innerWidth = 1024
    })

    it('renders the page icons in the configured order, leaving out the hidden ones', async () => {
      localStorage.setItem('agentic.sidebarNav', JSON.stringify({ order: ['settings', 'tasks'], hidden: ['gantt'] }))
      const wrapper = mountApp()
      await flushPromises()

      const titles = wrapper.findAll('.sidebar-nav-links .nav-link').map((link) => link.attributes('title'))
      expect(titles.slice(0, 2)).toEqual(['Settings', 'Tasks'])
      expect(titles).not.toContain('Gantt')
      expect(titles.length).toBe(SIDEBAR_NAV_ITEMS.length - 1)
    })

    it('lights the icon of a detail route through its route names', async () => {
      route.name = 'repository'
      const wrapper = mountApp()
      await flushPromises()
      const active = wrapper.findAll('.sidebar-nav-links .nav-link.active')
      expect(active.map((link) => link.attributes('title'))).toEqual(['Repositories'])
    })

    it('sizes the grid to the visible icons', async () => {
      localStorage.setItem(
        'agentic.sidebarNav',
        JSON.stringify({ order: [], hidden: ['reviews', 'stack', 'gantt', 'graph', 'metrics', 'items', 'people'] })
      )
      const wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.sidebar-nav-links').attributes('style')).toContain('--nav-cols: 5')
    })

    it('leaves out the nav container when every icon is hidden', async () => {
      const ids = SIDEBAR_NAV_ITEMS.map((item) => item.id)
      localStorage.setItem('agentic.sidebarNav', JSON.stringify({ order: ids, hidden: ids }))
      const wrapper = mountApp()
      await flushPromises()
      expect(wrapper.find('.sidebar-nav-links').exists()).toBe(false)
    })
  })
})
