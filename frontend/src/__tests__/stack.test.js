import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  history: vi.fn(),
  current: vi.fn(),
  push: vi.fn(),
  pop: vi.fn(),
  promote: vi.fn(),
  reorder: vi.fn(),
  update: vi.fn(),
  remove: vi.fn()
}))

vi.mock('../api', () => ({ api: { stack: mocks } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import StackView from '../views/StackView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

function entry(overrides = {}) {
  return {
    id: 's1',
    task_id: 't1',
    task: { title: 'First', description: '', status: 'open' },
    position: 0,
    is_current: true,
    created_at: '2026-01-01T00:00:00',
    deleted_at: null,
    started_at: '2026-01-01T00:00:00',
    last_current: '2026-01-01T00:10:00',
    duration: 90,
    execution_count: 2,
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.list.mockResolvedValue([
    entry(),
    entry({
      id: 's2',
      task_id: 't2',
      task: { title: 'Second', description: 'note', status: 'in_progress' },
      position: 1,
      is_current: false,
      duration: 0,
      execution_count: 0
    })
  ])
  mocks.history.mockResolvedValue([])
  mocks.push.mockResolvedValue([])
  mocks.pop.mockResolvedValue([])
  mocks.promote.mockResolvedValue([])
  mocks.reorder.mockResolvedValue([])
  mocks.update.mockResolvedValue([])
  mocks.remove.mockResolvedValue(null)
})

describe('StackView', () => {
  it('lists the stack with the current task first', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    expect(mocks.list).toHaveBeenCalled()
    const rows = wrapper.findAll('.stack-row')
    expect(rows.length).toBe(2)
    expect(rows[0].classes()).toContain('current')
    expect(wrapper.text()).toContain('First')
    expect(wrapper.text()).toContain('Second')
    expect(wrapper.text()).toContain('×2')
    expect(wrapper.text()).toContain('1m 30s')
    // Each row shows its task status (open, in progress, blocked).
    expect(wrapper.findAll('.stack-status').map((b) => b.text())).toEqual(['Open', 'In progress'])
  })

  it('adds to the top on Enter and after the current on Shift+Enter', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    const input = wrapper.find('input.input')
    await input.setValue('New task')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith({ title: 'New task', position: 'top' })

    await input.setValue('Next task')
    await input.trigger('keydown', { key: 'Enter', shiftKey: true })
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith({ title: 'Next task', position: 'next' })
  })

  it('filters the list as you type', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.find('input.input').setValue('sec')
    await flushPromises()
    expect(wrapper.findAll('.stack-row').length).toBe(1)
    expect(wrapper.text()).toContain('Second')
  })

  it('pops the current task and removes the selected one', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    const secondRowButtons = wrapper.findAll('.stack-row')[1].findAll('.stack-actions .btn')
    await secondRowButtons[0].trigger('click')
    expect(mocks.promote).toHaveBeenCalledWith('s2')
    await secondRowButtons[1].trigger('click')
    expect(mocks.remove).toHaveBeenCalledWith('s2')
    await flushPromises()

    await wrapper.find('.stack-footer .btn').trigger('click')
    expect(mocks.pop).toHaveBeenCalled()
  })

  it('selects with the arrow keys and removes with Delete', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.find('.stack-page').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(wrapper.findAll('.stack-row')[0].classes()).toContain('selected')

    await wrapper.find('.stack-page').trigger('keydown', { key: 'Delete' })
    await flushPromises()
    expect(mocks.remove).toHaveBeenCalledWith('s1')
  })

  it('shows the description editor for the selected task and saves on blur', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.findAll('.stack-row')[1].trigger('click')
    await flushPromises()
    const textarea = wrapper.find('.stack-desc textarea')
    expect(textarea.exists()).toBe(true)

    await textarea.setValue('updated note')
    await textarea.trigger('blur')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledWith('s2', { description: 'updated note' })
  })

  it('toggles the history panel', async () => {
    mocks.history.mockResolvedValue([
      entry({ id: 's9', task_id: 't9', task: { title: 'Done task' }, is_current: false })
    ])
    const wrapper = mount(StackView, stub)
    await flushPromises()

    const historyButton = wrapper.findAll('.page-head .btn').find((b) => b.text().includes('History'))
    await historyButton.trigger('click')
    await flushPromises()
    expect(mocks.history).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Done task')
  })
})
