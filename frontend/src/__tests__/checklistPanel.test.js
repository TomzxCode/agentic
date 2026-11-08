import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  addItem: vi.fn(),
  updateItem: vi.fn(),
  updateTask: vi.fn(),
  removeItem: vi.fn(),
  reorderItems: vi.fn(),
  convertItem: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: {
      addChecklistItem: mocks.addItem,
      updateChecklistItem: mocks.updateItem,
      update: mocks.updateTask,
      removeChecklistItem: mocks.removeItem,
      reorderChecklistItems: mocks.reorderItems,
      convertChecklistItem: mocks.convertItem
    }
  }
}))

import ChecklistPanel from '../components/ChecklistPanel.vue'

function task(checklist) {
  return { id: 't1', checklist }
}

describe('ChecklistPanel', () => {
  afterEach(() => vi.clearAllMocks())

  it('shows applicable progress and disables items whose template no longer matches', () => {
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([
          {
            id: 'i1',
            text: 'Announce the feature',
            done: false,
            applicable: true,
            template_name: 'Feature'
          },
          { id: 'i2', text: 'Write docs', done: true, applicable: true, template_name: null },
          { id: 'i3', text: 'Old step', done: false, applicable: false, template_name: 'Old' }
        ])
      }
    })

    expect(wrapper.text()).toContain('1/2')
    expect(wrapper.text()).toContain('no longer applies')
    const boxes = wrapper.findAll('input[type="checkbox"]')
    expect(boxes).toHaveLength(3)
    expect(boxes[2].attributes('disabled')).toBeDefined()
  })

  it('checks an item off and adds a manual item', async () => {
    mocks.updateItem.mockResolvedValue({})
    mocks.addItem.mockResolvedValue({})
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([{ id: 'i1', text: 'Announce', done: false, applicable: true, template_name: 'Feature' }])
      }
    })

    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(mocks.updateItem).toHaveBeenCalledWith('t1', 'i1', { done: true })
    expect(wrapper.emitted('changed')).toHaveLength(1)

    await wrapper.get('input[aria-label="New checklist item"]').setValue('Add a release note')
    await wrapper.get('button.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.addItem).toHaveBeenCalledWith('t1', { text: 'Add a release note' })
  })

  it('removes an item', async () => {
    mocks.removeItem.mockResolvedValue(null)
    const wrapper = mount(ChecklistPanel, {
      props: { task: task([{ id: 'i1', text: 'Announce', done: false, applicable: true }]) }
    })

    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.removeItem).toHaveBeenCalledWith('t1', 'i1')
  })

  it('converts an item into a task', async () => {
    mocks.convertItem.mockResolvedValue({ id: 'new-task', title: 'Announce the feature' })
    const wrapper = mount(ChecklistPanel, {
      props: { task: task([{ id: 'i1', text: 'Announce the feature', done: false, applicable: true }]) }
    })

    await wrapper.get('button[aria-label="Convert Announce the feature into a task"]').trigger('click')
    await flushPromises()

    expect(mocks.convertItem).toHaveBeenCalledWith('t1', 'i1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('links a converted item to its task instead of offering another conversion', () => {
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([
          {
            id: 'i1',
            text: 'Announce the feature',
            done: true,
            applicable: true,
            converted_task_id: 'new-task',
            converted_task_title: 'Announce the feature'
          }
        ])
      },
      global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } }
    })

    expect(wrapper.find('button[aria-label="Convert Announce the feature into a task"]').exists()).toBe(false)
    const link = wrapper.get('a[href="/task/new-task"]')
    expect(link.find('svg').exists()).toBe(true)
    expect(link.attributes('aria-label')).toBe('Open the task: Announce the feature')
  })

  it('edits the linked task title from a converted item', async () => {
    mocks.updateTask.mockResolvedValue({})
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([
          {
            id: 'i1',
            text: 'Old step text',
            done: true,
            applicable: true,
            converted_task_id: 'new-task',
            converted_task_title: 'Announce the feature'
          }
        ])
      },
      global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } }
    })

    // The field shows the live task title, and the checked row keeps its done
    // state, which draws the strikethrough.
    expect(wrapper.get('.checklist-item').classes()).toContain('done')
    expect(wrapper.get('.checklist-text').text()).toBe('Announce the feature')

    await wrapper.get('.checklist-text').trigger('click')
    const field = wrapper.get('input.inline-input')
    expect(field.element.value).toBe('Announce the feature')
    await field.setValue('Ship the feature')
    await field.trigger('blur')
    await flushPromises()

    expect(mocks.updateTask).toHaveBeenCalledWith('new-task', { title: 'Ship the feature' })
    expect(mocks.updateItem).not.toHaveBeenCalled()
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('reorders with the pointer and saves the new order once', async () => {
    mocks.reorderItems.mockResolvedValue([])
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([
          { id: 'a', text: 'One', done: false, applicable: true },
          { id: 'b', text: 'Two', done: false, applicable: true },
          { id: 'c', text: 'Three', done: false, applicable: true }
        ])
      }
    })

    const rows = wrapper.findAll('[data-checklist-id]')
    rows.forEach((row, index) => {
      row.element.getBoundingClientRect = () => ({ top: index * 20, height: 20, bottom: index * 20 + 20 })
    })

    await wrapper
      .findAll('.checklist-grip')[0]
      .element.dispatchEvent(new MouseEvent('pointerdown', { button: 0, bubbles: true }))
    // Past the middle of the second row, so the item takes its place.
    window.dispatchEvent(new MouseEvent('pointermove', { clientY: 35 }))
    window.dispatchEvent(new MouseEvent('pointerup'))
    await flushPromises()

    expect(mocks.reorderItems).toHaveBeenCalledTimes(1)
    expect(mocks.reorderItems).toHaveBeenCalledWith('t1', ['b', 'a', 'c'])
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('moves an item with the arrow keys on its handle', async () => {
    mocks.reorderItems.mockResolvedValue([])
    const wrapper = mount(ChecklistPanel, {
      props: {
        task: task([
          { id: 'a', text: 'One', done: false, applicable: true },
          { id: 'b', text: 'Two', done: false, applicable: true },
          { id: 'c', text: 'Three', done: false, applicable: true }
        ])
      }
    })

    await wrapper.findAll('.checklist-grip')[1].trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(mocks.reorderItems).toHaveBeenCalledWith('t1', ['b', 'a', 'c'])

    // The first item has nowhere to go up.
    mocks.reorderItems.mockClear()
    await wrapper.findAll('.checklist-grip')[0].trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(mocks.reorderItems).not.toHaveBeenCalled()
  })
})
