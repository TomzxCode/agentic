import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// WorktreesPanel renders a <router-link>; stub it so mounting does not warn
// about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  taskUpdate: vi.fn(),
  associate: vi.fn(),
  unassociate: vi.fn(),
  itemRefresh: vi.fn(),
  itemUpdate: vi.fn(),
  worktreeCreate: vi.fn(),
  worktreeRemove: vi.fn(),
  refreshContext: vi.fn(),
  refreshSummary: vi.fn(),
  settingsGet: vi.fn(),
  changeCreate: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.taskUpdate, associate: mocks.associate, unassociate: mocks.unassociate },
    items: { refresh: mocks.itemRefresh, update: mocks.itemUpdate },
    worktrees: { create: mocks.worktreeCreate, remove: mocks.worktreeRemove },
    runs: { refreshContext: mocks.refreshContext, refreshSummary: mocks.refreshSummary },
    settings: { get: mocks.settingsGet },
    changes: { create: mocks.changeCreate }
  }
}))

import ContextPanel from '../components/ContextPanel.vue'
import ItemsPanel from '../components/ItemsPanel.vue'
import NotesPanel from '../components/NotesPanel.vue'
import RepositorySelect from '../components/RepositorySelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import WorktreesPanel from '../components/WorktreesPanel.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ContextPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    summary: 'The summary',
    next_steps: [{ text: 'Step A', done: false }],
    context_updated_at: null,
    ...over
  })

  it('renders the summary and toggles a next step', async () => {
    mocks.taskUpdate.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.get('.summary').text()).toBe('The summary')
    expect(wrapper.find('.badge.warn').exists()).toBe(false)

    await wrapper.get('input[type=checkbox]').trigger('change')
    await flushPromises()
    expect(mocks.taskUpdate).toHaveBeenCalledWith('t1', { next_steps: [{ text: 'Step A', done: true }] })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('shows empty states', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: '', next_steps: [] }) } })
    expect(wrapper.text()).toContain('No context yet')
    expect(wrapper.text()).toContain('No next steps defined')
  })

  it('flags a task with no next steps in the header badge', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: 'Has a summary', next_steps: [] }) } })
    expect(wrapper.get('.badge.warn').text()).toBe('no next steps')
    expect(wrapper.get('.context-missing').text()).toContain('No next steps defined')
  })

  it('refreshes with the agent and emits changed', async () => {
    mocks.refreshContext.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    await wrapper.get('.panel-head button').trigger('click')
    await flushPromises()
    expect(mocks.refreshContext).toHaveBeenCalledWith('t1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(store.toast.message).toContain('Agent is reading')
  })

  it('notifies when the refresh fails', async () => {
    mocks.refreshContext.mockRejectedValueOnce(new Error('agent down'))
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    await wrapper.get('.panel-head button').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'agent down', isError: true })
  })

  it('offers to name and summarize a task with a Slack thread', async () => {
    mocks.refreshSummary.mockResolvedValue({})
    const withSlack = task({
      associations: [{ id: 'a1', note: '', created_at: 'x', item: { id: 'i1', source: 'slack', content: 'th' } }]
    })
    const wrapper = mount(ContextPanel, { props: { task: withSlack } })
    const buttons = wrapper.findAll('.panel-head button')
    expect(buttons.map((b) => b.text()).join(' ')).toContain('Name & summarize')

    await buttons[1].trigger('click')
    await flushPromises()
    expect(mocks.refreshSummary).toHaveBeenCalledWith('t1')
    expect(store.toast.message).toContain('naming the task')
  })

  it('hides the summarize action without a Slack thread', () => {
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.text()).not.toContain('Name & summarize')
  })
})

describe('ItemsPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    associations: [
      {
        id: 'a1',
        note: 'a note',
        created_at: new Date().toISOString(),
        item: { id: 'i1', source: 'github', title: 'Issue 1', url: 'https://x', content: 'body', fetched_at: null }
      }
    ],
    ...over
  })

  it('groups items by source and shows notes', () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('GitHub')
    expect(wrapper.text()).toContain('Issue 1')
    expect(wrapper.text()).toContain('a note')
  })

  it('does nothing when the draft is empty', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).not.toHaveBeenCalled()
  })

  it('associates a new item and clears the draft', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://github.com/o/r/issues/2')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ item: expect.objectContaining({ url: 'https://github.com/o/r/issues/2' }) })
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.findAll('input')[0].element.value).toBe('')
  })

  it('notifies when associating fails', async () => {
    mocks.associate.mockRejectedValueOnce(new Error('bad'))
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://x')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'bad', isError: true })
  })

  it('removes and refreshes an item', async () => {
    mocks.unassociate.mockResolvedValue({})
    mocks.itemRefresh.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })

    await wrapper.get('button[title="Remove"]').trigger('click')
    await flushPromises()
    expect(mocks.unassociate).toHaveBeenCalledWith('t1', 'i1')

    await wrapper.get('button[title="Refresh"]').trigger('click')
    await flushPromises()
    expect(mocks.itemRefresh).toHaveBeenCalledWith('i1')
  })

  it('toggles the expanded state', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    const expand = wrapper.get('button[title="Expand"]')
    expect(expand.text()).toBe('▸')
    await expand.trigger('click')
    expect(wrapper.get('button[title="Expand"]').text()).toBe('▾')
  })

  it('shows the status of a pull request item', () => {
    const withPr = task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i1',
            source: 'github',
            kind: 'pull_request',
            title: 'Fix the thing',
            url: 'https://gh/pull/3',
            content: '',
            metadata_json: { state: 'OPEN', is_draft: true },
            fetched_at: null
          }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withPr } })
    expect(wrapper.text()).toContain('pull request')
    expect(wrapper.get('.badge.st-draft').text()).toBe('Draft')
  })

  const prTask = (over = {}) =>
    task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: {
            id: 'i1',
            source: 'github',
            kind: 'pull_request',
            title: 'Fix the thing',
            url: 'https://gh/pull/3',
            external_id: 'o/r#3',
            content: '',
            metadata_json: { state: 'OPEN' },
            fetched_at: null
          }
        }
      ],
      ...over
    })

  it('offers to record a change for a PR no change references yet', async () => {
    mocks.changeCreate.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: prTask() } })
    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()
    expect(mocks.changeCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Fix the thing',
      external_ref: 'https://gh/pull/3'
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('opens a merged PR as an accepted change dated to the merge', async () => {
    mocks.changeCreate.mockResolvedValue({})
    const merged = prTask()
    merged.associations[0].item.metadata_json = { state: 'MERGED', merged_at: '2026-10-11T05:23:53Z' }
    const wrapper = mount(ItemsPanel, { props: { task: merged } })
    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    await flushPromises()
    expect(mocks.changeCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Fix the thing',
      external_ref: 'https://gh/pull/3',
      status: 'accepted',
      opened_at: '2026-10-11T05:23:53Z',
      accepted_at: '2026-10-11T05:23:53Z'
    })
  })

  it('hides the record button when a change already references the PR', () => {
    const wrapper = mount(ItemsPanel, {
      props: { task: prTask({ changes: [{ id: 'c1', external_ref: 'https://gh/pull/3' }] }) }
    })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('matches a change recorded against the PR external id', () => {
    const wrapper = mount(ItemsPanel, {
      props: { task: prTask({ changes: [{ id: 'c1', external_ref: 'o/r#3' }] }) }
    })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('does not offer a change for a non-PR item', () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    expect(wrapper.find('button[title="Record a change for this PR"]').exists()).toBe(false)
  })

  it('leaves notes to the Notes panel', () => {
    const withNote = task({
      associations: [
        ...task().associations,
        {
          id: 'a2',
          note: '',
          created_at: new Date().toISOString(),
          item: { id: 'i2', source: 'note', title: 'Just a note', url: null, content: 'kept text', fetched_at: null }
        }
      ]
    })
    const wrapper = mount(ItemsPanel, { props: { task: withNote } })
    expect(wrapper.text()).toContain('GitHub')
    expect(wrapper.text()).not.toContain('Just a note')
    expect(wrapper.text()).not.toContain('kept text')
  })
})

describe('NotesPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    associations: [
      {
        id: 'a1',
        note: '',
        created_at: new Date().toISOString(),
        item: {
          id: 'i1',
          source: 'note',
          title: 'Remember this',
          url: null,
          content: 'the note body',
          fetched_at: null
        }
      },
      {
        id: 'a2',
        note: '',
        created_at: new Date().toISOString(),
        item: { id: 'i2', source: 'github', title: 'Issue 1', url: 'https://x', content: 'body', fetched_at: null }
      }
    ],
    ...over
  })

  it('shows a note as one value, without a title or extra controls', () => {
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    // The note's single value is its text; its (derived) title is not shown.
    expect(wrapper.text()).toContain('the note body')
    expect(wrapper.text()).not.toContain('Remember this')
    expect(wrapper.text()).not.toContain('Issue 1')
    expect(wrapper.find('button[title="Refresh"]').exists()).toBe(false)
    expect(wrapper.find('button[title="Expand"]').exists()).toBe(false)
  })

  it('shows an empty state without notes', () => {
    const wrapper = mount(NotesPanel, { props: { task: { id: 't1', associations: [] } } })
    expect(wrapper.text()).toContain('No notes yet')
  })

  it('shows the note date, not a relative time', () => {
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    const meta = wrapper.get('.item .faint').text()
    expect(meta).toContain('added')
    expect(meta).not.toContain('ago')
    expect(meta).toContain(String(new Date().getFullYear()))
  })

  it('renders the note content as Markdown', () => {
    const md = task({
      associations: [
        {
          id: 'a1',
          note: '',
          created_at: new Date().toISOString(),
          item: { id: 'i1', source: 'note', title: 'T', url: null, content: '**bold** and `code`', fetched_at: null }
        }
      ]
    })
    const wrapper = mount(NotesPanel, { props: { task: md } })
    const body = wrapper.get('.inline-edit .md')
    expect(body.find('strong').text()).toBe('bold')
    expect(body.find('code').text()).toBe('code')
  })

  it('associates a written note and clears the draft', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    await wrapper.get('textarea.textarea').setValue('a fresh note')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).toHaveBeenCalledWith('t1', {
      item: { title: '', content: 'a fresh note', fetch: false }
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.get('textarea.textarea').element.value).toBe('')
  })

  it('does nothing when the draft is empty', async () => {
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).not.toHaveBeenCalled()
  })

  it('submits the typed note on Ctrl+Enter', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    const field = wrapper.get('textarea.textarea')
    await field.setValue('a quick note')
    await field.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect(mocks.associate).toHaveBeenCalledWith('t1', {
      item: { title: '', content: 'a quick note', fetch: false }
    })
    expect(field.element.value).toBe('')
  })

  it('leaves a bare Enter to insert a newline', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    const field = wrapper.get('textarea.textarea')
    await field.setValue('line one')
    await field.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(mocks.associate).not.toHaveBeenCalled()
  })

  it('edits a note content inline', async () => {
    mocks.itemUpdate.mockResolvedValue({})
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    await wrapper.get('.inline-edit').trigger('click')
    const textarea = wrapper.get('textarea.inline-input')
    await textarea.setValue('edited body')
    await textarea.trigger('blur')
    await flushPromises()
    expect(mocks.itemUpdate).toHaveBeenCalledWith('i1', { content: 'edited body' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('notifies when editing a note fails', async () => {
    mocks.itemUpdate.mockRejectedValueOnce(new Error('nope'))
    const wrapper = mount(NotesPanel, { props: { task: task() } })
    await wrapper.get('.inline-edit').trigger('click')
    const textarea = wrapper.get('textarea.inline-input')
    await textarea.setValue('edited body')
    await textarea.trigger('blur')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'nope', isError: true })
  })

  it('removes a note', async () => {
    mocks.unassociate.mockResolvedValue({})
    const wrapper = mount(NotesPanel, { props: { task: task() } })

    await wrapper.get('button[title="Remove"]').trigger('click')
    await flushPromises()
    expect(mocks.unassociate).toHaveBeenCalledWith('t1', 'i1')
  })
})

describe('RepositorySelect', () => {
  const repositories = [
    { id: 'a', name: 'Alpha' },
    { id: 'b', name: 'Beta' }
  ]

  it('renders the selected chips and the empty label', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['b'], repositories } })
    expect(wrapper.get('.chip').text()).toContain('Beta')

    const empty = mount(RepositorySelect, { props: { modelValue: [], repositories: [] } })
    expect(empty.text()).toBe('no repositories')
  })

  it('emits an added repository and removes one', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['a'], repositories } })
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'b')
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]])

    await wrapper.get('.chip-x').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']], [[]]])
  })

  it('exposes activate for the command palette', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: [], repositories } })
    wrapper.vm.activate()
    expect(wrapper.findComponent(SearchSelect).exists()).toBe(true)
  })
})

describe('WorktreesPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    repository_ids: ['r1'],
    worktrees: [
      {
        id: 'w1',
        status: 'active',
        branch: 'feature',
        path: '/w',
        repository_id: 'r1',
        created_at: new Date().toISOString()
      }
    ],
    ...over
  })

  beforeEach(() => {
    store.settings = { editor_url_template: 'vscode://file/{path}' }
  })

  it('lists worktrees and opens the editor', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('feature')
    expect(wrapper.text()).toContain('/w')

    await wrapper.get('button[title="Open in editor"]').trigger('click')
    expect(open).toHaveBeenCalledWith('vscode://file//w', '_blank')
  })

  it('copies the worktree path', async () => {
    const writeText = vi.fn()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button[title="Copy path"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith('/w')
    expect(store.toast.message).toBe('Path copied')
  })

  it('removes a worktree when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.worktreeRemove.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.worktreeRemove).toHaveBeenCalledWith('t1', 'w1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('does not remove when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button.btn.danger').trigger('click')
    expect(mocks.worktreeRemove).not.toHaveBeenCalled()
  })

  it('creates a worktree with the drafted branch', async () => {
    mocks.worktreeCreate.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, {
      props: { task: task({ worktrees: [] }) },
      global: { stubs: { SearchSelect: true } }
    })
    await wrapper.findAll('input')[0].setValue('my-branch')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.worktreeCreate).toHaveBeenCalledWith('t1', { repository_id: 'r1', branch: 'my-branch' })
  })

  it('picks the repository for a new worktree even after one exists', async () => {
    mocks.worktreeCreate.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, {
      props: {
        task: task({ repository_ids: ['r1', 'r2'] }),
        repositories: [
          { id: 'r1', name: 'alpha' },
          { id: 'r2', name: 'beta' }
        ]
      }
    })
    expect(wrapper.findComponent(SearchSelect).exists()).toBe(true)
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'r2')
    await flushPromises()
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.worktreeCreate).toHaveBeenCalledWith('t1', { repository_id: 'r2' })
  })

  it('labels each worktree with its repository', () => {
    const wrapper = mount(WorktreesPanel, {
      props: {
        task: task(),
        repositories: [{ id: 'r1', name: 'alpha' }]
      }
    })
    expect(wrapper.get('.chip').text()).toBe('alpha')
  })

  it('disables creation without any repository', () => {
    const wrapper = mount(WorktreesPanel, {
      props: { task: task({ worktrees: [], repository_ids: [] }), repositories: [] },
      global: { stubs: { SearchSelect: true } }
    })
    expect(wrapper.get('.btn.primary').attributes('disabled')).toBeDefined()
  })
})
