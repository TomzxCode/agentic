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

  it('does not open the editor when a task-list checkbox is clicked', async () => {
    const wrapper = mount(EditableText, {
      props: { value: '- [ ] Do it', markdown: true, taskLists: true, as: 'div', multiline: true }
    })
    await wrapper.get('input[type=checkbox]').trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })

  it('opens the editor from an edit button in the field, leaving the content its own clicks', async () => {
    const raw = '<details><summary>More</summary>body</details>'
    const wrapper = mount(EditableText, {
      props: { value: raw, markdown: true, editTrigger: 'field', as: 'div', multiline: true }
    })
    // The click belongs to the collapsible section, not to the field.
    await wrapper.get('summary').trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(false)

    await wrapper.get('.inline-edit-btn').trigger('click')
    const textarea = wrapper.get('textarea')
    expect(textarea.element.value).toBe(raw)
    await textarea.setValue('plain text')
    await textarea.trigger('blur')
    expect(wrapper.emitted('save')).toEqual([['plain text']])
  })

  it('keeps the placeholder clickable when an edit button field is empty', async () => {
    const wrapper = mount(EditableText, {
      props: { markdown: true, editTrigger: 'field', as: 'div', multiline: true, placeholder: 'Add one…' }
    })
    await wrapper.trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('opens a multiline editor at the height the value occupied on screen', async () => {
    const wrapper = mount(EditableText, {
      props: { value: 'A **short** note', markdown: true, multiline: true, as: 'div' }
    })
    // jsdom does no layout, so stand in for the rendered height of the value.
    Object.defineProperty(wrapper.get('.inline-edit').element, 'offsetHeight', { configurable: true, value: 240 })

    await wrapper.get('.inline-edit').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('textarea').element.style.height).toBe('240px')
  })

  it('opens from an external action, protecting the content and reporting its editing state', async () => {
    const raw = '<details><summary>More</summary>body</details>'
    const wrapper = mount(EditableText, {
      props: { value: raw, markdown: true, editTrigger: 'external', as: 'div', multiline: true }
    })
    // No button lives inside the field; the parent renders it.
    expect(wrapper.find('.inline-edit-btn').exists()).toBe(false)
    // The collapsible section keeps its click.
    await wrapper.get('summary').trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.emitted('editing')).toBeUndefined()

    await wrapper.vm.activate()
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.emitted('editing')).toEqual([[true]])

    await wrapper.get('textarea').trigger('blur')
    expect(wrapper.emitted('editing')).toEqual([[true], [false]])
  })
})
