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

import RepositoriesView from '../views/RepositoriesView.vue'
import { store } from '../store'
import { AgGridVue } from 'ag-grid-vue3'

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

  // AG Grid renders its rows and cells asynchronously.
  const settle = async () => {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 20))
  }

  const RepoLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

  const mountView = async () => {
    const wrapper = mount(RepositoriesView, { global: { stubs: { RouterLink: RepoLinkStub } } })
    await settle()
    return wrapper
  }

  it("breaks each repository's associated items down by state", async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('1 open · 1 draft · 1 merged')
  })

  it('omits the state line when no item carries a state', async () => {
    store.items = [ghItem('i1', 'issue', 1, {})]
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('api')
    expect(wrapper.text()).not.toContain('open')
  })

  it('offers the column chooser once the grid is ready', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.col-chooser').exists()).toBe(true)
  })

  it('lists the repositories in the grid and links each name', async () => {
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
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('/src/api')
    expect(wrapper.text()).toContain('/src/tools')
    expect(wrapper.get('a[href="/repositories/r1"]').text()).toBe('api')
  })

  it('filters the rows through the grid, and reports how much is shown', async () => {
    store.repositories = [
      { id: 'r1', name: 'api', remote_url: 'https://github.com/acme/api.git', path: '/src/api' },
      { id: 'r2', name: 'tools', remote_url: null, path: '/src/tools' }
    ]
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('/src/api')
    expect(wrapper.text()).toContain('/src/tools')
    expect(wrapper.text()).toContain('2 of 2 repositories')

    const api = wrapper.getComponent(AgGridVue).vm.api
    await api.setFilterModel({ name: { filterType: 'text', type: 'contains', filter: 'tools' } })
    await settle()

    expect(wrapper.text()).toContain('/src/tools')
    expect(wrapper.text()).not.toContain('/src/api')
    expect(wrapper.text()).toContain('1 of 2 repositories')
  })
})
