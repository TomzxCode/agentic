import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  apply: vi.fn(),
  tasksList: vi.fn(),
  tagsList: vi.fn(),
  peopleList: vi.fn(),
  repositoriesList: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    checklistTemplates: {
      list: mocks.list,
      create: mocks.create,
      update: mocks.update,
      remove: mocks.remove,
      apply: mocks.apply
    },
    tasks: { list: mocks.tasksList },
    tags: { list: mocks.tagsList },
    people: { list: mocks.peopleList },
    repositories: { list: mocks.repositoriesList }
  }
}))

import SettingsChecklists from '../components/SettingsChecklists.vue'
import { store } from '../store'

const TEMPLATE = {
  id: 'c1',
  name: 'Feature',
  description: '',
  rules: [{ field: 'tags', op: 'has_any', values: ['feature'] }],
  items: ['Announce the feature', 'Write documentation'],
  applied_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

function button(wrapper, label) {
  return wrapper.findAll('button').find((entry) => entry.text() === label)
}

beforeEach(() => {
  vi.clearAllMocks()
  store.tags = [{ name: 'feature', count: 3 }]
  store.people = []
  store.repositories = []
  mocks.list.mockResolvedValue([TEMPLATE])
  mocks.create.mockResolvedValue(TEMPLATE)
  mocks.update.mockResolvedValue(TEMPLATE)
  mocks.apply.mockResolvedValue({ applied: 4 })
  mocks.remove.mockResolvedValue(null)
  mocks.tasksList.mockResolvedValue([])
  mocks.tagsList.mockResolvedValue([{ name: 'feature', count: 3 }])
  mocks.peopleList.mockResolvedValue([])
  mocks.repositoriesList.mockResolvedValue([])
  vi.spyOn(store, 'notify').mockImplementation(() => {})
})

describe('SettingsChecklists', () => {
  it('lists a template with its rules, items, and applied count', async () => {
    const wrapper = mount(SettingsChecklists)
    await flushPromises()

    expect(wrapper.text()).toContain('Feature')
    expect(wrapper.text()).toContain('Tags has any of feature')
    expect(wrapper.text()).toContain('2 items')
    expect(wrapper.text()).toContain('2 applied')
  })

  it('edits a template and saves its rules and items', async () => {
    const wrapper = mount(SettingsChecklists)
    await flushPromises()

    await button(wrapper, 'Edit').trigger('click')
    await wrapper.get('input.input').setValue('Feature release')
    await wrapper.get('textarea').setValue('Announce the feature\nWrite documentation\nUpdate the changelog')
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()

    expect(mocks.update).toHaveBeenCalledWith('c1', {
      name: 'Feature release',
      description: '',
      rules: [{ field: 'tags', op: 'has_any', values: ['feature'] }],
      items: ['Announce the feature', 'Write documentation', 'Update the changelog']
    })
  })

  it('creates a new checklist with a default status rule', async () => {
    const wrapper = mount(SettingsChecklists)
    await flushPromises()

    await button(wrapper, 'New checklist').trigger('click')
    await wrapper.get('input.input').setValue('Blocked work')
    await button(wrapper, 'Add rule').trigger('click')
    await wrapper.get('textarea').setValue('Chase the blocker')
    await button(wrapper, 'Save').trigger('click')
    await flushPromises()

    expect(mocks.create).toHaveBeenCalledWith({
      name: 'Blocked work',
      description: '',
      rules: [{ field: 'status', op: 'is_any', values: ['open'] }],
      items: ['Chase the blocker']
    })
  })

  it('applies a template to matching tasks', async () => {
    const wrapper = mount(SettingsChecklists)
    await flushPromises()

    await button(wrapper, 'Apply now').trigger('click')
    await flushPromises()

    expect(mocks.apply).toHaveBeenCalledWith('c1')
    expect(store.notify).toHaveBeenCalledWith('Added items to 4 tasks')
  })
})
