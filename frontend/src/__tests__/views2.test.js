import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  routeQuery: {},
  replace: vi.fn(),
  routerPush: vi.fn(),
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
  githubRepository: vi.fn(),
  tasksCreate: vi.fn(),
  changesList: vi.fn(),
  changesCreate: vi.fn(),
  tasksGet: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksRemove: vi.fn(),
  openTaskStream: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery }),
  useRouter: () => ({ replace: mocks.replace, push: mocks.routerPush })
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
    github: { repository: mocks.githubRepository },
    changes: { list: mocks.changesList, create: mocks.changesCreate },
    tasks: { get: mocks.tasksGet, update: mocks.tasksUpdate, remove: mocks.tasksRemove, create: mocks.tasksCreate }
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
  mocks.githubRepository.mockResolvedValue({ items: [], failed: [] })
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

  it('edits user-defined agent prompts and saves them as JSON', async () => {
    mocks.settingsGet.mockResolvedValue({
      defaults: {
        agent_prompts: JSON.stringify([
          { kind: 'pull_request', label: 'Review PR', template: '$review-pr-full {number} {owner}/{repository}' }
        ])
      },
      overrides: {}
    })
    mocks.settingsUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    const promptsNav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Agent prompts')
    await promptsNav.trigger('click')
    await flushPromises()
    // The seeded default is shown when nothing is overridden.
    expect(wrapper.get('input[placeholder="$review-pr-full {number} {owner}/{repository}"]').element.value).toBe(
      '$review-pr-full {number} {owner}/{repository}'
    )

    await wrapper.get('input[placeholder="$review-pr-full {number} {owner}/{repository}"]').setValue('$x {number}')
    await wrapper.get('input[placeholder="$review-pr-full {number} {owner}/{repository}"]').trigger('blur')
    await flushPromises()
    expect(mocks.settingsUpdate).toHaveBeenCalledWith({
      agent_prompts: JSON.stringify([{ kind: 'pull_request', label: 'Review PR', template: '$x {number}' }])
    })
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
    NotesPanel: passthrough,
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

  it('puts the Notes section directly under Context', async () => {
    const wrapper = mount(TaskView, {
      props: { id: 't1' },
      global: {
        stubs: {
          ...stubs,
          ContextPanel: { template: '<section class="context" />' },
          NotesPanel: { template: '<section class="notes" />' }
        }
      }
    })
    await flushPromises()
    expect(wrapper.get('.context').element.nextElementSibling.classList.contains('notes')).toBe(true)
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

  it('renders the description as Markdown and edits it from its edit button', async () => {
    mocks.tasksGet.mockResolvedValue({
      ...task,
      description: 'A **bold** claim with [a link](https://example.com/x)'
    })
    // The real editor, so the rendered Markdown is asserted rather than a stub.
    const wrapper = mount(TaskView, {
      props: { id: 't1' },
      global: { stubs: { ...stubs, EditableText: false } }
    })
    await flushPromises()

    const description = wrapper.get('.task-description')
    expect(description.get('.md strong').text()).toBe('bold')
    expect(description.get('.md a').attributes('href')).toBe('https://example.com/x')
    expect(description.get('.md a').attributes('target')).toBe('_blank')
    expect(description.text()).not.toContain('**bold**')

    // The content is not an edit target (its own controls need the click); the
    // edit button opens the editor on the raw Markdown.
    await description.trigger('click')
    expect(description.find('textarea').exists()).toBe(false)

    await description.get('.inline-edit-btn').trigger('click')
    // The editor replaces the field, so re-query from the view.
    const textarea = wrapper.get('textarea')
    expect(textarea.element.value).toBe('A **bold** claim with [a link](https://example.com/x)')
    await textarea.setValue('Edited')
    await textarea.trigger('blur')
    await flushPromises()
    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { description: 'Edited' })
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
    mocks.tasksCreate.mockResolvedValue({ id: 't9', title: 'Imported issue' })
    store.repositories = [repository]
    store.people = []
    store.settings = {}
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

  it('shows the header right away and a spinner per section until the listing arrives', async () => {
    // The listing is the slow part; hold it pending to see the loading state.
    mocks.githubRepository.mockReturnValue(new Promise(() => {}))
    const wrapper = mountView()
    await flushPromises()

    // The top section is up while the listing loads.
    expect(wrapper.find('h1').text()).toBe('api')
    expect(wrapper.find('[aria-label="Refresh all issues and pull requests"]').exists()).toBe(true)
    // One spinner under each of the two section headings, and nothing else yet.
    expect(wrapper.findAll('.spinner')).toHaveLength(2)
    expect(wrapper.get('h2.group-head').text()).toBe('Issues')
    // A half-loaded page (no listing yet) does not flash the empty state or the
    // filters.
    expect(wrapper.text()).not.toContain('No issues or pull requests')
    expect(wrapper.find('input[aria-label="Filter items"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lists issues and PRs and filters them by kind', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).toContain('Merged PR')

    // Each filter group is named by an inline label, like the repositories list.
    expect(wrapper.findAll('.filter-label').map((l) => l.text())).toEqual(['Kind', 'State', 'Task status'])

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

  it('hides the record button for a merged PR someone else authored', async () => {
    store.settings = { github_login: 'me' }
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'someone' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('offers the record button when the author matches the configured login', async () => {
    store.settings = { github_login: 'me' }
    // Case-insensitive: GitHub logins differ in case.
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'Me' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(true)
  })

  it('offers the record button when no login is known', async () => {
    store.settings = {}
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'someone' })]
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(true)
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

  it('matches a change by the item external id, not only its url', async () => {
    mocks.changesList.mockResolvedValue([
      {
        id: 'c1',
        task_id: 't1',
        status: 'accepted',
        change_class: 'feature',
        title: 'Landed change',
        external_ref: 'acme/api#5'
      }
    ])
    store.items = [{ ...ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED' }), external_id: 'acme/api#5' }]
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Landed change')
    // A change already references the PR, so no duplicate is offered.
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

  it('refreshes the repository listing from GitHub', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 1, kind: 'issue', title: 'Open issue', url: 'https://github.com/acme/api/issues/1', state: 'OPEN' },
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: []
    })
    const wrapper = mountView()
    await flushPromises()

    // The unlinked PR appears alongside the stored, task-linked items.
    expect(wrapper.text()).toContain('Unlinked PR')

    await wrapper.get('[aria-label="Refresh all issues and pull requests"]').trigger('click')
    await flushPromises()

    // The refresh asks the backend to re-fetch from GitHub, not just re-read.
    expect(mocks.githubRepository).toHaveBeenLastCalledWith({
      repository_id: 'r1',
      state: 'all',
      limit: 1000,
      refresh: true
    })
    expect(store.toast.message).toBe('Refreshed 1 issue and 1 pull request')
    expect(store.toast.isError).toBe(false)
  })

  it('offers to create a task for an issue or PR no task uses', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 1, kind: 'issue', title: 'Open issue', url: 'https://github.com/acme/api/issues/1', state: 'OPEN' },
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: []
    })
    const wrapper = mountView()
    await flushPromises()

    // The unlinked PR gets the button; the stored, task-linked issue does not.
    expect(wrapper.find('button[title="Create a task from this pull request"]').exists()).toBe(true)
    expect(wrapper.find('button[title="Create a task from this issue"]').exists()).toBe(false)
  })

  it('creates a task from an unlinked PR and stays on the repository', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: []
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('button[title="Create a task from this pull request"]').trigger('click')
    await flushPromises()

    expect(mocks.tasksCreate).toHaveBeenCalledWith({ github_url: 'https://github.com/acme/api/pull/7' })
    // The import linked an item, so the stores reload and the row shows its chip.
    expect(store.loadItems).toHaveBeenCalledTimes(2)
    expect(store.loadTasks).toHaveBeenCalledTimes(2)
    // No navigation: the toast and the row's new task chip are the confirmation.
    expect(mocks.routerPush).not.toHaveBeenCalled()
    expect(store.toast.message).toBe('Task created')
    expect(store.toast.isError).toBe(false)
  })

  it('reports a failed task creation and stays on the repository', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: []
    })
    mocks.tasksCreate.mockRejectedValue(new Error('ghx down'))
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('button[title="Create a task from this pull request"]').trigger('click')
    await flushPromises()

    expect(mocks.routerPush).not.toHaveBeenCalled()
    expect(store.toast.message).toBe('ghx down')
    expect(store.toast.isError).toBe(true)
  })

  it('notes a per-kind listing failure but keeps the other kind', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: ['issues']
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Unlinked PR')
    expect(wrapper.text()).toContain('Could not load the issues from GitHub')
  })

  it('refreshes only the issues and PRs associated to tasks', async () => {
    mocks.itemsRefresh.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[aria-label="Refresh issues and pull requests associated to tasks"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh.mock.calls.map((call) => call[0]).sort()).toEqual(['i1', 'i2', 'i3', 'i4', 'i5'])
    // The view reloads the items after refreshing, on top of the initial load.
    expect(store.loadItems).toHaveBeenCalledTimes(2)
    expect(store.toast.message).toBe('Refreshed 5 linked items')
    expect(store.toast.isError).toBe(false)
  })

  it('keeps going when one linked item refresh fails', async () => {
    mocks.itemsRefresh.mockImplementation((id) =>
      id === 'i2' ? Promise.reject(new Error('ghx down')) : Promise.resolve({})
    )
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[aria-label="Refresh issues and pull requests associated to tasks"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).toHaveBeenCalledTimes(5)
    expect(store.toast.message).toBe('Refreshed 4 of 5 linked items; 1 failed')
    expect(store.toast.isError).toBe(true)
  })

  it('disables the linked refresh when nothing is associated to a task', async () => {
    store.items = []
    const wrapper = mountView()
    await flushPromises()
    expect(
      wrapper.get('[aria-label="Refresh issues and pull requests associated to tasks"]').attributes('disabled')
    ).toBeDefined()
    // The whole-repository refresh stays available: the remote is listable.
    expect(wrapper.get('[aria-label="Refresh all issues and pull requests"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps the stored items when the GitHub listing fails', async () => {
    mocks.githubRepository.mockRejectedValue(new Error('ghx down'))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).toContain('Could not list this repository from GitHub')
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

  it('filters by search and remote, and reports how much is shown', async () => {
    store.repositories = [
      {
        id: 'r1',
        name: 'api',
        remote_url: 'https://github.com/acme/api.git',
        path: '/src/api',
        default_branch: 'main'
      },
      { id: 'r2', name: 'tools', remote_url: null, path: '/src/tools' }
    ]
    const wrapper = mountView()
    await flushPromises()

    const paths = () => wrapper.findAll('.mono').map((d) => d.text())
    expect(paths()).toEqual(['/src/api', '/src/tools'])

    await wrapper.get('input[aria-label="Filter repositories"]').setValue('tools')
    expect(paths()).toEqual(['/src/tools'])
    expect(wrapper.text()).toContain('1 of 2 repositories')

    // The GitHub/Other buttons carry whole-list counts that do not move, and
    // each control group is named by an inline label.
    const toolbar = wrapper.get('.panel input ~ .row')
    expect(toolbar.findAll('.filter-label').map((l) => l.text())).toEqual(['Remote', 'Sort'])
    const remoteRow = toolbar.get('[aria-label="Filter by remote"]')
    expect(remoteRow.findAll('.btn').map((b) => b.text())).toEqual(['All 2', 'GitHub 1', 'Other 1'])

    await remoteRow
      .findAll('.btn')
      .find((b) => b.text().startsWith('Other'))
      .trigger('click')
    await wrapper.get('input[aria-label="Filter repositories"]').setValue('')
    expect(paths()).toEqual(['/src/tools'])
  })

  it('re-sorts the list from the select', async () => {
    store.repositories = [
      {
        id: 'r1',
        name: 'api',
        remote_url: 'https://github.com/acme/api.git',
        path: '/src/api',
        created_at: '2026-01-01T00:00:00Z'
      },
      { id: 'r2', name: 'tools', remote_url: null, path: '/src/tools', created_at: '2026-01-02T00:00:00Z' }
    ]
    const wrapper = mountView()
    await flushPromises()

    const paths = () => wrapper.findAll('.mono').map((d) => d.text())
    // Name is the default order, and the sort keys are direction-neutral (the
    // toggle carries ascending/descending, not the option names).
    expect(paths()).toEqual(['/src/api', '/src/tools'])
    expect(wrapper.findAll('select[aria-label="Sort repositories"] option').map((o) => o.text())).toEqual([
      'Name',
      'Item count',
      'Date added'
    ])

    await wrapper.get('select[aria-label="Sort repositories"]').setValue('newest')
    expect(paths()).toEqual(['/src/tools', '/src/api'])
  })

  it('toggles the sort direction, resetting it when the order changes', async () => {
    store.repositories = [
      {
        id: 'r1',
        name: 'api',
        remote_url: 'https://github.com/acme/api.git',
        path: '/src/api',
        created_at: '2026-01-01T00:00:00Z'
      },
      { id: 'r2', name: 'tools', remote_url: null, path: '/src/tools', created_at: '2026-01-02T00:00:00Z' }
    ]
    const wrapper = mountView()
    await flushPromises()

    const paths = () => wrapper.findAll('.mono').map((d) => d.text())
    const toggle = () => wrapper.get('button[aria-label="Toggle sort direction"]')

    // Name defaults to ascending.
    expect(toggle().text()).toContain('Asc')
    await toggle().trigger('click')
    expect(paths()).toEqual(['/src/tools', '/src/api'])

    // Item count defaults to descending, so the toggle reset on the switch.
    await wrapper.get('select[aria-label="Sort repositories"]').setValue('items')
    expect(toggle().text()).toContain('Desc')
    expect(paths()).toEqual(['/src/api', '/src/tools'])

    // Ascending puts the item-less repository first.
    await toggle().trigger('click')
    expect(paths()).toEqual(['/src/tools', '/src/api'])
  })

  it('says so when nothing matches the filters', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[aria-label="Filter repositories"]').setValue('nothing')
    expect(wrapper.text()).toContain('No repositories match the filters')
    expect(wrapper.find('.mono').exists()).toBe(false)
  })
})
