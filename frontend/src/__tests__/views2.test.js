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

import SettingsView from '../views/SettingsView.vue'
import TaskView from '../views/TaskView.vue'
import RepositoryDetailView from '../views/RepositoryDetailView.vue'
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
      description: '',
      model: null
    })
  })

  it('saves a harness model', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .get('input[placeholder="model, e.g. zai-coding-plan/glm-5.3 (empty uses the harness default)"]')
      .setValue('zai-coding-plan/glm-5.3')
    await wrapper
      .findAll('button')
      .filter((b) => b.text() === 'Save')[1]
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', { model: 'zai-coding-plan/glm-5.3' })
    expect(store.toast.message).toBe('Model saved')
  })

  it('adds a harness with a model', async () => {
    mocks.harnessesCreate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[placeholder="Name"]').setValue('Custom')
    await wrapper.get('input[placeholder="command (e.g. opencode)"]').setValue('custom-acp')
    await wrapper.get('input[placeholder="model (optional)"]').setValue('openai/gpt-5')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Add harness')
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesCreate).toHaveBeenCalledWith({
      name: 'Custom',
      command: 'custom-acp',
      args: [],
      description: '',
      model: 'openai/gpt-5'
    })
  })

  it('saves a resume command', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})

    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Save')
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', { resume_command: 'opencode --session {session}' })
    expect(store.toast.message).toBe('Resume command saved')
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

describe('RepositoryDetailView', () => {
  const repository = {
    id: 'r1',
    name: 'api',
    remote_url: 'https://github.com/acme/api.git',
    default_branch: 'main'
  }

  const ghItem = (id, kind, number, title, metadata_json) => ({
    id,
    source: 'github',
    kind,
    title,
    url: `https://github.com/acme/api/${kind === 'pr' ? 'pull' : 'issues'}/${number}`,
    metadata_json,
    task_ids: ['t1'],
    fetched_at: null
  })

  beforeEach(() => {
    vi.spyOn(store, 'loadRepositories').mockResolvedValue()
    vi.spyOn(store, 'loadItems').mockResolvedValue()
    vi.spyOn(store, 'loadTasks').mockResolvedValue()
    store.repositories = [repository]
    store.tasks = [{ id: 't1', title: 'Task One', status: 'open' }]
    store.items = [
      ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN' }),
      ghItem('i2', 'issue', 2, 'Closed issue', { state: 'CLOSED' }),
      ghItem('i3', 'pr', 3, 'Open PR', { state: 'OPEN' }),
      ghItem('i4', 'pr', 4, 'Draft PR', { state: 'OPEN', is_draft: true }),
      ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED' })
    ]
  })

  const mountView = () =>
    mount(RepositoryDetailView, {
      props: { id: 'r1' },
      global: { stubs: { RouterLink: RouterLinkStub, StatusIcon: true } }
    })

  it('lists issues and PRs and filters them by kind', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).toContain('Merged PR')

    const kindRow = wrapper.get('[aria-label="Filter by kind"]')
    await kindRow
      .findAll('.btn')
      .find((b) => b.text().startsWith('Issues'))
      .trigger('click')

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).not.toContain('Merged PR')
    expect(kindRow.find('.btn.primary').text()).toContain('Issues')
  })

  it('filters by stored state with counts', async () => {
    const wrapper = mountView()
    await flushPromises()

    const stateRow = wrapper.get('[aria-label="Filter by state"]')
    expect(stateRow.findAll('.btn').map((b) => b.text())).toEqual([
      'Any state',
      'Open 2',
      'Draft 1',
      'Merged 1',
      'Closed 1'
    ])

    await stateRow
      .findAll('.btn')
      .find((b) => b.text().startsWith('Merged'))
      .trigger('click')
    expect(wrapper.text()).toContain('Merged PR')
    expect(wrapper.text()).not.toContain('Open issue')
    expect(wrapper.text()).not.toContain('Open PR')
  })

  it('keeps the title and number search', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label="Filter items"]').setValue('closed issue')
    expect(wrapper.text()).toContain('Closed issue')
    expect(wrapper.text()).not.toContain('Open issue')
    expect(wrapper.text()).not.toContain('Merged PR')
  })

  it('hides the kind filter when the repository has one kind', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'Only issue', { state: 'OPEN' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('[aria-label="Filter by kind"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Filter by state"]').exists()).toBe(true)
  })
})
