import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TagInput from '../components/TagInput.vue'

describe('TagInput', () => {
  it('renders a removable chip per tag', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['bug', 'ui'] } })
    expect(wrapper.findAll('.chip')).toHaveLength(2)
    expect(wrapper.text()).toContain('bug')

    await wrapper.findAll('.chip-x')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['ui'])
  })

  it('adds a tag on Enter and clears the field', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['bug'] } })
    await wrapper.get('.tag-entry').setValue('urgent')
    await wrapper.get('.tag-entry').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['bug', 'urgent'])
    expect(wrapper.get('.tag-entry').element.value).toBe('')
  })

  it('adds a tag on comma and ignores blanks', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: [] } })
    const entry = wrapper.get('.tag-entry')

    await entry.setValue('   ')
    await entry.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    await entry.setValue('ui')
    await entry.trigger('keydown', { key: ',' })
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['ui'])
  })

  it('ignores a tag that is already applied', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['ui'] } })
    await wrapper.get('.tag-entry').setValue('ui')
    await wrapper.get('.tag-entry').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('removes the last tag on Backspace when the field is empty', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: ['bug', 'ui'] } })
    await wrapper.get('.tag-entry').trigger('keydown', { key: 'Backspace' })
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['bug'])
  })

  it('offers existing tags as quick picks, excluding those already applied', async () => {
    const wrapper = mount(TagInput, {
      props: {
        modelValue: ['bug'],
        suggestions: [
          { name: 'bug', count: 2 },
          { name: 'urgent', count: 1 }
        ]
      }
    })
    const picks = wrapper.findAll('.chip-add')
    expect(picks).toHaveLength(1)
    expect(picks[0].text()).toContain('urgent')

    await picks[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['bug', 'urgent'])
  })

  it('commits a typed tag on blur', async () => {
    const wrapper = mount(TagInput, { props: { modelValue: [] } })
    await wrapper.get('.tag-entry').setValue('infra')
    await wrapper.get('.tag-entry').trigger('blur')
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(['infra'])
  })
})
