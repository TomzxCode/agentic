import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// WorktreesPanel renders a <router-link>; stub it so mounting does not warn
// about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  taskUpdate: vi.fn(),
  associate: vi.fn(),
  unassociate: vi.fn(),
  itemRefresh: vi.fn(),
  itemUpdate: vi.fn(),
  worktreeCreate: vi.fn(),
  worktreeRemove: vi.fn(),
  refreshContext: vi.fn(),
  refreshSummary: vi.fn(),
  settingsGet: vi.fn(),
  changeCreate: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.taskUpdate, associate: mocks.associate, unassociate: mocks.unassociate },
    items: { refresh: mocks.itemRefresh, update: mocks.itemUpdate },
    worktrees: { create: mocks.worktreeCreate, remove: mocks.worktreeRemove },
    runs: { refreshContext: mocks.refreshContext, refreshSummary: mocks.refreshSummary },
    settings: { get: mocks.settingsGet },
    changes: { create: mocks.changeCreate }
  }
}))

import RepositorySelect from '../components/RepositorySelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RepositorySelect', () => {
  const repositories = [
    { id: 'a', name: 'Alpha' },
    { id: 'b', name: 'Beta' }
  ]

  it('renders the selected chips and the empty label', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['b'], repositories } })
    expect(wrapper.get('.chip').text()).toContain('Beta')

    const empty = mount(RepositorySelect, { props: { modelValue: [], repositories: [] } })
    expect(empty.text()).toBe('no repositories')
  })

  it('emits an added repository and removes one', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['a'], repositories } })
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'b')
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]])

    await wrapper.get('.chip-x').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']], [[]]])
  })

  it('exposes activate for the command palette', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: [], repositories } })
    wrapper.vm.activate()
    expect(wrapper.findComponent(SearchSelect).exists()).toBe(true)
  })
})
