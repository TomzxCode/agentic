import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RepositorySelect from '../components/RepositorySelect.vue'

const repositories = [
  { id: 'r1', name: 'alpha' },
  { id: 'r2', name: 'beta' },
  { id: 'r3', name: 'gamma' }
]

describe('RepositorySelect', () => {
  it('shows a chip per selected repository, sorted by name', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['r2', 'r1'], repositories } })
    // The chip lays the name and the remove control out with `gap`, so the text
    // content carries no literal space between them.
    expect(wrapper.findAll('.chip').map((c) => c.text())).toEqual(['alpha×', 'beta×'])
  })

  it('emits the remaining ids when a chip is removed', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['r1', 'r2'], repositories } })
    await wrapper.findAll('.chip-x')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['r2']]])
  })

  it('adds the repository chosen from the dropdown and keeps the list open', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['r1'], repositories } })
    await wrapper.get('.ss-trigger').trigger('click')
    await wrapper.findAll('.ss-option')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['r1', 'r2']]])
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
  })

  it('hides the add dropdown once every repository is selected', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['r1', 'r2', 'r3'], repositories } })
    expect(wrapper.find('.ss-trigger').exists()).toBe(false)
  })

  it('shows the empty label when there are no repositories', () => {
    const wrapper = mount(RepositorySelect, {
      props: { modelValue: [], repositories: [], emptyLabel: 'none registered' }
    })
    expect(wrapper.get('.faint').text()).toBe('none registered')
  })

  it('exposes activate() to open the add dropdown', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: [], repositories } })
    wrapper.vm.activate()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
  })
})
