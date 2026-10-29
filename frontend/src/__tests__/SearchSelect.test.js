import { describe, expect, it } from 'vitest'
import { markRaw } from 'vue'
import { mount } from '@vue/test-utils'
import SearchSelect from '../components/SearchSelect.vue'

const options = [
  { value: 'b', label: 'Beta' },
  { value: '', label: 'None' },
  { value: 'a', label: 'Alpha' }
]

function open(wrapper) {
  return wrapper.get('.ss-trigger').trigger('click')
}

describe('SearchSelect', () => {
  it('shows the selected label', () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    expect(wrapper.get('.ss-label').text()).toBe('Alpha')
  })

  it('shows the placeholder when nothing matches', () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'missing', placeholder: 'Pick one', options } })
    expect(wrapper.get('.ss-label').text()).toBe('Pick one')
    expect(wrapper.get('.ss-label').classes()).toContain('placeholder')
  })

  it('sorts options alphabetically, keeping the empty sentinel first', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    await open(wrapper)
    expect(wrapper.findAll('.ss-option').map((o) => o.text())).toEqual(['None', 'Alpha', 'Beta'])
  })

  it('filters options as the user types', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    await open(wrapper)
    await wrapper.get('.ss-search').setValue('al')
    expect(wrapper.findAll('.ss-option').map((o) => o.text())).toEqual(['Alpha'])
  })

  it('shows an empty state when nothing matches', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    await open(wrapper)
    await wrapper.get('.ss-search').setValue('zzz')
    expect(wrapper.find('.ss-option').exists()).toBe(false)
    expect(wrapper.get('.ss-empty').text()).toBe('No matches')
  })

  it('emits the chosen value and closes', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    await open(wrapper)
    await wrapper.findAll('.ss-option')[2].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['b']])
    expect(wrapper.find('.ss-panel').exists()).toBe(false)
  })

  it('closes on Escape', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    await open(wrapper)
    await wrapper.get('.ss-search').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.ss-panel').exists()).toBe(false)
  })

  it('does not open when disabled', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options, disabled: true } })
    await open(wrapper)
    expect(wrapper.find('.ss-panel').exists()).toBe(false)
  })

  it('exposes activate() to open the dropdown', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: 'a', options } })
    wrapper.vm.activate()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
  })

  it('shows only the selected icon in the icon variant', async () => {
    const Icon = markRaw({ template: '<span class="fake-icon" />' })
    const iconOptions = [{ value: 'a', label: 'Alpha', icon: Icon }]
    const wrapper = mount(SearchSelect, {
      props: { modelValue: 'a', variant: 'icon', options: iconOptions }
    })
    expect(wrapper.get('.ss-trigger').find('.fake-icon').exists()).toBe(true)
    expect(wrapper.find('.ss-label').exists()).toBe(false)

    // The dropdown still spells out the options.
    await open(wrapper)
    expect(wrapper.get('.ss-option').text()).toBe('Alpha')
  })

  it('keeps the list open and clears the filter after choosing when keepOpen is set', async () => {
    const wrapper = mount(SearchSelect, { props: { modelValue: '', options, keepOpen: true } })
    await open(wrapper)
    await wrapper.get('.ss-search').setValue('al')
    await wrapper.findAll('.ss-option')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['a']])
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
    expect(wrapper.get('.ss-search').element.value).toBe('')
  })

  describe('multiple', () => {
    const multi = () => mount(SearchSelect, { props: { modelValue: [], options, multiple: true } })

    it('toggles a value and keeps the list open', async () => {
      const wrapper = multi()
      await open(wrapper)
      await wrapper.findAll('.ss-option')[1].trigger('click')
      await wrapper.setProps({ modelValue: ['a'] })
      await wrapper.findAll('.ss-option')[2].trigger('click')

      expect(wrapper.emitted('update:modelValue')).toEqual([[['a']], [['a', 'b']]])
      expect(wrapper.find('.ss-panel').exists()).toBe(true)
      expect(wrapper.get('.ss-search').element.value).toBe('')
    })

    it('untoggles a chosen value', async () => {
      const wrapper = mount(SearchSelect, { props: { modelValue: ['a', 'b'], options, multiple: true } })
      await open(wrapper)
      await wrapper.findAll('.ss-option')[1].trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[['b']]])
    })

    it('summarizes the chosen labels on the trigger and ticks the options', async () => {
      const wrapper = mount(SearchSelect, { props: { modelValue: ['b'], options, multiple: true } })
      expect(wrapper.get('.ss-label').text()).toBe('Beta')
      await open(wrapper)
      const beta = wrapper.findAll('.ss-option').find((option) => option.text().includes('Beta'))
      expect(beta.text()).toContain('✓')
      expect(beta.attributes('aria-pressed')).toBe('true')
    })

    it('shows the placeholder when nothing is chosen', () => {
      const wrapper = mount(SearchSelect, {
        props: { modelValue: [], options, multiple: true, placeholder: 'All authors' }
      })
      expect(wrapper.get('.ss-label').text()).toBe('All authors')
      expect(wrapper.get('.ss-label').classes()).toContain('placeholder')
    })
  })

  describe('bulk actions', () => {
    const bulk = (props = {}) =>
      mount(SearchSelect, { props: { modelValue: [], options, multiple: true, bulkActions: true, ...props } })

    it('takes every real option in one click, skipping the empty sentinel', async () => {
      const wrapper = bulk({ modelValue: ['a'] })
      await open(wrapper)
      const actions = wrapper.findAll('.ss-bulk-action')
      expect(actions.map((action) => action.text())).toEqual(['Select all', 'Deselect all'])

      await actions[0].trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]])
      // The panel stays open and the search box keeps the focus.
      expect(wrapper.find('.ss-panel').exists()).toBe(true)
    })

    it('selects only the options the search box lists', async () => {
      const wrapper = bulk()
      await open(wrapper)
      await wrapper.get('.ss-search').setValue('be')
      await wrapper.get('.ss-bulk-action').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[['b']]])
    })

    it('clears the whole selection in one click', async () => {
      const wrapper = bulk({ modelValue: ['a', 'b'] })
      await open(wrapper)
      await wrapper.findAll('.ss-bulk-action')[1].trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[[]]])
    })

    it('disables each action when it would change nothing', async () => {
      const none = bulk()
      await open(none)
      expect(none.findAll('.ss-bulk-action')[0].attributes('disabled')).toBeUndefined()
      expect(none.findAll('.ss-bulk-action')[1].attributes('disabled')).toBeDefined()

      const all = bulk({ modelValue: ['a', 'b'] })
      await open(all)
      expect(all.findAll('.ss-bulk-action')[0].attributes('disabled')).toBeDefined()
      expect(all.findAll('.ss-bulk-action')[1].attributes('disabled')).toBeUndefined()
    })

    it('stays out of a single select and of a multi-select without the option', async () => {
      const single = mount(SearchSelect, { props: { modelValue: '', options, bulkActions: true } })
      await open(single)
      expect(single.find('.ss-bulk').exists()).toBe(false)

      const multi = mount(SearchSelect, { props: { modelValue: [], options, multiple: true } })
      await open(multi)
      expect(multi.find('.ss-bulk').exists()).toBe(false)
    })
  })

  describe('creatable', () => {
    const creatable = (props = {}) =>
      mount(SearchSelect, { props: { modelValue: '', options, creatable: true, keepOpen: true, ...props } })

    it('offers the typed text as a new value when no option matches', async () => {
      const wrapper = creatable()
      await open(wrapper)
      await wrapper.get('.ss-search').setValue('Gamma')

      const create = wrapper.get('.ss-option.create')
      expect(create.text()).toBe('Create "Gamma"')
      await create.trigger('click')

      expect(wrapper.emitted('update:modelValue')).toEqual([['Gamma']])
      // The list stays open and the filter clears for the next value.
      expect(wrapper.find('.ss-panel').exists()).toBe(true)
      expect(wrapper.get('.ss-search').element.value).toBe('')
    })

    it('does not offer a duplicate of an existing option, whatever the case', async () => {
      const wrapper = creatable()
      await open(wrapper)
      await wrapper.get('.ss-search').setValue('alpha')

      expect(wrapper.find('.ss-option.create').exists()).toBe(false)
      expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['Alpha'])
    })

    it('offers no create entry when the list is not creatable', async () => {
      const wrapper = mount(SearchSelect, { props: { modelValue: '', options } })
      await open(wrapper)
      await wrapper.get('.ss-search').setValue('Gamma')
      expect(wrapper.find('.ss-option.create').exists()).toBe(false)
    })
  })
})
