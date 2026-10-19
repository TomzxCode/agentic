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

import RepositoryDetailView from '../views/RepositoryDetailView.vue'
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

  // AG Grid applies a changed rowData asynchronously, so a test that narrows
  // the rows (a filter or a search) lets the grid settle before asserting.
  const settleGrid = async () => {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 20))
  }

  // The grid renders rows and their cells asynchronously; mount through these
  // helpers so a test asserts only once the grid has settled.
  const mountRepoView = async () => {
    const wrapper = mountView()
    await settleGrid()
    return wrapper
  }
  const mountRepoLinked = async () => {
    const wrapper = mountLinked()
    await settleGrid()
    return wrapper
  }

  it('offers the column chooser once the grid is ready', async () => {
    const wrapper = await mountRepoView()
    expect(wrapper.find('.col-chooser').exists()).toBe(true)
  })

  it('shows the header right away and a spinner until the listing arrives', async () => {
    // The listing is the slow part; hold it pending to see the loading state.
    mocks.githubRepository.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountRepoView()
    await flushPromises()

    // The top section is up while the listing loads.
    expect(wrapper.find('h1').text()).toBe('api')
    expect(wrapper.find('[aria-label="Refresh all issues and pull requests"]').exists()).toBe(true)
    // One spinner where the grid will land, and no grid yet.
    expect(wrapper.findAll('.spinner')).toHaveLength(1)
    expect(wrapper.find('.repo-grid').exists()).toBe(false)
    // A half-loaded page (no listing yet) does not flash the empty state.
    expect(wrapper.text()).not.toContain('No issues or pull requests')
    wrapper.unmount()
  })

  it('lists issues and PRs in the grid', async () => {
    const wrapper = await mountRepoView()
    await flushPromises()

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).toContain('Merged PR')
    // Filtering is at the column level, opened from each header's filter button.
    expect(wrapper.find('.ag-header-cell-filter-button').exists()).toBe(true)
    // The rows are linked to a task, whose status the Task status column shows.
    expect(wrapper.get('.ag-cell[col-id="taskStatus"]').text()).toContain('Open')
  })

  it('shows each item state as a badge', async () => {
    const wrapper = await mountRepoView()
    await settleGrid()

    // One combined table, newest number first, so issues and PRs interleave.
    const badges = wrapper.findAll('.badge.st-open, .badge.st-draft, .badge.st-merged, .badge.st-closed')
    expect(badges.map((b) => b.text())).toEqual(['Merged', 'Draft', 'Open', 'Closed', 'Open'])
    expect(badges.map((b) => b.classes().find((c) => c.startsWith('st-')))).toEqual([
      'st-merged',
      'st-draft',
      'st-open',
      'st-closed',
      'st-open'
    ])
  })

  it('omits the state badge when no state is stored', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'Stateless issue', {})]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.text()).toContain('Stateless issue')
    expect(wrapper.find('.badge.st-open').exists()).toBe(false)
  })

  it('shows the author of each item', async () => {
    store.items = [
      ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN', author: 'alice' }),
      ghItem('i2', 'pr', 2, 'Merged PR', { state: 'MERGED', author: 'bob' })
    ]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.text()).toContain('@alice')
    expect(wrapper.text()).toContain('@bob')
  })

  it('omits the author when none is stored', async () => {
    store.items = [ghItem('i1', 'issue', 1, 'No author', { state: 'OPEN' })]
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoLinked()
    await flushPromises()

    const row = wrapper.get('.change-line')
    expect(row.get('.badge').text()).toBe('accepted')
    expect(row.get('.badge').classes()).toContain('ok')
    expect(row.get('a[href="/task/t1"]').text()).toBe('Landed change')
  })

  it('shows no change rows when nothing references a pull request', async () => {
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.find('.change-line').exists()).toBe(false)
  })

  it('offers to record a change for a merged PR with a single task', async () => {
    const wrapper = await mountRepoView()
    await flushPromises()
    // Only the merged PR (i5) gets a button; open and draft PRs and issues do not.
    expect(wrapper.findAll('button[title="Record a change for this PR"]')).toHaveLength(1)
  })

  it('hides the record button for a merged PR someone else authored', async () => {
    store.settings = { github_login: 'me' }
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'someone' })]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('offers the record button when the author matches the configured login', async () => {
    store.settings = { github_login: 'me' }
    // Case-insensitive: GitHub logins differ in case.
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'Me' })]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(true)
  })

  it('offers the record button when no login is known', async () => {
    store.settings = {}
    store.items = [ghItem('i5', 'pr', 5, 'Merged PR', { state: 'MERGED', author: 'someone' })]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(true)
  })

  it('hides the record button for an open PR', async () => {
    store.items = [ghItem('i3', 'pr', 3, 'Open PR', { state: 'OPEN' })]
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('hides the record button when a PR has more than one task', async () => {
    store.tasks = [
      { id: 't1', title: 'Task One', status: 'open' },
      { id: 't2', title: 'Task Two', status: 'open' }
    ]
    store.items = [{ ...ghItem('i5', 'pr', 5, 'Shared PR', { state: 'MERGED' }), task_ids: ['t1', 't2'] }]
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoLinked()
    await flushPromises()
    expect(wrapper.get('a[href="/person/p1"]').text()).toBe('@alice')
  })

  it('links the author to the prefilled creation page when no person carries the login', async () => {
    store.people = [{ id: 'p1', name: 'Alice', aliases: ['alice'] }]
    store.items = [ghItem('i1', 'issue', 1, 'Open issue', { state: 'OPEN', author: 'ghost' })]
    const wrapper = await mountRepoLinked()
    await flushPromises()
    expect(wrapper.text()).toContain('@ghost')
    const link = wrapper.get('a[href="/person/new?name=ghost&alias=ghost"]')
    expect(link.text()).toBe('@ghost')
    expect(link.classes()).toContain('faint')
  })

  it('refreshes the repository listing from GitHub', async () => {
    mocks.githubRepository.mockResolvedValue({
      items: [
        { number: 1, kind: 'issue', title: 'Open issue', url: 'https://github.com/acme/api/issues/1', state: 'OPEN' },
        { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
      ],
      failed: []
    })
    const wrapper = await mountRepoView()
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
    // The backend syncs the linked items, so the view reloads them too.
    expect(store.loadItems).toHaveBeenCalledTimes(2)
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
    await flushPromises()

    expect(wrapper.text()).toContain('Unlinked PR')
    expect(wrapper.text()).toContain('Could not load the issues from GitHub')
  })

  it('refreshes only the issues and PRs associated to tasks', async () => {
    mocks.itemsRefresh.mockResolvedValue({})
    const wrapper = await mountRepoView()
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
    const wrapper = await mountRepoView()
    await flushPromises()

    await wrapper.get('[aria-label="Refresh issues and pull requests associated to tasks"]').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).toHaveBeenCalledTimes(5)
    expect(store.toast.message).toBe('Refreshed 4 of 5 linked items; 1 failed')
    expect(store.toast.isError).toBe(true)
  })

  it('disables the linked refresh when nothing is associated to a task', async () => {
    store.items = []
    const wrapper = await mountRepoView()
    await flushPromises()
    expect(
      wrapper.get('[aria-label="Refresh issues and pull requests associated to tasks"]').attributes('disabled')
    ).toBeDefined()
    // The whole-repository refresh stays available: the remote is listable.
    expect(wrapper.get('[aria-label="Refresh all issues and pull requests"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps the stored items when the GitHub listing fails', async () => {
    mocks.githubRepository.mockRejectedValue(new Error('ghx down'))
    const wrapper = await mountRepoView()
    await flushPromises()

    expect(wrapper.text()).toContain('Open issue')
    expect(wrapper.text()).toContain('Could not list this repository from GitHub')
  })
})
