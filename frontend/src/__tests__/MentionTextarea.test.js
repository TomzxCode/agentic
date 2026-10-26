import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import MentionTextarea from '../components/MentionTextarea.vue'
import { store } from '../store'

enableAutoUnmount(afterEach)

beforeEach(() => {
  store.people = [
    { id: 'p1', name: 'Ada Lovelace', aliases: ['ada'] },
    { id: 'p2', name: 'Grace Hopper', aliases: ['grace'] }
  ]
  store.tasks = [
    { id: 't1', title: 'Ship release notes', status: 'in_progress' },
    { id: 't2', title: 'Plan the launch', status: 'open' }
  ]
  store.items = [
    { id: 'i1', source: 'github', kind: 'issue', title: 'Fix login timeout', metadata_json: { number: 42 } },
    { id: 'i2', source: 'note', kind: '', title: 'just a note' }
  ]
})

afterEach(() => {
  vi.useRealTimers()
  store.people = []
  store.tasks = []
  store.items = []
})

// Put `value` in the textarea, place the caret at its end, and fire input. The
// prop is what the field's value is, so the test passes it in.
async function typeWith(wrapper, value) {
  await wrapper.setProps({ modelValue: value })
  const field = wrapper.get('textarea')
  field.element.value = value
  field.element.setSelectionRange(value.length, value.length)
  await field.trigger('input')
}

async function type(wrapper, value) {
  await typeWith(wrapper, value)
}

describe('MentionTextarea', () => {
  it('opens the picker on @ and lists only matching people and items', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@ad')
    const panel = wrapper.get('.mention-panel')
    expect(panel.text()).toContain('Ada Lovelace')
    expect(panel.text()).not.toContain('Grace Hopper')
    expect(panel.text()).not.toContain('just a note')
  })

  it('inserts the name as plain text', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, 'ask @ad')
    await wrapper.get('.mention-option').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['ask @Ada Lovelace '])
  })

  it('chooses an item too', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@login')
    const option = wrapper.get('.mention-option')
    expect(option.text()).toContain('Fix login timeout')
    await option.trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['@Fix login timeout '])
  })

  it('references another task by its id with a readable label', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@release')
    expect(wrapper.get('.mention-panel').text()).toContain('Tasks')
    await wrapper.get('.mention-option').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['[@Ship release notes](/task/t1) '])
  })

  it('shows the current title of a saved task reference', () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: 'see [@Old title](/task/t1)' } })
    expect(wrapper.get('textarea').element.value).toBe('see [@Ship release notes](/task/t1)')
  })

  it('offers relative dates and inserts the date instead of the phrase', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 26, 12))
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@last')
    const panel = wrapper.get('.mention-panel')
    expect(panel.text()).toContain('Dates')
    expect(panel.text()).toContain('last week')
    expect(panel.text()).toContain('last month')
    // The full phrase keeps the picker open: choosing it is what writes the date.
    await type(wrapper, '@last week')
    expect(wrapper.find('.mention-panel').exists()).toBe(true)
    await wrapper.get('.mention-option').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['2026-10-19 '])
  })

  it('moves the highlight with the arrow keys and inserts with Enter', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@a')
    const field = wrapper.get('textarea')
    await field.trigger('keydown', { key: 'ArrowDown' })
    await field.trigger('keydown', { key: 'Enter' })
    // The first match is Ada (a prefix match); the next is Grace.
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['@Grace Hopper '])
  })

  it('closes on Escape without changing the value', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '@a' } })
    const field = wrapper.get('textarea')
    field.element.setSelectionRange(2, 2)
    await field.trigger('input')
    expect(wrapper.find('.mention-panel').exists()).toBe(true)
    const before = wrapper.emitted('update:modelValue')?.length || 0
    await field.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.mention-panel').exists()).toBe(false)
    expect(wrapper.emitted('update:modelValue')?.length || 0).toBe(before)
  })

  it('closes once the typed text spells a whole name', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: '' } })
    await type(wrapper, '@Ada Lov')
    expect(wrapper.find('.mention-panel').exists()).toBe(true)
    await type(wrapper, '@Ada Lovelace')
    expect(wrapper.find('.mention-panel').exists()).toBe(false)
  })

  it('forwards keys the picker does not take', async () => {
    const wrapper = mount(MentionTextarea, { props: { modelValue: 'plain' } })
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('keydown')).toHaveLength(1)
  })
})
