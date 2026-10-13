import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  routeQuery: {},
  replace: vi.fn(),
  harnessesFull: vi.fn(),
  harnessesList: vi.fn(),
  harnessesCreate: vi.fn(),
  harnessesUpdate: vi.fn(),
  settingsGet: vi.fn(),
  settingsUpdate: vi.fn(),
  repositoriesCreate: vi.fn(),
  repositoriesCreateBulk: vi.fn(),
  repositoriesRemove: vi.fn(),
  tasksGet: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksRemove: vi.fn(),
  openTaskStream: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery }),
  useRouter: () => ({ replace: mocks.replace })
}))

vi.mock('../api', () => ({
  api: {
    harnesses: {
      full: mocks.harnessesFull,
      list: mocks.harnessesList,
      create: mocks.harnessesCreate,
      update: mocks.harnessesUpdate
    },
    settings: { get: mocks.settingsGet, update: mocks.settingsUpdate },
    repositories: {
      create: mocks.repositoriesCreate,
      createBulk: mocks.repositoriesCreateBulk,
      remove: mocks.repositoriesRemove
    },
    tasks: { get: mocks.tasksGet, update: mocks.tasksUpdate, remove: mocks.tasksRemove }
  },
  openTaskStream: mocks.openTaskStream
}))

import DirectoryPicker from '../components/DirectoryPicker.vue'
import SettingsView from '../views/SettingsView.vue'
import TaskView from '../views/TaskView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.harnesses = []
  store.repositories = []
  mocks.routeQuery = {}
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('SettingsView', () => {
  beforeEach(() => {
    vi.spyOn(store, 'loadRepositories').mockResolvedValue()
    mocks.harnessesFull.mockResolvedValue([
      { id: 'opencode', name: 'OpenCode', command: 'opencode', resume_command: 'opencode --session {session}' }
    ])
    mocks.harnessesList.mockResolvedValue([{ id: 'opencode', available: true, detail: '/usr/bin/opencode' }])
    mocks.settingsGet.mockResolvedValue({
      defaults: { openchamber_session_path: '/?session={session}' },
      overrides: {}
    })
  })

  const mountView = () =>
    mount(SettingsView, {
      global: { stubs: { RepositoryGroupsPanel: true, RouterLink: RouterLinkStub } }
    })

  it('loads data and switches sections', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(store.loadRepositories).toHaveBeenCalled()
    expect(wrapper.text()).toContain('OpenCode')

    const harnesses = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Agent harnesses')
    await harnesses.trigger('click')
    expect(mocks.replace).toHaveBeenCalledWith({ query: { section: 'harnesses' } })
  })

  it('saves a session link field on blur', async () => {
    mocks.settingsUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    const input = wrapper.get('input[placeholder="http://localhost:3001"]')
    await input.setValue('http://oc/')
    await input.trigger('blur')
    await flushPromises()
    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ openchamber_url: 'http://oc/' })
  })

  it('adds a repository by path', async () => {
    mocks.repositoriesCreate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[placeholder="/absolute/path/to/git/repo"]').setValue('/repo')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Add repository')
      .trigger('click')
    await flushPromises()
    expect(mocks.repositoriesCreate).toHaveBeenCalledWith({ path: '/repo' })
  })

  it('adds repositories through the picker and reports skips', async () => {
    mocks.repositoriesCreateBulk.mockResolvedValue({ added: [{}], errors: [{ path: '/x', error: 'nope' }] })
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Browse…')
      .trigger('click')
    await flushPromises()
    wrapper.findComponent(DirectoryPicker).vm.$emit('add', ['/a'])
    await flushPromises()
    expect(mocks.repositoriesCreateBulk).toHaveBeenCalledWith(['/a'])
    expect(store.toast.message).toContain('skipped')
  })

  it('adds a harness with parsed args', async () => {
    mocks.harnessesCreate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[placeholder="Name"]').setValue('Custom')
    await wrapper.get('input[placeholder="command (e.g. opencode)"]').setValue('custom-acp')
    await wrapper.get('input[placeholder="args (space separated, e.g. acp)"]').setValue('--flag acp')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Add harness')
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesCreate).toHaveBeenCalledWith({
      name: 'Custom',
      command: 'custom-acp',
      args: ['--flag', 'acp'],
      description: ''
    })
  })

  it('saves a resume command and removes a repository', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})
    mocks.repositoriesRemove.mockResolvedValue({})
    vi.stubGlobal('confirm', () => true)
    store.repositories = [{ id: 'r1', name: 'Repo', path: '/p', default_branch: 'main', remote_url: 'git@x' }]

    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Save')
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', { resume_command: 'opencode --session {session}' })
    expect(store.toast.message).toBe('Resume command saved')

    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.repositoriesRemove).toHaveBeenCalledWith('r1')
  })

  it('sets a default harness', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})
    mocks.harnessesFull.mockResolvedValue([
      { id: 'opencode2', name: 'OpenCode v2', command: 'opencode2', is_default: true, resume_command: '' },
      { id: 'pi', name: 'pi', command: 'pi-acp', is_default: false, resume_command: '' }
    ])

    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Set default')
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('pi', { is_default: true })
    expect(store.toast.message).toBe('Default harness updated')
  })
})

describe('TaskView', () => {
  const task = {
    id: 't1',
    title: 'My task',
    description: 'desc',
    status: 'open',
    priority: 2,
    repository_ids: [],
    timeline: [],
    runs: []
  }

  const EditableStub = {
    props: ['value', 'placeholder'],
    emits: ['save'],
    template: '<div class="et" @click="$emit(\'save\', \'NEW\')"></div>'
  }
  const passthrough = { template: '<div class="stub"><slot /></div>' }

  const stubs = {
    RouterLink: RouterLinkStub,
    EditableText: EditableStub,
    SearchSelect: passthrough,
    RepositorySelect: passthrough,
    StatusIcon: passthrough,
    PriorityIcon: passthrough,
    ContextPanel: passthrough,
    AgentPanel: passthrough,
    ItemsPanel: passthrough,
    WorktreesPanel: passthrough,
    TimelinePanel: passthrough,
    SessionLinks: passthrough
  }

  beforeEach(() => {
    mocks.tasksGet.mockResolvedValue(task)
    mocks.openTaskStream.mockReturnValue(vi.fn())
    vi.spyOn(store, 'loadHarnesses').mockResolvedValue()
    vi.spyOn(store, 'loadRepositories').mockResolvedValue()
  })

  const mountView = () => mount(TaskView, { props: { id: 't1' }, global: { stubs } })

  it('loads the task and subscribes to its stream', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(mocks.tasksGet).toHaveBeenCalledWith('t1')
    expect(mocks.openTaskStream).toHaveBeenCalledWith('t1', expect.any(Function))
    expect(wrapper.find('.et').exists()).toBe(true)
  })

  it('shows a not-found state when the load fails', async () => {
    mocks.tasksGet.mockRejectedValue(new Error('404'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Task not found')
  })

  it('reloads when the task stream reports a change', async () => {
    let onEvent
    mocks.openTaskStream.mockImplementation((id, cb) => {
      onEvent = cb
      return vi.fn()
    })
    mountView()
    await flushPromises()
    expect(mocks.tasksGet).toHaveBeenCalledTimes(1)

    onEvent({ kind: 'task', action: 'updated' })
    await flushPromises()
    expect(mocks.tasksGet).toHaveBeenCalledTimes(2)
  })

  it('saves an edited field', async () => {
    mocks.tasksUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.et').trigger('click')
    await flushPromises()
    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { title: 'NEW' })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('blurs the focused field on Escape', async () => {
    const wrapper = mount(TaskView, {
      props: { id: 't1' },
      attachTo: document.body,
      global: { stubs }
    })
    await flushPromises()
    const entry = wrapper.get('.tag-entry')
    entry.element.focus()
    expect(document.activeElement).toBe(entry.element)
    await entry.trigger('keydown', { key: 'Escape' })
    expect(document.activeElement).not.toBe(entry.element)
  })

  it('deletes the task when confirmed', async () => {
    mocks.tasksRemove.mockResolvedValue(null)
    vi.stubGlobal('confirm', () => true)
    vi.stubGlobal('location', { reload: vi.fn() })

    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Delete')
      .trigger('click')
    await flushPromises()
    expect(mocks.tasksRemove).toHaveBeenCalledWith('t1')
  })

  it('clears palette state on unmount', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(typeof store.focusField).toBe('function')
    wrapper.unmount()
    expect(store.focusField).toBeNull()
  })
})
