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

import SettingsView from '../views/SettingsView.vue'
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
      .get('input[placeholder="model, e.g. provider/model (empty uses the harness default)"]')
      .setValue('zai-coding-plan/glm-5.3')
    await wrapper
      .findAll('button')
      .filter((b) => b.text() === 'Save')[1]
      .trigger('click')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', { model: 'zai-coding-plan/glm-5.3' })
    expect(store.toast.message).toBe('Model saved')
  })

  it('shows the model the harness config file names while the field is blank', async () => {
    mocks.harnessesFull.mockResolvedValue([
      {
        id: 'opencode2',
        name: 'OpenCode v2',
        command: 'opencode2',
        model: null,
        default_model: 'zai-coding-plan/glm-5.3-flash'
      }
    ])
    const wrapper = mountView()
    await flushPromises()
    const input = wrapper.get('input[placeholder="zai-coding-plan/glm-5.3-flash (harness default)"]')
    expect(input.element.value).toBe('')
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
