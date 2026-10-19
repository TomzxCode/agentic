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
  settingsDiagnostics: vi.fn(),
  reviewsScan: vi.fn(),
  reviewsRunScan: vi.fn(),
  repositoriesUpdate: vi.fn(),
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
      refreshStatus: mocks.settingsRefreshStatus,
      diagnostics: mocks.settingsDiagnostics
    },
    repositories: {
      create: mocks.repositoriesCreate,
      createBulk: mocks.repositoriesCreateBulk,
      update: mocks.repositoriesUpdate,
      remove: mocks.repositoriesRemove
    },
    reviews: { scan: mocks.reviewsScan, runScan: mocks.reviewsRunScan },
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
import { SIDEBAR_NAV_ITEMS, resetSidebarNav } from '../sidebarNav'

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
    mocks.settingsDiagnostics.mockResolvedValue({ checked_at: new Date().toISOString(), dependencies: [] })
  })

  const mountView = () =>
    mount(SettingsView, {
      global: { stubs: { RepositoryGroupsPanel: true, RouterLink: RouterLinkStub } }
    })

  it('shows an icon on every settings nav item', async () => {
    const wrapper = mountView()
    await flushPromises()

    const items = wrapper.findAll('.settings-nav-item')
    expect(items.length).toBe(9)
    for (const item of items) {
      expect(item.find('svg').exists()).toBe(true)
    }
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
          origin: 'manual',
          refreshed_24h: 7
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
    expect(wrapper.text()).toContain('7 refreshed in the last 24h')
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

  it('lists dependencies with presence and versions, and rechecks on demand', async () => {
    mocks.settingsDiagnostics.mockResolvedValue({
      checked_at: new Date().toISOString(),
      ghx_cache: {
        available: true,
        error: null,
        repositories: [
          {
            repository: 'openchamber/openchamber',
            issues: 1854,
            pull_requests: 2409,
            cached_age: '14d',
            status: 'stale'
          },
          { repository: 'tomzx/agents', issues: 2, pull_requests: 3, cached_age: null, status: 'no cache info' }
        ]
      },
      slackx_cache: {
        available: true,
        error: null,
        workspace: 'tomzx',
        db_path: '/home/tomzx/.cache/slackx/tomzx/threads.db',
        channel_count: 12,
        user_count: 6,
        thread_count: 32,
        message_count: 47,
        read_marker_count: 1,
        channels_updated_at: new Date().toISOString(),
        users_updated_at: null,
        threads_updated_at: null
      },
      dependencies: [
        {
          id: 'python',
          name: 'Python',
          command: 'python',
          category: 'runtime',
          required: true,
          purpose: 'Runs the Agentic server.',
          present: true,
          path: '/usr/bin/python3',
          version: '3.12.3'
        },
        {
          id: 'ghx',
          name: 'ghx',
          command: 'ghx',
          category: 'tool',
          required: false,
          purpose: 'Reading GitHub issues and pull requests.',
          present: true,
          path: '/usr/bin/ghx',
          version: 'ghx version 1.2.3'
        },
        {
          id: 'slackx',
          name: 'slackx',
          command: 'slackx',
          category: 'tool',
          required: false,
          purpose: 'Importing Slack threads and refreshing their content.',
          present: false,
          path: null,
          version: null
        },
        {
          id: 'harness:opencode',
          name: 'OpenCode',
          command: 'opencode',
          category: 'harness',
          required: false,
          purpose: 'OpenCode ACP.',
          present: true,
          path: '/usr/bin/opencode',
          version: 'opencode v2.0.30'
        }
      ]
    })
    const wrapper = mountView()
    await flushPromises()

    // The probes spawn each command server side, so they wait for the section.
    expect(mocks.settingsDiagnostics).not.toHaveBeenCalled()

    const nav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Diagnostics')
    await nav.trigger('click')
    await flushPromises()

    expect(mocks.settingsDiagnostics).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Runtime')
    expect(wrapper.text()).toContain('Helper tools')
    expect(wrapper.text()).toContain('Agent harnesses')
    expect(wrapper.text()).toContain('ghx version 1.2.3')
    expect(wrapper.text()).toContain('/usr/bin/ghx')
    expect(wrapper.text()).toContain('missing')
    expect(wrapper.text()).toContain('3 of 4 available')
    expect(wrapper.text()).toContain('1 missing')

    // The ghx cache dump, parsed from its table output.
    expect(wrapper.text()).toContain('ghx cache')
    expect(wrapper.text()).toContain('2 repositories')
    expect(wrapper.text()).toContain('4268 issues and PRs')
    expect(wrapper.text()).toContain('1 stale')
    expect(wrapper.get('.diagnostics-table').text()).toContain('openchamber/openchamber')
    expect(wrapper.get('.diagnostics-table').text()).toContain('1854')

    // The slackx cache counts, read from its JSON status.
    expect(wrapper.text()).toContain('slackx cache')
    expect(wrapper.text()).toContain('workspace tomzx')
    expect(wrapper.text()).toContain('/home/tomzx/.cache/slackx/tomzx/threads.db')
    expect(wrapper.text()).toContain('Read markers')

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Recheck')
      .trigger('click')
    await flushPromises()
    expect(mocks.settingsDiagnostics).toHaveBeenCalledTimes(2)
  })

  it('configures the review scan and the repositories it covers', async () => {
    store.repositories = [
      { id: 'r1', name: 'agentic', remote_url: 'git@github.com:TomzxCode/agentic.git', review_scan: 'default' },
      {
        id: 'r2',
        name: 'openchamber',
        remote_url: 'https://github.com/openchamber/openchamber',
        review_scan: 'exclude'
      }
    ]
    mocks.settingsGet.mockResolvedValue({ defaults: { review_scan_interval: '1h' }, overrides: {} })
    mocks.reviewsScan.mockResolvedValue({
      interval: '1h',
      enabled: true,
      default: 'include',
      stored: 4,
      found: 9,
      kept: 4,
      last_run_at: new Date().toISOString(),
      origin: 'background'
    })
    mocks.settingsUpdate.mockResolvedValue({})
    mocks.repositoriesUpdate.mockResolvedValue({ id: 'r2', review_scan: 'include' })

    const wrapper = mountView()
    await flushPromises()
    const nav = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Review requests')
    await nav.trigger('click')
    await flushPromises()

    expect(mocks.reviewsScan).toHaveBeenCalled()
    expect(wrapper.text()).toContain('9 found, 4 kept')

    // The cadence saves on blur.
    await wrapper.get('input[placeholder="1h"]').setValue('30m')
    await wrapper.get('input[placeholder="1h"]').trigger('blur')
    await flushPromises()
    expect(mocks.settingsUpdate).toHaveBeenCalledWith({ review_scan_interval: '30m' })

    // Each row is identified by its owner/repo (not its registered name) and the
    // list is alphabetical, so openchamber/openchamber comes before TomzxCode/agentic.
    const selects = wrapper.findAll('select[aria-label^="Review scan for"]')
    expect(selects.map((select) => select.attributes('aria-label'))).toEqual([
      'Review scan for openchamber/openchamber',
      'Review scan for TomzxCode/agentic'
    ])
    expect(wrapper.text()).toContain('agentic')
    await selects[1].setValue('include')
    await flushPromises()
    expect(mocks.repositoriesUpdate).toHaveBeenCalledWith('r1', { review_scan: 'include' })
    expect(store.repositories.find((r) => r.id === 'r1').review_scan).toBe('include')

    // Scan now runs it immediately and reports the outcome.
    mocks.reviewsRunScan.mockResolvedValue({ enabled: true, stored: 5, found: 12, kept: 5 })
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Scan now')
      .trigger('click')
    await flushPromises()
    expect(mocks.reviewsRunScan).toHaveBeenCalled()
    expect(store.toast.message).toBe('Scan found 12, kept 5')
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

  it('saves a harness model when the field loses focus', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    const input = wrapper.get('input[placeholder="model, e.g. provider/model (empty uses the harness default)"]')
    await input.setValue('zai-coding-plan/glm-5.3')
    await input.trigger('blur')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', { model: 'zai-coding-plan/glm-5.3' })
    expect(store.toast).toBeNull()
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

  it('saves a resume command when the field loses focus', async () => {
    mocks.harnessesUpdate.mockResolvedValue({})

    const wrapper = mountView()
    await flushPromises()
    const input = wrapper.get('input[placeholder="opencode --session {session}"]')
    await input.setValue('opencode2 --session {session}')
    await input.trigger('blur')
    await flushPromises()
    expect(mocks.harnessesUpdate).toHaveBeenCalledWith('opencode', {
      resume_command: 'opencode2 --session {session}'
    })
    expect(wrapper.text()).toContain('saved')
  })

  it('does not save a harness field that did not change', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[placeholder="opencode --session {session}"]').trigger('blur')
    await wrapper
      .get('input[placeholder="model, e.g. provider/model (empty uses the harness default)"]')
      .trigger('blur')
    await flushPromises()
    expect(mocks.harnessesUpdate).not.toHaveBeenCalled()
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

  it('configures the sidebar nav, saving the choice on the device', async () => {
    localStorage.clear()
    resetSidebarNav()
    const wrapper = mountView()
    await flushPromises()

    const section = wrapper.findAll('.settings-nav-item').find((b) => b.text() === 'Sidebar')
    await section.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.nav-config-row').length).toBe(SIDEBAR_NAV_ITEMS.length)

    // Hide Gantt.
    const gantt = wrapper.findAll('.nav-config-row').find((row) => row.text().includes('Gantt'))
    await gantt.get('input[type="checkbox"]').setValue(false)
    expect(JSON.parse(localStorage.getItem('agentic.sidebarNav')).hidden).toEqual(['gantt'])

    // Drag Tasks down two slots.
    const rows = wrapper.findAll('.nav-config-row')
    rows.forEach((row, index) => {
      row.element.getBoundingClientRect = () => ({ top: index * 40, bottom: index * 40 + 40, height: 40 })
    })
    const tasks = rows.find((row) => row.text().includes('Tasks'))
    const pointer = (type, y) => {
      const event = new Event(type, { bubbles: true, cancelable: true })
      event.clientY = y
      event.button = 0
      return event
    }
    tasks.get('.nav-config-grip').element.dispatchEvent(pointer('pointerdown', 20))
    window.dispatchEvent(pointer('pointermove', 95))
    window.dispatchEvent(pointer('pointerup', 95))
    expect(JSON.parse(localStorage.getItem('agentic.sidebarNav')).order[2]).toBe('tasks')

    // Reset restores the default order and visibility.
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Reset to default')
      .trigger('click')
    expect(JSON.parse(localStorage.getItem('agentic.sidebarNav'))).toEqual({
      order: SIDEBAR_NAV_ITEMS.map((item) => item.id),
      hidden: []
    })
  })

  it('reorders the sidebar nav from the keyboard on the grip', async () => {
    localStorage.clear()
    resetSidebarNav()
    const wrapper = mountView()
    await flushPromises()

    const tasks = wrapper.findAll('.nav-config-row').find((row) => row.text().includes('Tasks'))
    await tasks.get('.nav-config-grip').trigger('keydown', { key: 'ArrowDown' })
    expect(JSON.parse(localStorage.getItem('agentic.sidebarNav')).order[1]).toBe('tasks')
  })
})
