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
})
