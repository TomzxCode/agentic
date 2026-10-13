import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  transition: vi.fn(),
  intervene: vi.fn(),
  remove: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    changes: {
      create: mocks.create,
      transition: mocks.transition,
      intervene: mocks.intervene,
      remove: mocks.remove
    }
  }
}))

import ChangesPanel from '../components/ChangesPanel.vue'
import { changeCreateBody, changeReferencesItem, changesForItem, changeStatusBadge } from '../changes'
import { store } from '../store'

const SearchSelectStub = {
  props: ['modelValue', 'options'],
  emits: ['update:modelValue'],
  template:
    '<select class="ss" @change="$emit(\'update:modelValue\', $event.target.value)">' +
    '<option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>'
}

const task = {
  id: 't1',
  title: 'Task One',
  changes: [
    {
      id: 'c1',
      task_id: 't1',
      title: 'Fix bug',
      change_class: 'bugfix',
      status: 'proposed',
      human_intervened: false,
      external_ref: null,
      opened_at: new Date().toISOString()
    }
  ]
}

function mountPanel(props = { task }) {
  return mount(ChangesPanel, { props, global: { stubs: { SearchSelect: SearchSelectStub } } })
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ChangesPanel', () => {
  it('lists the changes of a task', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('Changes')
    expect(wrapper.text()).toContain('Fix bug')
    expect(wrapper.text()).toContain('bugfix')
  })

  it('records a change against the task', async () => {
    mocks.create.mockResolvedValue({})
    const wrapper = mountPanel()
    await wrapper.get('input[placeholder="What changed?"]').setValue('Add a test')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Record change')
      .trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Add a test',
      change_class: 'feature',
      external_ref: null
    })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('moves a change through its lifecycle', async () => {
    mocks.transition.mockResolvedValue({})
    const wrapper = mountPanel()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Accept')
      .trigger('click')
    await flushPromises()
    expect(mocks.transition).toHaveBeenCalledWith('c1', 'accepted')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('asks for the kind only after Intervene is clicked, then saves it', async () => {
    mocks.intervene.mockResolvedValue({})
    const wrapper = mountPanel()

    // No kind picker until asked.
    expect(wrapper.find('.intervene-kind').exists()).toBe(false)

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Intervene')
      .trigger('click')
    await flushPromises()
    expect(mocks.intervene).not.toHaveBeenCalled()
    expect(wrapper.find('.intervene-kind').exists()).toBe(true)

    // Save is disabled until a kind is chosen.
    const save = () => wrapper.findAll('button').find((b) => b.text() === 'Save')
    expect(save().attributes('disabled')).toBeDefined()

    await wrapper.get('.intervene-kind select.ss').setValue('correction')
    await save().trigger('click')
    await flushPromises()
    expect(mocks.intervene).toHaveBeenCalledWith('c1', { kind: 'correction' })
    expect(wrapper.emitted('changed')).toBeTruthy()
    expect(wrapper.find('.intervene-kind').exists()).toBe(false)
  })

  it('cancels an intervention without recording it', async () => {
    const wrapper = mountPanel()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Intervene')
      .trigger('click')
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Cancel')
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('.intervene-kind').exists()).toBe(false)
    expect(mocks.intervene).not.toHaveBeenCalled()
  })

  it('deletes a change', async () => {
    mocks.remove.mockResolvedValue(null)
    vi.stubGlobal('confirm', () => true)
    const wrapper = mountPanel()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Delete')
      .trigger('click')
    await flushPromises()
    expect(mocks.remove).toHaveBeenCalledWith('c1')
  })
})

describe('change helpers', () => {
  it('maps a status to its badge class, defaulting to the neutral badge', () => {
    expect(changeStatusBadge('accepted')).toBe('badge ok')
    expect(changeStatusBadge('proposed')).toBe('badge')
    expect(changeStatusBadge('nonsense')).toBe('badge')
  })

  it('matches a change to an item by url or external id', () => {
    const item = { url: 'https://gh/pull/3', external_id: 'o/r#3' }
    expect(changeReferencesItem({ external_ref: 'https://gh/pull/3' }, item)).toBe(true)
    expect(changeReferencesItem({ external_ref: 'o/r#3' }, item)).toBe(true)
    expect(changeReferencesItem({ external_ref: ' https://gh/pull/3 ' }, item)).toBe(true)
    expect(changeReferencesItem({ external_ref: 'https://gh/pull/4' }, item)).toBe(false)
    expect(changeReferencesItem({ external_ref: null }, item)).toBe(false)
    expect(changeReferencesItem({ external_ref: 'https://gh/pull/3' }, null)).toBe(false)
  })

  it('keeps only the changes that reference an item', () => {
    const item = { url: 'https://gh/pull/3' }
    const changes = [
      { id: 'a', external_ref: 'https://gh/pull/3' },
      { id: 'b', external_ref: null }
    ]
    expect(changesForItem(changes, item).map((c) => c.id)).toEqual(['a'])
    expect(changesForItem(null, item)).toEqual([])
  })

  it('builds the body that records a change for an item', () => {
    expect(changeCreateBody('t1', { title: 'Fix', url: 'https://gh/pull/3' })).toEqual({
      task_id: 't1',
      title: 'Fix',
      external_ref: 'https://gh/pull/3'
    })

    // A merged PR opens accepted and dated to the merge.
    expect(
      changeCreateBody('t1', {
        title: 'Fix',
        url: 'https://gh/pull/3',
        metadata_json: { merged_at: '2026-10-11T05:23:53Z' }
      })
    ).toEqual({
      task_id: 't1',
      title: 'Fix',
      external_ref: 'https://gh/pull/3',
      status: 'accepted',
      opened_at: '2026-10-11T05:23:53Z',
      accepted_at: '2026-10-11T05:23:53Z'
    })

    // A merge time resolved elsewhere (a fresh GitHub fetch) overrides the
    // item's stored metadata.
    expect(changeCreateBody('t1', { title: 'Fix', url: 'https://gh/pull/3' }, '2026-10-12T00:00:00Z')).toEqual({
      task_id: 't1',
      title: 'Fix',
      external_ref: 'https://gh/pull/3',
      status: 'accepted',
      opened_at: '2026-10-12T00:00:00Z',
      accepted_at: '2026-10-12T00:00:00Z'
    })
  })
})
