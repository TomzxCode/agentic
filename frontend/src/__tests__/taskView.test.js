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
  githubCreateIssue: vi.fn(),
  tasksCreate: vi.fn(),
  changesList: vi.fn(),
  changesCreate: vi.fn(),
  tasksGet: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksRemove: vi.fn(),
  tasksAssociate: vi.fn(),
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
    github: { repository: mocks.githubRepository, createIssue: mocks.githubCreateIssue },
    changes: { list: mocks.changesList, create: mocks.changesCreate },
    tasks: {
      get: mocks.tasksGet,
      update: mocks.tasksUpdate,
      remove: mocks.tasksRemove,
      create: mocks.tasksCreate,
      associate: mocks.tasksAssociate
    }
  },
  openTaskStream: mocks.openTaskStream
}))

import TaskView from '../views/TaskView.vue'
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

  it('puts the description and its context side by side above the panels', async () => {
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
    const band = wrapper.get('.grid-even')
    expect(band.element.children).toHaveLength(2)
    expect(band.findAll('.et')).toHaveLength(1)
    expect(band.get('.context').exists()).toBe(true)
    // Notes opens the left column of the panels below the band.
    expect(wrapper.get('.grid-2').element.children[0].firstElementChild.classList.contains('notes')).toBe(true)
  })

  it('puts the properties strip above the description and the description band above the panels', async () => {
    const wrapper = mountView()
    await flushPromises()
    const properties = wrapper.get('.properties').element
    const band = wrapper.get('.grid-even').element
    const panels = wrapper.get('.grid-2').element
    expect(properties.nextElementSibling).toBe(band)
    expect(band.nextElementSibling).toBe(panels)
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
    // panel head's button opens the editor on the raw Markdown.
    await description.trigger('click')
    expect(description.find('textarea').exists()).toBe(false)

    const editButton = wrapper.get('button[aria-label="Edit the description"]')
    await editButton.trigger('click')
    // The head hides its action while the field is open.
    expect(wrapper.find('button[aria-label="Edit the description"]').exists()).toBe(false)
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

  const githubRepo = { id: 'r1', name: 'api', remote_url: 'https://github.com/acme/api.git' }

  it('creates a GitHub issue straight away when the task names one repository', async () => {
    store.repositories = [githubRepo]
    mocks.tasksGet.mockResolvedValue({ ...task, repository_ids: ['r1'] })
    mocks.githubCreateIssue.mockResolvedValue({ number: 12, url: 'https://github.com/acme/api/issues/12' })
    mocks.tasksAssociate.mockResolvedValue({})

    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Create GitHub issue'))
      .trigger('click')
    await flushPromises()

    expect(mocks.githubCreateIssue).toHaveBeenCalledWith({
      repository_id: 'r1',
      title: 'My task',
      body: 'desc'
    })
    expect(mocks.tasksAssociate).toHaveBeenCalledWith('t1', {
      item: { url: 'https://github.com/acme/api/issues/12' }
    })
    expect(store.toast.message).toBe('Created GitHub issue #12')
  })

  it('asks which repository to use when none is linked', async () => {
    store.repositories = [githubRepo, { id: 'r2', name: 'tools', remote_url: 'https://github.com/acme/tools.git' }]
    mocks.githubCreateIssue.mockResolvedValue({ number: 3, url: 'https://github.com/acme/tools/issues/3' })
    mocks.tasksAssociate.mockResolvedValue({})

    // The real picker, so the choice can be made through the same dropdown the
    // repository property uses.
    const wrapper = mount(TaskView, {
      props: { id: 't1' },
      global: { stubs: { ...stubs, SearchSelect: false } }
    })
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Create GitHub issue'))
      .trigger('click')
    await flushPromises()

    // Nothing is created until a repository is chosen.
    expect(mocks.githubCreateIssue).not.toHaveBeenCalled()
    const pick = wrapper.get('.create-issue-pick')
    await pick.get('.ss-trigger').trigger('click')
    await flushPromises()
    await pick
      .findAll('.ss-option')
      .find((o) => o.text() === 'tools')
      .trigger('click')
    await flushPromises()

    expect(mocks.githubCreateIssue).toHaveBeenCalledWith({
      repository_id: 'r2',
      title: 'My task',
      body: 'desc'
    })
  })

  it('offers only the task repositories when it links several', async () => {
    store.repositories = [
      githubRepo,
      { id: 'r2', name: 'tools', remote_url: 'https://github.com/acme/tools.git' },
      { id: 'r3', name: 'other', remote_url: 'https://github.com/acme/other.git' }
    ]
    mocks.tasksGet.mockResolvedValue({ ...task, repository_ids: ['r1', 'r2'] })

    const wrapper = mount(TaskView, {
      props: { id: 't1' },
      global: { stubs: { ...stubs, SearchSelect: false } }
    })
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Create GitHub issue'))
      .trigger('click')
    await flushPromises()

    const pick = wrapper.get('.create-issue-pick')
    await pick.get('.ss-trigger').trigger('click')
    await flushPromises()
    expect(pick.findAll('.ss-option-label').map((o) => o.text())).toEqual(['api', 'tools'])
  })
})
