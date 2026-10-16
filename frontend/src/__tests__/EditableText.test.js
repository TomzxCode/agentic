import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import EditableText from '../components/EditableText.vue'

describe('EditableText', () => {
  it('shows the value, or the placeholder when empty', () => {
    const withValue = mount(EditableText, { props: { value: 'Hello' } })
    expect(withValue.text()).toBe('Hello')

    const empty = mount(EditableText, { props: { placeholder: 'Add title' } })
    expect(empty.text()).toBe('Add title')
  })

  it('switches to an input seeded with the current value on click', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.trigger('click')
    const input = wrapper.get('input')
    expect(input.element.value).toBe('Hello')
  })

  it('emits save with the edited value on blur', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.trigger('click')
    const input = wrapper.get('input')
    await input.setValue('World')
    await input.trigger('blur')
    expect(wrapper.emitted('save')).toEqual([['World']])
  })

  it('does not emit when the value is unchanged', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.trigger('click')
    await wrapper.get('input').trigger('blur')
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('cancels on Escape without emitting', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.trigger('click')
    const input = wrapper.get('input')
    await input.setValue('World')
    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.text()).toBe('Hello')
  })

  it('starts editing from the keyboard on Enter', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.get('.inline-edit').trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('input').exists()).toBe(true)
  })

  it('submits a multiline field on Ctrl+Enter', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello', multiline: true } })
    await wrapper.trigger('click')
    const textarea = wrapper.get('textarea')
    await textarea.setValue('World')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('save')).toEqual([['World']])
  })

  it('exposes activate() for the command palette', async () => {
    const wrapper = mount(EditableText, { props: { value: 'Hello' } })
    await wrapper.vm.activate()
    expect(wrapper.find('input').exists()).toBe(true)
  })

  it('renders display Markdown while editing the raw value', async () => {
    const wrapper = mount(EditableText, {
      props: { value: '**bold**', markdown: true, as: 'div', multiline: true }
    })
    expect(wrapper.get('.md strong').text()).toBe('bold')
    await wrapper.get('.inline-edit').trigger('click')
    const textarea = wrapper.get('textarea')
    expect(textarea.element.value).toBe('**bold**')
    await textarea.setValue('*it*')
    await textarea.trigger('blur')
    expect(wrapper.emitted('save')).toEqual([['*it*']])
  })
})
