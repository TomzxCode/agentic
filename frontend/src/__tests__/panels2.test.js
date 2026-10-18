import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  groupsCreate: vi.fn(),
  groupsUpdate: vi.fn(),
  groupsRemove: vi.fn(),
  fsList: vi.fn(),
  runsList: vi.fn(),
  runsCreate: vi.fn(),
  runsGet: vi.fn(),
  runsEvents: vi.fn(),
  runsCancel: vi.fn(),
  openRunStream: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    groups: { create: mocks.groupsCreate, update: mocks.groupsUpdate, remove: mocks.groupsRemove },
    fs: { list: mocks.fsList },
    runs: {
      list: mocks.runsList,
      create: mocks.runsCreate,
      get: mocks.runsGet,
      events: mocks.runsEvents,
      cancel: mocks.runsCancel
    }
  },
  openRunStream: mocks.openRunStream
}))

import AgentPanel from '../components/AgentPanel.vue'
import DirectoryPicker from '../components/DirectoryPicker.vue'
import RepositoryGroupsPanel from '../components/RepositoryGroupsPanel.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('RepositoryGroupsPanel', () => {
  beforeEach(() => {
    store.repositories = [{ id: 'r1', name: 'Repo One' }]
    store.groups = [{ id: 'g1', name: 'Core', description: 'd', repository_ids: ['r1'] }]
    vi.spyOn(store, 'loadGroups').mockResolvedValue()
  })

  const mountPanel = () => mount(RepositoryGroupsPanel, { global: { stubs: { RepositorySelect: true } } })

  it('renders groups with resolved repository names', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('Core')
    expect(wrapper.text()).toContain('Repo One')
  })

  it('disables add until a name exists, then creates', async () => {
    mocks.groupsCreate.mockResolvedValue({})
    const wrapper = mountPanel()
    const add = wrapper.get('.btn.primary')
    expect(add.attributes('disabled')).toBeDefined()

    await wrapper.get('input.input').setValue('New group')
    await add.trigger('click')
    await flushPromises()
    expect(mocks.groupsCreate).toHaveBeenCalledWith(expect.objectContaining({ name: 'New group' }))
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('edits and saves a group', async () => {
    mocks.groupsUpdate.mockResolvedValue({})
    const wrapper = mountPanel()
    await wrapper.get('button.btn.sm').trigger('click')
    await wrapper.get('input.input').setValue('Renamed')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.groupsUpdate).toHaveBeenCalledWith('g1', expect.objectContaining({ name: 'Renamed' }))
  })

  it('removes a group when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.groupsRemove.mockResolvedValue({})
    const wrapper = mountPanel()
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.groupsRemove).toHaveBeenCalledWith('g1')
  })
})

describe('DirectoryPicker', () => {
  beforeEach(() => {
    mocks.fsList.mockResolvedValue({
      path: '/root',
      parent: null,
      is_git: true,
      entries: [
        { name: 'a', path: '/root/a', is_git: true },
        { name: 'b', path: '/root/b', is_git: false }
      ]
    })
  })

  const button = (wrapper, label) => wrapper.findAll('button').find((b) => b.text() === label)

  it('loads the listing and marks already-added folders', async () => {
    const wrapper = mount(DirectoryPicker, { props: { existing: ['/root/b'] } })
    await flushPromises()
    expect(mocks.fsList).toHaveBeenCalledWith(undefined, false)
    expect(wrapper.findAll('.picker-row')).toHaveLength(2)
    expect(wrapper.findAll('.picker-row input[type=checkbox]')[1].attributes('disabled')).toBeDefined()
  })

  it('selects a folder and emits it on add', async () => {
    const wrapper = mount(DirectoryPicker, { props: {} })
    await flushPromises()
    await wrapper.findAll('.picker-row input[type=checkbox]')[0].trigger('change')
    await wrapper.get('.btn.primary').trigger('click')
    expect(wrapper.emitted('add')).toEqual([[['/root/a']]])
  })

  it('navigates, toggles hidden, and submits a manual path', async () => {
    const wrapper = mount(DirectoryPicker, { props: {} })
    await flushPromises()

    await wrapper.get('.picker-name').trigger('click')
    expect(mocks.fsList).toHaveBeenCalledWith('/root/a', false)

    await wrapper.get('input[type=checkbox]').trigger('change')
    await flushPromises()
    expect(mocks.fsList).toHaveBeenCalledWith('/root', true)

    await wrapper.get('input.input').setValue('/manual')
    await button(wrapper, 'Go').trigger('click')
    await flushPromises()
    expect(mocks.fsList).toHaveBeenCalledWith('/manual', true)
  })

  it('shows an error when the listing fails', async () => {
    mocks.fsList.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mount(DirectoryPicker, { props: {} })
    await flushPromises()
    expect(wrapper.text()).toContain('boom')
  })

  it('emits close from the backdrop and the cancel button', async () => {
    const wrapper = mount(DirectoryPicker, { props: {} })
    await flushPromises()
    await wrapper.get('.modal-backdrop').trigger('click')
    await button(wrapper, 'Cancel').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })
})

describe('AgentPanel', () => {
  const task = { id: 't1', worktrees: [{ id: 'w1', status: 'active', branch: 'b', path: '/w' }] }
  const mountPanel = () =>
    mount(AgentPanel, {
      props: { task, harnesses: [] },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })

  beforeEach(() => {
    mocks.runsList.mockResolvedValue([])
  })

  it('loads runs on mount and shows the working directory', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(mocks.runsList).toHaveBeenCalledWith('t1')
    expect(wrapper.text()).toContain('/w')
  })

  it('names the default harness on the default option', async () => {
    const wrapper = mount(AgentPanel, {
      props: {
        task,
        harnesses: [
          { id: 'opencode2', name: 'OpenCode v2', available: true, is_default: true },
          { id: 'pi', name: 'pi', available: true, is_default: false }
        ]
      },
      global: { stubs: { SessionLinks: true } }
    })
    await flushPromises()
    expect(wrapper.get('.ss-label').text()).toContain('OpenCode v2')
  })

  it('shows the harness model alongside its name', async () => {
    const wrapper = mount(AgentPanel, {
      props: {
        task,
        harnesses: [{ id: 'opencode2', name: 'OpenCode v2', available: true, is_default: true, model: 'zai/glm' }]
      },
      global: { stubs: { SessionLinks: true } }
    })
    await flushPromises()
    expect(wrapper.get('.ss-label').text()).toContain('zai/glm')
  })

  it('falls back to the model the harness config file names', async () => {
    const wrapper = mount(AgentPanel, {
      props: {
        task,
        harnesses: [
          {
            id: 'opencode2',
            name: 'OpenCode v2',
            available: true,
            is_default: true,
            model: null,
            default_model: 'zai-coding-plan/glm-5.3-flash'
          }
        ]
      },
      global: { stubs: { SessionLinks: true } }
    })
    await flushPromises()
    expect(wrapper.get('.ss-label').text()).toContain('zai-coding-plan/glm-5.3-flash')
  })

  it('starts a run, streams events into blocks, and finishes', async () => {
    let onEvent
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.runsGet.mockResolvedValue({ id: 'r1', status: 'succeeded', kind: 'chat', links: [] })
    mocks.openRunStream.mockImplementation((id, cb) => {
      onEvent = cb
      return vi.fn()
    })

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.runsCreate).toHaveBeenCalledWith('t1', { prompt: 'do work' })
    expect(mocks.openRunStream).toHaveBeenCalled()

    onEvent({ type: 'message', text: 'hello' })
    onEvent({ type: 'message', text: ' world' })
    onEvent({
      type: 'tool_call',
      text: 'shell',
      data: { toolCallId: 'x', kind: 'execute', rawInput: { cwd: '/w' }, status: 'pending', locations: [] }
    })
    onEvent({
      type: 'tool_update',
      data: { toolCallId: 'x', kind: 'execute', rawInput: { command: 'ls' }, status: 'completed' }
    })
    onEvent({ type: 'plan', data: { entries: [{ content: 'step one' }] } })
    onEvent({ type: 'error', text: 'oops' })
    onEvent({ type: 'info', text: 'noise' })
    await flushPromises()

    expect(wrapper.text()).toContain('hello world')
    expect(wrapper.text()).toContain('ls')
    expect(wrapper.text()).toContain('step one')
    expect(wrapper.text()).toContain('oops')

    onEvent({ type: 'run_finished' })
    await flushPromises()
    expect(mocks.runsGet).toHaveBeenCalledWith('r1')
  })

  it('shows what a tool call touched, which the ACP title alone does not', async () => {
    let onEvent
    mocks.runsCreate.mockResolvedValue({ id: 'r2', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockImplementation((id, cb) => {
      onEvent = cb
      return vi.fn()
    })

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    // Both calls start before either reports, so their updates interleave: each
    // update still lands on the row its toolCallId belongs to.
    onEvent({
      type: 'tool_call',
      text: 'read',
      data: { toolCallId: 'a', kind: 'read', status: 'pending', rawInput: {}, locations: [] }
    })
    onEvent({
      type: 'tool_call',
      text: 'skill',
      data: { toolCallId: 'b', kind: 'other', status: 'pending', rawInput: {}, locations: [] }
    })
    onEvent({
      type: 'tool_update',
      data: { toolCallId: 'b', kind: 'other', status: 'completed', rawInput: { id: 'validate-pr' } }
    })
    // A read names its file only in rawInput, on the call's first update.
    onEvent({
      type: 'tool_update',
      data: {
        toolCallId: 'a',
        kind: 'read',
        status: 'completed',
        rawInput: { path: '/w/src/main.js' },
        locations: [{ path: '/w/src/main.js' }]
      }
    })
    await flushPromises()

    const rows = wrapper.findAll('.ev.tool .body').map((row) => row.text())
    expect(rows).toEqual(['read · completed · src/main.js', 'skill · completed · validate-pr'])
  })

  it('opens a previous run and loads its transcript', async () => {
    mocks.runsList.mockResolvedValue([
      { id: 'r9', status: 'succeeded', kind: 'chat', prompt: 'old prompt', created_at: new Date().toISOString() }
    ])
    mocks.runsGet.mockResolvedValue({ id: 'r9', status: 'succeeded', kind: 'chat', prompt: 'old prompt', links: [] })
    mocks.runsEvents.mockResolvedValue([{ type: 'message', text: 'old transcript' }])

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('.item').trigger('click')
    await flushPromises()
    expect(mocks.runsGet).toHaveBeenCalledWith('r9')
    expect(wrapper.text()).toContain('old transcript')
  })

  it('names the model the run answers with, live and replayed', async () => {
    let onEvent
    mocks.runsList.mockResolvedValue([
      {
        id: 'r8',
        status: 'succeeded',
        kind: 'chat',
        prompt: 'old prompt',
        model: 'zai-coding-plan/glm-5.3',
        created_at: new Date().toISOString()
      }
    ])
    mocks.runsCreate.mockResolvedValue({ id: 'r7', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockImplementation((id, cb) => {
      onEvent = cb
      return vi.fn()
    })

    const wrapper = mountPanel()
    await flushPromises()

    // The history row carries the model the stored run recorded.
    expect(wrapper.text()).toContain('zai-coding-plan/glm-5.3')

    // A live run has no stored model yet, so the ACP-reported one heads the
    // transcript as soon as the harness says what it selected.
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    onEvent({ type: 'model', text: 'opencode/its-own-default' })
    await flushPromises()

    expect(wrapper.get('.transcript-head').text()).toContain('opencode/its-own-default')
  })

  it('cancels the active run', async () => {
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())
    mocks.runsCancel.mockResolvedValue({})

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('textarea').setValue('x')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    const cancel = wrapper.findAll('button').find((b) => b.text().includes('Cancel'))
    await cancel.trigger('click')
    await flushPromises()
    expect(mocks.runsCancel).toHaveBeenCalledWith('r1')
  })

  it('shows a user-defined prompt button and starts the run with its resolved text', async () => {
    store.settings = {
      agent_prompts: JSON.stringify([
        { kind: 'pull_request', label: 'Review PR', template: '$review-pr-full {number} {owner}/{repository}' }
      ])
    }
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const task = {
      id: 't1',
      associations: [
        {
          id: 'a1',
          item: {
            id: 'i1',
            source: 'github',
            kind: 'pull_request',
            metadata_json: { owner: 'acme', repo: 'api', number: 123 }
          }
        }
      ]
    }
    const wrapper = mount(AgentPanel, {
      props: { task, harnesses: [] },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })
    await flushPromises()

    const promptButton = wrapper.findAll('button').find((b) => b.text().includes('Review PR'))
    expect(promptButton).toBeTruthy()
    await promptButton.trigger('click')
    await flushPromises()
    expect(mocks.runsCreate).toHaveBeenCalledWith('t1', { prompt: '$review-pr-full 123 acme/api' })
    store.settings = {}
  })

  it('hides a prompt button when the task has two items of that kind', async () => {
    store.settings = {
      agent_prompts: JSON.stringify([
        { kind: 'issue', label: 'Triage issue', template: '$triage-issue {number} {owner}/{repository}' }
      ])
    }
    const task = {
      id: 't1',
      associations: [
        {
          id: 'a1',
          item: { id: 'i1', source: 'github', kind: 'issue', metadata_json: { owner: 'acme', repo: 'api', number: 1 } }
        },
        {
          id: 'a2',
          item: { id: 'i2', source: 'github', kind: 'issue', metadata_json: { owner: 'acme', repo: 'api', number: 2 } }
        }
      ]
    }
    const wrapper = mount(AgentPanel, {
      props: { task, harnesses: [] },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })
    await flushPromises()
    expect(wrapper.findAll('button').some((b) => b.text().includes('Triage issue'))).toBe(false)
    store.settings = {}
  })
})
