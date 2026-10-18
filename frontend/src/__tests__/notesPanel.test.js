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

import NotesPanel from '../components/NotesPanel.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
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
