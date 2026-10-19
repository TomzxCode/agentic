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
  harnessModels: vi.fn(),
  openRunStream: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    groups: { create: mocks.groupsCreate, update: mocks.groupsUpdate, remove: mocks.groupsRemove },
    fs: { list: mocks.fsList },
    harnesses: { models: mocks.harnessModels },
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
  const task = {
    id: 't1',
    title: 'Test task',
    status: 'open',
    worktrees: [{ id: 'w1', status: 'active', branch: 'b', path: '/w' }]
  }
  const mountPanel = () =>
    mount(AgentPanel, {
      props: { task, harnesses: [] },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })

  beforeEach(() => {
    mocks.runsList.mockResolvedValue([])
    mocks.harnessModels.mockResolvedValue({ harness_id: 'opencode2', models: [], live: false })
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

  it('shows the harness model on the model picker, not on the harness picker', async () => {
    const wrapper = mount(AgentPanel, {
      props: {
        task,
        harnesses: [{ id: 'opencode2', name: 'OpenCode v2', available: true, is_default: true, model: 'zai/glm' }]
      },
      global: { stubs: { SessionLinks: true } }
    })
    await flushPromises()
    // The harness picker names harnesses; the model picker names the model.
    expect(wrapper.get('.ss-label').text()).toContain('OpenCode v2')
    expect(wrapper.get('.ss-label').text()).not.toContain('zai/glm')
    expect(wrapper.get('.model-select .ss-label').text()).toContain('zai/glm')
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
    expect(wrapper.get('.model-select .ss-label').text()).toContain('zai-coding-plan/glm-5.3-flash')
  })

  it('lists the models the harness reports and sends the chosen one with the run', async () => {
    mocks.harnessModels.mockResolvedValue({
      harness_id: 'opencode2',
      models: [
        { value: 'zai/glm-5.3', name: 'Zai GLM 5.3' },
        { value: 'opencode/big-pickle', name: 'Big Pickle' }
      ],
      current: 'zai/glm-5.3',
      live: true
    })
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const wrapper = mount(AgentPanel, {
      props: {
        task,
        harnesses: [{ id: 'opencode2', name: 'OpenCode v2', available: true, is_default: true }]
      },
      global: { stubs: { SessionLinks: true } }
    })
    await flushPromises()
    // The list comes from the API for the harness the run will use.
    expect(mocks.harnessModels).toHaveBeenCalledWith('opencode2')

    const picker = wrapper.getComponent('.model-select')
    expect(picker.props('options').map((o) => o.value)).toEqual(['', 'zai/glm-5.3', 'opencode/big-pickle'])

    picker.vm.$emit('update:modelValue', 'opencode/big-pickle')
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    const body = mocks.runsCreate.mock.calls[0][1]
    expect(body.model).toBe('opencode/big-pickle')
    expect(body.prompt.startsWith('do work')).toBe(true)
  })

  it('reloads the model list when the harness changes', async () => {
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
    expect(mocks.harnessModels).toHaveBeenCalledWith('opencode2')

    wrapper.getComponent('.w-170').vm.$emit('update:modelValue', 'pi')
    await flushPromises()
    expect(mocks.harnessModels).toHaveBeenCalledWith('pi')
  })

  it('loads the model list when the harness list arrives after mount', async () => {
    const wrapper = mount(AgentPanel, {
      props: { task, harnesses: [] },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })
    await flushPromises()
    expect(mocks.harnessModels).not.toHaveBeenCalled()

    await wrapper.setProps({
      harnesses: [{ id: 'opencode2', name: 'OpenCode v2', available: true, is_default: true }]
    })
    await flushPromises()
    expect(mocks.harnessModels).toHaveBeenCalledWith('opencode2')
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
    const sent = mocks.runsCreate.mock.calls[0][1].prompt
    expect(sent.startsWith('do work')).toBe(true)
    expect(sent).toContain('# Context')
    expect(sent).toContain('- Task: Test task (t1)')
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

  it('adopts a run started elsewhere and follows it from queued', async () => {
    mocks.runsList.mockResolvedValue([])
    mocks.openRunStream.mockReturnValue(vi.fn())
    const wrapper = mountPanel()
    await flushPromises()

    // The findings selector in the PR view creates the run and hands it over.
    wrapper.vm.adopt({ id: 'r5', status: 'queued', kind: 'chat', prompt: 'sent findings' })
    await flushPromises()

    // A queued run is followed too, so its first event opens the transcript.
    expect(mocks.openRunStream).toHaveBeenCalledWith('r5', expect.any(Function))
    expect(mocks.runsList).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.transcript-head').text()).toContain('queued')
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
        model_name: 'GLM 5.3',
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

    // The history row names the model the harness called it, keeping the id it
    // selects with as the row's tooltip.
    expect(wrapper.text()).toContain('GLM 5.3')
    expect(wrapper.text()).not.toContain('zai-coding-plan/glm-5.3')
    const named = wrapper.findAll('.faint.mono').find((el) => el.attributes('title') === 'zai-coding-plan/glm-5.3')
    expect(named.text()).toBe('GLM 5.3')

    // A live run has no stored model yet, so the ACP-reported one heads the
    // transcript as soon as the harness says what it selected.
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    onEvent({ type: 'model', text: 'GLM 5.2' })
    await flushPromises()

    expect(wrapper.get('.transcript-head').text()).toContain('GLM 5.2')
  })

  it('heads a replayed transcript with the model name the run stored', async () => {
    mocks.runsList.mockResolvedValue([
      {
        id: 'r9',
        status: 'succeeded',
        kind: 'chat',
        prompt: 'old',
        model: 'google/gemini-3-pro',
        model_name: 'Gemini 3 Pro',
        created_at: new Date().toISOString()
      }
    ])
    mocks.runsGet.mockResolvedValue({
      id: 'r9',
      status: 'succeeded',
      kind: 'chat',
      prompt: 'old',
      model: 'google/gemini-3-pro',
      model_name: 'Gemini 3 Pro',
      links: []
    })
    mocks.runsEvents.mockResolvedValue([{ type: 'message', text: 'old transcript' }])

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('.item').trigger('click')
    await flushPromises()
    expect(wrapper.get('.transcript-head').text()).toContain('Gemini 3 Pro')
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

  it('attaches the linked item the view is about to a typed prompt', async () => {
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const task = {
      id: 't1',
      title: 'Fix login',
      status: 'open',
      associations: [
        {
          id: 'a1',
          item: {
            id: 'i1',
            source: 'github',
            kind: 'issue',
            title: 'Login fails',
            url: 'https://github.com/acme/api/issues/7',
            metadata_json: { owner: 'acme', repo: 'api', number: 7 }
          }
        }
      ]
    }
    const wrapper = mount(AgentPanel, {
      props: { task, harnesses: [], contextKind: 'issue' },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })
    await flushPromises()
    await wrapper.get('textarea').setValue('why does {number} fail?')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    const prompt = mocks.runsCreate.mock.calls[0][1].prompt
    // Task and item variables are filled, then the view context is appended.
    expect(prompt.startsWith('why does 7 fail?')).toBe(true)
    expect(prompt).toContain('# Context')
    expect(prompt).toContain('- Issue: https://github.com/acme/api/issues/7 (Login fails)')
  })

  it('gives each linked item a short id when a task links several', async () => {
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const task = {
      id: 't1',
      title: 'Compare',
      status: 'open',
      associations: [
        {
          id: 'a1',
          item: {
            id: 'i1',
            source: 'github',
            kind: 'issue',
            title: 'First',
            url: 'https://github.com/acme/api/issues/1',
            metadata_json: { owner: 'acme', repo: 'api', number: 1 }
          }
        },
        {
          id: 'a2',
          item: {
            id: 'i2',
            source: 'github',
            kind: 'issue',
            title: 'Second',
            url: 'https://github.com/acme/api/issues/2',
            metadata_json: { owner: 'acme', repo: 'api', number: 2 }
          }
        }
      ]
    }
    const wrapper = mount(AgentPanel, {
      props: { task, harnesses: [], contextKind: 'issue' },
      global: { stubs: { SearchSelect: true, SessionLinks: true } }
    })
    await flushPromises()

    // The per-item groups replace the ambiguous single-item group.
    expect(wrapper.findAll('button.prompt-var').some((b) => b.text() === 'item_url')).toBe(false)
    expect(wrapper.findAll('button.prompt-var').some((b) => b.text() === 'li.a.item_url')).toBe(true)
    expect(wrapper.text()).toContain('acme/api#1 · First')
    expect(wrapper.text()).toContain('acme/api#2 · Second')

    await wrapper.get('textarea').setValue('compare {li.a.item_url} and {li.b.item_url}')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    const prompt = mocks.runsCreate.mock.calls[0][1].prompt
    expect(
      prompt.startsWith('compare https://github.com/acme/api/issues/1 and https://github.com/acme/api/issues/2')
    ).toBe(true)
  })

  it('leaves a command prompt as-is, without attaching context', async () => {
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('textarea').setValue('$some-skill 1 acme/api')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.runsCreate).toHaveBeenCalledWith('t1', { prompt: '$some-skill 1 acme/api' })
  })

  it('submits the prompt alone when attaching context is turned off', async () => {
    mocks.runsCreate.mockResolvedValue({ id: 'r1', status: 'running', kind: 'chat', links: [] })
    mocks.openRunStream.mockReturnValue(vi.fn())

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(false)
    await wrapper.get('textarea').setValue('do work')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.runsCreate).toHaveBeenCalledWith('t1', { prompt: 'do work' })
  })

  it('inserts a variable token when its chip is clicked', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const chip = wrapper.findAll('button.prompt-var').find((b) => b.text() === 'title')
    expect(chip).toBeTruthy()
    await chip.trigger('click')
    expect(wrapper.get('textarea').element.value).toBe('{title}')
  })
})
