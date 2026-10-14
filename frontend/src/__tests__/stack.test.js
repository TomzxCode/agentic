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
  remove: vi.fn(),
  updateTask: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    stack: {
      list: mocks.list,
      history: mocks.history,
      current: mocks.current,
      push: mocks.push,
      pop: mocks.pop,
      promote: mocks.promote,
      reorder: mocks.reorder,
      update: mocks.update,
      remove: mocks.remove
    },
    tasks: { update: mocks.updateTask }
  }
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import StackView from '../views/StackView.vue'
import { formatTimestamp, moveItem, targetIndexAt } from '../stack'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

// jsdom has no PointerEvent, so dispatch a plain Event and attach the fields
// the handler reads.
function fire(el, type, props = {}) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, props)
  el.dispatchEvent(event)
}

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
  mocks.updateTask.mockResolvedValue({})
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
    // Each row reuses the icon status picker (editable in place).
    expect(wrapper.findAll('.task-status-select').length).toBe(2)
  })

  it('changes a task status from the stack', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.findAll('.task-status-select .ss-trigger')[0].trigger('click')
    await flushPromises()
    const blocked = wrapper.findAll('.ss-option').find((option) => option.text().includes('Blocked'))
    await blocked.trigger('click')
    await flushPromises()

    expect(mocks.updateTask).toHaveBeenCalledWith('t1', { status: 'blocked' })
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

  it('promotes and removes a row from its actions', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    const row = wrapper.findAll('.stack-row')[1]
    await row.find('[title="Promote to current (Home)"]').trigger('click')
    expect(mocks.promote).toHaveBeenCalledWith('s2')
    await row.find('[title="Remove from the stack (Delete)"]').trigger('click')
    expect(mocks.remove).toHaveBeenCalledWith('s2')
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

  function midpoints(wrapper) {
    const rows = wrapper.findAll('.stack-row')
    rows[0].element.getBoundingClientRect = () => ({ top: 0, height: 20 })
    rows[1].element.getBoundingClientRect = () => ({ top: 20, height: 20 })
    return rows
  }

  it('selects a row on click without navigating, and opens it via the link', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.findAll('.stack-row')[1].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.stack-row')[1].classes()).toContain('selected')

    // The task page is reached through the row's open link, not the row itself.
    expect(wrapper.findAll('.stack-row')[1].find('.stack-actions a').attributes('href')).toBe('/task/t2')
  })

  it('edits the title inline', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.findAll('.stack-title')[0].trigger('click')
    await flushPromises()
    const input = wrapper.find('.inline-input')
    expect(input.exists()).toBe(true)

    await input.setValue('Renamed task')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(mocks.update).toHaveBeenCalledWith('s1', { title: 'Renamed task' })
  })

  it('reorders the clicked row with the arrow keys', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()

    await wrapper.findAll('.stack-row')[1].trigger('click')
    await flushPromises()
    await wrapper.find('.stack-page').trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()

    expect(mocks.reorder).toHaveBeenCalledWith('s2', 0)
  })

  it('counts the current task duration up every second', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    try {
      const wrapper = mount(StackView, stub)
      await flushPromises()
      expect(wrapper.find('.stack-row .stack-duration').text()).toBe('1m 30s')

      vi.advanceTimersByTime(5000)
      await flushPromises()
      expect(wrapper.find('.stack-row .stack-duration').text()).toBe('1m 35s')

      // A non-current row's duration is fixed.
      expect(wrapper.findAll('.stack-duration')[1].text()).toBe('0m 00s')
    } finally {
      vi.useRealTimers()
    }
  })

  it('reorders rows by dragging with the mouse', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()
    const rows = midpoints(wrapper)

    fire(rows[0].element, 'pointerdown', { clientY: 5, pointerType: 'mouse' })
    fire(window, 'pointermove', { clientY: 40 }) // below the second row's midpoint
    fire(window, 'pointerup', {})
    await flushPromises()

    expect(mocks.reorder).toHaveBeenCalledWith('s1', 1)
  })

  it('drags from the handle on touch but not from the row body', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()
    const rows = midpoints(wrapper)

    // A touch on the row body must not start a drag (the list has to scroll).
    fire(rows[0].element, 'pointerdown', { clientY: 5, pointerType: 'touch' })
    fire(window, 'pointermove', { clientY: 40 })
    fire(window, 'pointerup', {})
    await flushPromises()
    expect(mocks.reorder).not.toHaveBeenCalled()

    // The handle does start one.
    fire(rows[0].find('.stack-handle').element, 'pointerdown', { clientY: 5, pointerType: 'touch' })
    fire(window, 'pointermove', { clientY: 40 })
    fire(window, 'pointerup', {})
    await flushPromises()
    expect(mocks.reorder).toHaveBeenCalledWith('s1', 1)
  })

  it('ignores a drag while filtering', async () => {
    const wrapper = mount(StackView, stub)
    await flushPromises()
    const rows = midpoints(wrapper)

    await wrapper.find('input.input').setValue('first')
    fire(rows[0].element, 'pointerdown', { clientY: 5, pointerType: 'mouse' })
    fire(window, 'pointermove', { clientY: 40 })
    fire(window, 'pointerup', {})
    await flushPromises()

    expect(mocks.reorder).not.toHaveBeenCalled()
  })
})

describe('stack drag helpers', () => {
  it('targetIndexAt picks the row the pointer is above', () => {
    expect(targetIndexAt([10, 30, 50], 5)).toBe(0)
    expect(targetIndexAt([10, 30, 50], 20)).toBe(1)
    expect(targetIndexAt([10, 30, 50], 45)).toBe(2)
    expect(targetIndexAt([10, 30, 50], 100)).toBe(2) // past the end lands on the last row
    expect(targetIndexAt([], 5)).toBe(0)
  })

  it('moveItem moves an item without mutating the input', () => {
    const items = ['a', 'b', 'c']
    expect(moveItem(items, 0, 2)).toEqual(['b', 'c', 'a'])
    expect(moveItem(items, 2, 0)).toEqual(['c', 'a', 'b'])
    expect(items).toEqual(['a', 'b', 'c'])
  })
})

describe('formatTimestamp', () => {
  const now = new Date('2026-06-15T14:30:00')

  it('shows only the minutes within the same hour', () => {
    expect(formatTimestamp('2026-06-15T14:05:00', now)).toBe('05')
  })

  it('shows HH:MM in the same day but another hour', () => {
    expect(formatTimestamp('2026-06-15T09:07:00', now)).toBe('09:07')
  })

  it('shows DD HH:MM in the same month but another day', () => {
    expect(formatTimestamp('2026-06-02T09:07:00', now)).toBe('02 09:07')
  })

  it('shows MM-DD HH:MM in the same year but another month', () => {
    expect(formatTimestamp('2026-03-02T09:07:00', now)).toBe('03-02 09:07')
  })

  it('shows YYYY-MM-DD HH:MM in another year', () => {
    expect(formatTimestamp('2025-12-31T23:07:00', now)).toBe('2025-12-31 23:07')
  })

  it('shows an em dash for a missing or unparseable value', () => {
    expect(formatTimestamp(null, now)).toBe('—')
    expect(formatTimestamp('nope', now)).toBe('—')
  })
})
