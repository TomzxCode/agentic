import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandPalette from '../components/CommandPalette.vue'

const items = [
  { id: 'new', label: 'New task', group: 'Actions' },
  { id: 'settings', label: 'Go to settings', group: 'Navigation' },
  { id: 't1', label: 'Fix login bug', group: 'Tasks', hint: '#1' }
]

function mountPalette() {
  return mount(CommandPalette, { props: { items }, attachTo: document.body })
}

describe('CommandPalette', () => {
  it('lists every item grouped in the canonical section order', () => {
    const wrapper = mountPalette()
    expect(wrapper.findAll('.palette-group-title').map((t) => t.text())).toEqual(['Actions', 'Navigation', 'Tasks'])
    expect(wrapper.findAll('.palette-item')).toHaveLength(3)
  })

  it('filters items by label as the user types', async () => {
    const wrapper = mountPalette()
    await wrapper.get('.palette-input').setValue('login')
    const labels = wrapper.findAll('.palette-item').map((i) => i.text())
    expect(labels).toEqual(['Fix login bug#1'])
  })

  it('matches subsequences, not just substrings', async () => {
    const wrapper = mountPalette()
    await wrapper.get('.palette-input').setValue('stg')
    expect(wrapper.findAll('.palette-item').map((i) => i.text())).toEqual(['Go to settings'])
  })

  it('shows an empty state when nothing matches', async () => {
    const wrapper = mountPalette()
    await wrapper.get('.palette-input').setValue('zzzzz')
    expect(wrapper.find('.palette-item').exists()).toBe(false)
    expect(wrapper.get('.palette-empty').text()).toBe('No matches')
  })

  it('moves the highlight with the arrow keys', async () => {
    const wrapper = mountPalette()
    const input = wrapper.get('.palette-input')
    expect(wrapper.findAll('.palette-item')[0].classes()).toContain('active')
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.findAll('.palette-item')[1].classes()).toContain('active')
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(wrapper.findAll('.palette-item')[0].classes()).toContain('active')
  })

  it('selects the highlighted item on Enter and closes', async () => {
    const wrapper = mountPalette()
    const input = wrapper.get('.palette-input')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')).toEqual([[items[1]]])
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('selects on click', async () => {
    const wrapper = mountPalette()
    await wrapper.findAll('.palette-item')[2].trigger('click')
    expect(wrapper.emitted('select')).toEqual([[items[2]]])
  })

  it('closes on Escape', async () => {
    const wrapper = mountPalette()
    await wrapper.get('.palette-input').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
