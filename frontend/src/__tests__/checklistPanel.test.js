import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  addItem: vi.fn(),
  updateItem: vi.fn(),
  removeItem: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: {
      addChecklistItem: mocks.addItem,
      updateChecklistItem: mocks.updateItem,
      removeChecklistItem: mocks.removeItem
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
})
