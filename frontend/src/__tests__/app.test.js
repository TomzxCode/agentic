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

beforeEach(() => {
  vi.clearAllMocks()
  route.fullPath = '/'
  route.name = 'tasks'
  route.params = {}
  store.tasks = []
  store.repositories = []
  store.groups = []
  store.settings = {}
  store.hintMode = false
  store.toast = null
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadGroups').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
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

  it('toggles the mobile sidebar', async () => {
    const wrapper = mountApp()
    await flushPromises()
    await wrapper.get('.menu-btn').trigger('click')
    expect(wrapper.get('.app').classes()).toContain('sidebar-open')
  })
})
