import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// NotesPanel renders a <router-link> inside its Markdown; stub it so mounting
// does not warn about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

import NotesPanel from '../components/NotesPanel.vue'
import { store } from '../store'

const note = (over = {}) => ({
  id: 'n1',
  content: 'the note body',
  created_at: new Date().toISOString(),
  ...over
})

function mountPanel(over = {}) {
  const props = {
    notes: [note(), note({ id: 'n2', content: 'another body' })],
    add: vi.fn(),
    save: vi.fn(),
    remove: vi.fn(),
    ...over
  }
  return { wrapper: mount(NotesPanel, { props }), props }
}

beforeEach(() => {
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('NotesPanel', () => {
  it('shows each note as one value, without a title or extra controls', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.text()).toContain('the note body')
    expect(wrapper.text()).toContain('another body')
    expect(wrapper.find('button[title="Refresh"]').exists()).toBe(false)
    expect(wrapper.find('button[title="Expand"]').exists()).toBe(false)
  })

  it('shows an empty state without notes', () => {
    const { wrapper } = mountPanel({ notes: [] })
    expect(wrapper.text()).toContain('No notes yet')
  })

  it('shows the note date, not a relative time', () => {
    const { wrapper } = mountPanel()
    const meta = wrapper.get('.item .faint').text()
    expect(meta).toContain('added')
    expect(meta).not.toContain('ago')
    expect(meta).toContain(String(new Date().getFullYear()))
  })

  it('renders the note content as Markdown', () => {
    const { wrapper } = mountPanel({ notes: [note({ content: '**bold** and `code`' })] })
    const body = wrapper.get('.inline-edit .md')
    expect(body.find('strong').text()).toBe('bold')
    expect(body.find('code').text()).toBe('code')
  })

  it('adds a written note and clears the draft', async () => {
    const { wrapper, props } = mountPanel()
    await wrapper.get('textarea.textarea').setValue('a fresh note')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(props.add).toHaveBeenCalledWith('a fresh note')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.get('textarea.textarea').element.value).toBe('')
  })

  it('does nothing when the draft is empty', async () => {
    const { wrapper, props } = mountPanel()
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(props.add).not.toHaveBeenCalled()
  })

  it('submits the typed note on Ctrl+Enter', async () => {
    const { wrapper, props } = mountPanel()
    const field = wrapper.get('textarea.textarea')
    await field.setValue('a quick note')
    await field.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect(props.add).toHaveBeenCalledWith('a quick note')
    expect(field.element.value).toBe('')
  })

  it('leaves a bare Enter to insert a newline', async () => {
    const { wrapper, props } = mountPanel()
    const field = wrapper.get('textarea.textarea')
    await field.setValue('line one')
    await field.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(props.add).not.toHaveBeenCalled()
  })

  it('edits a note content inline', async () => {
    const { wrapper, props } = mountPanel()
    await wrapper.get('.inline-edit').trigger('click')
    const textarea = wrapper.get('textarea.inline-input')
    await textarea.setValue('edited body')
    await textarea.trigger('blur')
    await flushPromises()
    expect(props.save).toHaveBeenCalledWith('n1', 'edited body')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('notifies when editing a note fails', async () => {
    const { wrapper } = mountPanel({ save: vi.fn().mockRejectedValueOnce(new Error('nope')) })
    await wrapper.get('.inline-edit').trigger('click')
    const textarea = wrapper.get('textarea.inline-input')
    await textarea.setValue('edited body')
    await textarea.trigger('blur')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'nope', isError: true })
  })

  it('removes a note', async () => {
    const { wrapper, props } = mountPanel()
    await wrapper.get('button[title="Remove"]').trigger('click')
    await flushPromises()
    expect(props.remove).toHaveBeenCalledWith('n1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
})
