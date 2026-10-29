import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TagInput from '../components/TagInput.vue'

async function openPicker(wrapper) {
  await wrapper.get('.ss-trigger').trigger('click')
}

describe('TagInput', () => {
  it('renders a removable chip per tag', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['bug', 'ui'] } })
    expect(wrapper.findAll('.chip')).toHaveLength(2)
    expect(wrapper.text()).toContain('bug')

    await wrapper.findAll('.chip-x')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['ui'])
  })

  it('offers the existing tags in the picker, excluding those already applied', async () => {
    const wrapper = mount(TagInput, {
      props: {
        modelValue: ['bug'],
        suggestions: [
          { name: 'bug', count: 2 },
          { name: 'urgent', count: 1 }
        ]
      }
    })
    await openPicker(wrapper)
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['urgent'])

    await wrapper.get('.ss-option').trigger('click')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['bug', 'urgent'])
    // The picker stays open for the next tag.
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
  })

  it('filters the offered tags as the user types', async () => {
    const wrapper = mount(TagInput, {
      props: { suggestions: [{ name: 'bug' }, { name: 'urgent' }] }
    })
    await openPicker(wrapper)
    await wrapper.get('.ss-search').setValue('urg')
    // The close match comes first, so Enter picks it; the typed text is still
    // offered as a new tag after it.
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['urgent', 'Create "urg"'])
  })

  it('creates a tag that does not exist yet', async () => {
    const wrapper = mount(TagInput, { props: { suggestions: [{ name: 'bug' }] } })
    await openPicker(wrapper)
    await wrapper.get('.ss-search').setValue('infra')

    const create = wrapper.get('.ss-option.create')
    expect(create.text()).toContain('Create "infra"')
    await create.trigger('click')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['infra'])
  })

  it('does not offer to create a tag that already exists', async () => {
    const wrapper = mount(TagInput, { props: { suggestions: [{ name: 'bug' }] } })
    await openPicker(wrapper)
    await wrapper.get('.ss-search').setValue('bug')

    expect(wrapper.find('.ss-option.create').exists()).toBe(false)
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['bug'])
  })

  it('removes the last tag on Backspace when the picker filter is empty', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['bug', 'ui'] } })
    await openPicker(wrapper)
    await wrapper.get('.ss-search').trigger('keydown', { key: 'Backspace' })
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['bug'])
  })

  it('opens the picker through activate() for the command palette', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: [] } })
    wrapper.vm.activate()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.ss-panel').exists()).toBe(true)
  })
})
