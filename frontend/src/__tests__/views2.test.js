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
  settingsPreviewPolicy: vi.fn(),
  settingsRefreshStatus: vi.fn(),
  repositoriesCreate: vi.fn(),
  repositoriesCreateBulk: vi.fn(),
  repositoriesRemove: vi.fn(),
  itemsRefresh: vi.fn(),
  itemsRefreshSource: vi.fn(),
  changesList: vi.fn(),
  changesCreate: vi.fn(),
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
    settings: {
      get: mocks.settingsGet,
      update: mocks.settingsUpdate,
      previewRefreshPolicy: mocks.settingsPreviewPolicy,
      refreshStatus: mocks.settingsRefreshStatus
    },
    repositories: {
      create: mocks.repositoriesCreate,
      createBulk: mocks.repositoriesCreateBulk,
      remove: mocks.repositoriesRemove
    },
    items: { refresh: mocks.itemsRefresh, refreshSource: mocks.itemsRefreshSource },
    changes: { list: mocks.changesList, create: mocks.changesCreate },
    tasks: { get: mocks.tasksGet, update: mocks.tasksUpdate, remove: mocks.tasksRemove }
  },
  openTaskStream: mocks.openTaskStream
}))

import SettingsView from '../views/SettingsView.vue'
import TaskView from '../views/TaskView.vue'
import RepositoryDetailView from '../views/RepositoryDetailView.vue'
import RepositoriesView from '../views/RepositoriesView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.harnesses = []
  store.repositories = []
  store.people = []
  mocks.changesList.mockResolvedValue([])
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
    mocks.settingsPreviewPolicy.mockResolvedValue({
      valid: true,
      enabled: true,
      tiers: [{ max_age_seconds: 86400, interval_seconds: 3600 }],
      fallback_seconds: 604800
    })
    mocks.settingsRefreshStatus.mockResolvedValue({ sources: {} })
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

  it('previews and saves each source refresh policy', async () => {
    mocks.settingsGet.mockResolvedValue({
      defaults: { slack_refresh_policy: '', github_refresh_policy: '' },
      overrides: { slack_refresh_policy: '1d=1h', github_refresh_policy: '1d=2h' }
    })
    mocks.settingsUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    const refreshNav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Refresh')
    await refreshNav.trigger('click')
    await flushPromises()
    expect(mocks.settingsPreviewPolicy).toHaveBeenCalledWith('1d=1h')
    expect(mocks.settingsPreviewPolicy).toHaveBeenCalledWith('1d=2h')
    expect(wrapper.text()).toContain('Slack threads')
    expect(wrapper.text()).toContain('GitHub issues/PRs')

    const inputs = wrapper.findAll('input[placeholder="1d=1h,7d=6h,30d=1d,*=7d"]')
    expect(inputs.length).toBe(2)
    await inputs[0].setValue('1d=3h')
    await inputs[0].trigger('blur')
    await flushPromises()
    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ slack_refresh_policy: '1d=3h' })
  })

  it('shows when each source last ran and how it went', async () => {
    mocks.settingsRefreshStatus.mockResolvedValue({
      sources: {
        slack: {
          last_run_at: new Date().toISOString(),
          refreshed: 2,
          failed: 1,
          error: 'slackx: rate limited',
          origin: 'manual'
        }
      }
    })
    const wrapper = mountView()
    await flushPromises()

    const refreshNav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Refresh')
    await refreshNav.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Last run:')
    expect(wrapper.text()).toContain('2 refreshed')
    expect(wrapper.text()).toContain('1 failed')
    expect(wrapper.text()).toContain('slackx: rate limited')
    expect(wrapper.text()).toContain('forced')
    // GitHub has no recorded run yet.
    expect(wrapper.text()).toContain('never')
  })

  it('force refreshes one source and reports the outcome', async () => {
    mocks.itemsRefreshSource.mockResolvedValue({ checked: 2, due: 2, refreshed: 2, failed: 0, items: [] })
    const wrapper = mountView()
    await flushPromises()

    const refreshNav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Refresh')
    await refreshNav.trigger('click')
    await flushPromises()

    const buttons = wrapper.findAll('button').filter((b) => b.text() === 'Force refresh')
    expect(buttons.length).toBe(2)
    await buttons[0].trigger('click')
    await flushPromises()
    expect(mocks.itemsRefreshSource).toHaveBeenCalledWith('slack')
  })

  it('lets one source force refresh while the other is still refreshing', async () => {
    let pending
    mocks.itemsRefreshSource.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          pending = resolve
        })
    )
    const wrapper = mountView()
    await flushPromises()

    const refreshNav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Refresh')
    await refreshNav.trigger('click')
    await flushPromises()

    const buttons = wrapper.findAll('button').filter((b) => b.text() === 'Force refresh')
    await buttons[0].trigger('click')
    await flushPromises()
    expect(buttons[0].attributes('disabled')).toBeDefined()
    expect(buttons[1].attributes('disabled')).toBeUndefined()

    pending()
    await flushPromises()
    expect(buttons[0].attributes('disabled')).toBeUndefined()
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
  // Renders the labels of the links it is handed, so the header's choice of the
  // newest link set can be asserted.
  const SessionLinksStub = {
    name: 'SessionLinks',
    props: ['links', 'compact'],
    template: '<div class="sl">{{ (links || []).map((l) => l.label).join(",") }}</div>'
  }

  const stubs = {
    RouterLink: RouterLinkStub,
    EditableText: EditableStub,
    SearchSelect: passthrough,
    RepositorySelect: passthrough,
    PeopleSelect: passthrough,
    StatusIcon: passthrough,
    PriorityIcon: passthrough,
    ContextPanel: passthrough,
    AgentPanel: passthrough,
    SessionsPanel: passthrough,
    ItemsPanel: passthrough,
    WorktreesPanel: passthrough,
    DependenciesSelect: passthrough,
    TimelinePanel: passthrough,
    SessionLinks: SessionLinksStub
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

  it('shows a recorded session link in the header', async () => {
    mocks.tasksGet.mockResolvedValue({
      ...task,
      sessions: [
        {
          id: 's1',
          session_id: 'ses_1',
          created_at: '2026-02-01T00:00:00Z',
          links: [{ id: 'openchamber', label: 'Open in OpenChamber', url: 'http://oc/?session=ses_1' }]
        }
      ]
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('.sl').text()).toBe('Open in OpenChamber')
  })

  it('shows the newest link set across runs and sessions', async () => {
    mocks.tasksGet.mockResolvedValue({
      ...task,
      runs: [{ id: 'r1', created_at: '2026-01-01T00:00:00Z', links: [{ id: 'command', label: 'Resume command' }] }],
      sessions: [
        {
          id: 's1',
          session_id: 'ses_1',
          created_at: '2026-02-01T00:00:00Z',
          links: [{ id: 'openchamber', label: 'Open in OpenChamber', url: 'u' }]
        }
      ]
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('.sl').text()).toBe('Open in OpenChamber')
  })

  it('renders every property under its own label', async () => {
    const wrapper = mountView()
    await flushPromises()
    const labels = wrapper.findAll('.properties .prop-label').map((label) => label.text())
    expect(labels).toEqual(['Status', 'Priority', 'Deadline', 'Tags', 'People', 'Requested by', 'Repositories'])
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

  it('copies the task id', async () => {
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('button[title="Copy task id: t1"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('t1')
    expect(store.toast).toEqual({ message: 'Copied task id', isError: false })
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
    vi.spyOn(store, 'loadPeople').mockResolvedValue()
    store.repositories = [repository]
    store.people = []
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

  it('shows each item state as a badge', async () => {
    const wrapper = mountView()
    await flushPromises()

    const badges = wrapper.findAll('.badge.st-open, .badge.st-draft, .badge.st-merged, .badge.st-closed')
    expect(badges.map((b) => b.text())).toEqual(['Closed', 'Open', 'Merged', 'Draft', 'Open'])
    expect(badges.map((b) => b.classes().find((c) => c.startsWith('st-')))).toEqual([
      'st-closed',
      'st-open',
      'st-merged',
      'st-draft',
      'st-open'
    ])
  })

  it('omits the state badge when no state is stored', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'Stateless issue', {})]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Stateless issue')
    expect(wrapper.find('.badge.st-open').exists()).toBe(false)
  })

  it('shows the author of each item', async () => {
    store.items = [
      ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN', author: 'alice' }),
      ghItem('i2', 'pr', 2, 'Merged PR', { state: 'MERGED', author: 'bob' })
    ]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('@alice')
    expect(wrapper.text()).toContain('@bob')
  })

  it('omits the author when none is stored', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'No author', { state: 'OPEN' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('No author')
    expect(wrapper.text()).not.toContain('@')
  })

  it('shows the changes that reference a pull request', async () => {
    mocks.changesList.mockResolvedValue([
      {
        id: 'c1',
        task_id: 't1',
        status: 'accepted',
        change_class: 'feature',
        title: 'Landed change',
        external_ref: 'https://github.com/acme/api/pull/5'
      },
      {
        id: 'c2',
        task_id: 't1',
        status: 'proposed',
        change_class: 'bugfix',
        title: 'Issue change',
        external_ref: 'https://github.com/acme/api/issues/1'
      },
      { id: 'c3', task_id: 't1', status: 'proposed', change_class: 'chore', title: 'Loose change' }
    ])
    const wrapper = mountView()
    await flushPromises()

    // Only the change naming a PR appears; a change for an issue or with no ref
    // stays off the repository view.
    expect(wrapper.text()).toContain('Landed change')
    expect(wrapper.text()).not.toContain('Issue change')
    expect(wrapper.text()).not.toContain('Loose change')
  })

  it('renders a change with its status badge and a link to its task', async () => {
    mocks.changesList.mockResolvedValue([
      {
        id: 'c1',
        task_id: 't1',
        status: 'accepted',
        change_class: 'feature',
        title: 'Landed change',
        external_ref: 'https://github.com/acme/api/pull/5'
      }
    ])
    const wrapper = mountLinked()
    await flushPromises()

    const row = wrapper.get('.change-line')
    expect(row.get('.badge').text()).toBe('accepted')
    expect(row.get('.badge').classes()).toContain('ok')
    expect(row.get('a[href="/task/t1"]').text()).toBe('Landed change')
  })

  it('shows no change rows when nothing references a pull request', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.change-line').exists()).toBe(false)
  })

  it('offers to record a change for a merged PR with a single task', async () => {
    const wrapper = mountView()
    await flushPromises()
    // Only the merged PR (i5) gets a button; open and draft PRs and issues do not.
    expect(wrapper.findAll('button[title="Record a change for this PR"]')).toHaveLength(1)
  })

  it('hides the record button for an open PR', async () => {
    store.items = [ghItem('i3', 'pr', 3, 'Open PR', { state: 'OPEN' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('hides the record button when a PR has more than one task', async () => {
    store.tasks = [
      { id: 't1', title: 'Task One', status: 'open' },
      { id: 't2', title: 'Task Two', status: 'open' }
    ]
    store.items = [{ ...ghItem('i5', 'pr', 5, 'Shared PR', { state: 'MERGED' }), task_ids: ['t1', 't2'] }]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('hides the record button when a change already references the PR', async () => {
    mocks.changesList.mockResolvedValue([
      {
        id: 'c1',
        task_id: 't1',
        status: 'accepted',
        change_class: 'feature',
        title: 'Landed change',
        external_ref: 'https://github.com/acme/api/pull/5'
      }
    ])
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it("records a change on the PR's single task and shows it", async () => {
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', merged_at: '2026-10-11T05:23:53Z' })]
    mocks.changesCreate.mockResolvedValue({
      id: 'c9',
      task_id: 't1',
      status: 'accepted',
      change_class: 'feature',
      title: 'Merged PR',
      external_ref: 'https://github.com/acme/api/pull/5',
      opened_at: '2026-10-11T05:23:53Z'
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()

    expect(mocks.changesCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Merged PR',
      external_ref: 'https://github.com/acme/api/pull/5',
      status: 'accepted',
      opened_at: '2026-10-11T05:23:53Z',
      accepted_at: '2026-10-11T05:23:53Z'
    })
    // The new change shows under the PR and the button is gone.
    const row = wrapper.get('.change-line')
    expect(row.text()).toContain('accepted')
    expect(row.get('a').text()).toBe('Merged PR')
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
    expect(store.toast.message).toBe('Change recorded')
  })

  it('refreshes the item to pick up the merge time when it is missing', async () => {
    // A merged PR fetched before merge times were stored carries none.
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED' })]
    mocks.itemsRefresh.mockResolvedValue(
      ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', merged_at: '2026-10-11T05:23:53Z' })
    )
    mocks.changesCreate.mockResolvedValue({ id: 'c9', task_id: 't1', status: 'accepted', change_class: 'feature' })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).toHaveBeenCalledWith('i5')
    expect(mocks.changesCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Merged PR',
      external_ref: 'https://github.com/acme/api/pull/5',
      status: 'accepted',
      opened_at: '2026-10-11T05:23:53Z',
      accepted_at: '2026-10-11T05:23:53Z'
    })
  })

  const LinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
  const mountLinked = () =>
    mount(RepositoryDetailView, {
      props: { id: 'r1' },
      global: { stubs: { RouterLink: LinkStub, StatusIcon: true } }
    })

  it('links the author to the person carrying the login as an alias', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice', 'alice@example.com'] }]
    store.items = [ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN', author: 'alice' })]
    const wrapper = mountLinked()
    await flushPromises()
    expect(wrapper.get('a[href="/person/p1"]').text()).toBe('@alice')
  })

  it('leaves the author unlinked when no person carries the login', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice'] }]
    store.items = [ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN', author: 'ghost' })]
    const wrapper = mountLinked()
    await flushPromises()
    expect(wrapper.text()).toContain('@ghost')
    expect(wrapper.find('a[href^="/person/"]').exists()).toBe(false)
  })

  it('keeps the title and number search', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label="Filter items"]').setValue('closed issue')
    expect(wrapper.text()).toContain('Closed issue')
    expect(wrapper.text()).not.toContain('Open issue')
    expect(wrapper.text()).not.toContain('Merged PR')
  })

  it('filters by linked task status with counts', async () => {
    store.tasks = [
      { id: 't1', title: 'Task One', status: 'open' },
      { id: 't2', title: 'Task Two', status: 'done' }
    ]
    store.items = [
      { ...ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN' }), task_ids: ['t1'] },
      { ...ghItem('i2', 'issue', 2, 'Closed issue', { state: 'CLOSED' }), task_ids: ['t2'] },
      { ...ghItem('i3', 'pr', 3, 'Open PR', { state: 'OPEN' }), task_ids: ['t1', 't2'] }
    ]
    const wrapper = mountView()
    await flushPromises()

    const statusRow = wrapper.get('[aria-label="Filter by task status"]')
    expect(statusRow.findAll('.btn').map((b) => b.text())).toEqual(['Any task status', 'Open 2', 'Done 2'])

    await statusRow
      .findAll('.btn')
      .find((b) => b.text().startsWith('Done'))
      .trigger('click')
    expect(wrapper.text()).toContain('Closed issue')
    expect(wrapper.text()).toContain('Open PR')
    expect(wrapper.text()).not.toContain('Open issue')
  })

  it('hides the kind filter when the repository has one kind', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'Only issue', { state: 'OPEN' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('[aria-label="Filter by kind"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Filter by state"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Filter by task status"]').exists()).toBe(true)
  })

  it('refreshes every issue and PR from GitHub', async () => {
    mocks.itemsRefresh.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[aria-label="Refresh issues and pull requests"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh.mock.calls.map((call) => call[0]).sort()).toEqual(['i1', 'i2', 'i3', 'i4', 'i5'])
    // The view reloads the items after refreshing, on top of the initial load.
    expect(store.loadItems).toHaveBeenCalledTimes(2)
    expect(store.toast.message).toBe('Refreshed 5 items')
    expect(store.toast.isError).toBe(false)
  })

  it('keeps going when one item refresh fails', async () => {
    mocks.itemsRefresh.mockImplementation((id) =>
      id === 'i2' ? Promise.reject(new Error('ghx down')) : Promise.resolve({})
    )
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[aria-label="Refresh issues and pull requests"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).toHaveBeenCalledTimes(5)
    expect(store.toast.message).toBe('Refreshed 4 of 5 items; 1 failed')
    expect(store.toast.isError).toBe(true)
  })

  it('disables the refresh button when there is nothing to refresh', async () => {
    store.items = []
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('[aria-label="Refresh issues and pull requests"]').attributes('disabled')).toBeDefined()
  })
})

describe('RepositoriesView', () => {
  const repository = {
    id: 'r1',
    name: 'api',
    remote_url: 'https://github.com/acme/api.git',
    path: '/src/api',
    default_branch: 'main'
  }

  const ghItem = (id, kind, number, metadata_json) => ({
    id,
    source: 'github',
    url: `https://github.com/acme/api/${kind === 'pr' ? 'pull' : 'issues'}/${number}`,
    metadata_json,
    task_ids: ['t1']
  })

  beforeEach(() => {
    vi.spyOn(store, 'loadRepositories').mockResolvedValue()
    vi.spyOn(store, 'loadItems').mockResolvedValue()
    store.repositories = [repository]
    store.items = [
      ghItem('i1', 'issue', 1, { state: 'OPEN' }),
      ghItem('i2', 'pr', 2, { state: 'MERGED' }),
      ghItem('i3', 'pr', 3, { state: 'OPEN', is_draft: true })
    ]
  })

  const mountView = () => mount(RepositoriesView, { global: { stubs: { RouterLink: RouterLinkStub } } })

  it("breaks each repository's associated items down by state", async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('1 open · 1 draft · 1 merged')
  })

  it('omits the state line when no item carries a state', async () => {
    store.items = [ghItem('i1', 'issue', 1, {})]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('api')
    expect(wrapper.text()).not.toContain('open')
  })
})
