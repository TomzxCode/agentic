import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)
afterEach(() => vi.useRealTimers())

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  run: vi.fn(),
  runs: vi.fn(),
  executions: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    schedules: {
      list: mocks.list,
      create: mocks.create,
      update: mocks.update,
      remove: mocks.remove,
      run: mocks.run,
      runs: mocks.runs,
      executions: mocks.executions
    }
  }
}))

import SchedulesView from '../views/SchedulesView.vue'
import { store } from '../store'

const stub = { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }

function task(overrides = {}) {
  return {
    id: 's1',
    name: 'Nightly backup',
    command: '~/scripts/backup.sh',
    schedule: '0 9 * * *',
    cwd: null,
    timezone: 'UTC',
    enabled: true,
    last_run_at: '2026-01-01T09:00:00Z',
    next_run_at: '2026-01-02T09:00:00Z',
    last_status: 'succeeded',
    last_exit_code: 0,
    ...overrides
  }
}

function clickButton(wrapper, label) {
  const button = wrapper.findAll('button').find((b) => b.text() === label)
  expect(button, `button "${label}"`).toBeTruthy()
  return button.trigger('click')
}

function execution(overrides = {}) {
  return {
    id: 'r1',
    scheduled_task_id: 's1',
    task_name: 'Nightly backup',
    task_command: '~/scripts/backup.sh',
    status: 'succeeded',
    exit_code: 0,
    output: 'backup done\n',
    started_at: '2026-01-01T09:00:00Z',
    ended_at: '2026-01-01T09:00:05Z',
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.list.mockResolvedValue([task()])
  mocks.runs.mockResolvedValue([
    {
      id: 'r1',
      scheduled_task_id: 's1',
      status: 'succeeded',
      exit_code: 0,
      output: 'backup done\n',
      started_at: '2026-01-01T09:00:00Z',
      ended_at: '2026-01-01T09:00:05Z'
    }
  ])
  mocks.executions.mockResolvedValue([execution()])
  global.confirm = vi.fn(() => true)
})

describe('SchedulesView', () => {
  it('lists scheduled tasks with their schedule and last status', async () => {
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    expect(mocks.list).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Nightly backup')
    expect(wrapper.text()).toContain('0 9 * * *')
    expect(wrapper.text()).toContain('~/scripts/backup.sh')
    expect(wrapper.text()).toContain('succeeded')
    expect(wrapper.text()).toContain('next 2026-01-02 09:00')
  })

  it('shows the next run in the task zone and marks a paused task', async () => {
    mocks.list.mockResolvedValue([
      task({ timezone: 'Asia/Tokyo' }),
      task({ id: 's2', name: 'Paused', enabled: false, next_run_at: null })
    ])
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('next 2026-01-02 18:00')
    expect(wrapper.text()).toContain('paused')
  })

  it('hides the form until New scheduled task is clicked, and Cancel closes it', async () => {
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    expect(wrapper.find('#sched-name').exists()).toBe(false)
    await clickButton(wrapper, 'New scheduled task')
    expect(wrapper.find('#sched-name').exists()).toBe(true)
    expect(wrapper.findAll('.sched-next li')).toHaveLength(5)
    await clickButton(wrapper, 'Cancel')
    expect(wrapper.find('#sched-name').exists()).toBe(false)
  })

  it('refreshes the list on a timer so a run the scheduler starts appears', async () => {
    vi.useFakeTimers()
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    const calls = mocks.list.mock.calls.length
    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()
    expect(mocks.list.mock.calls.length).toBeGreaterThan(calls)
    wrapper.unmount()
  })

  it('computes the next five runs in the browser, with no preview request', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'New scheduled task')
    await wrapper.find('#sched-timezone').setValue('UTC')
    const times = wrapper.findAll('.sched-next li')
    expect(times).toHaveLength(5)
    expect(times[0].text()).toContain('2026-01-01 09:00')
    expect(times[4].text()).toContain('2026-01-05 09:00')
  })

  it('recomputes the runs when the schedule or timezone changes', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'New scheduled task')
    await wrapper.find('#sched-schedule').setValue('*/15 * * * *')
    await wrapper.find('#sched-timezone').setValue('UTC')
    expect(wrapper.findAll('.sched-next li')[0].text()).toContain('2026-01-01 00:15')
    await wrapper.find('#sched-timezone').setValue('Asia/Tokyo')
    expect(wrapper.findAll('.sched-next li')[0].text()).toContain('2026-01-01 09:15')
    await wrapper.find('#sched-schedule').setValue('nope')
    expect(wrapper.findAll('.sched-next li')).toHaveLength(0)
    expect(wrapper.text()).toContain('A schedule needs 5 fields')
  })

  it('shows every execution across schedules in the Executions tab', async () => {
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Executions')
    await flushPromises()
    expect(mocks.executions).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Nightly backup')
    expect(wrapper.text()).toContain('succeeded')
    await clickButton(wrapper, 'Show output')
    expect(wrapper.text()).toContain('backup done')
  })

  it('shows an empty state when there are none', async () => {
    mocks.list.mockResolvedValue([])
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('No scheduled tasks yet')
  })

  it('creates a scheduled task from the form', async () => {
    mocks.create.mockResolvedValue(task())
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'New scheduled task')
    await wrapper.find('#sched-name').setValue('Nightly backup')
    await wrapper.find('#sched-schedule').setValue('0 9 * * *')
    await wrapper.find('#sched-command').setValue('~/scripts/backup.sh')
    await wrapper.find('#sched-cwd').setValue('/home/me/project')
    await clickButton(wrapper, 'Create scheduled task')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Nightly backup',
        command: '~/scripts/backup.sh',
        schedule: '0 9 * * *',
        cwd: '/home/me/project',
        timezone: expect.any(String),
        enabled: true
      })
    )
  })

  it('validates the form before creating', async () => {
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'New scheduled task')
    await clickButton(wrapper, 'Create scheduled task')
    await flushPromises()
    expect(mocks.create).not.toHaveBeenCalled()
    expect(store.toast?.message).toMatch(/required/)
  })

  it('edits an existing task', async () => {
    mocks.update.mockResolvedValue(task({ name: 'Renamed' }))
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Edit')
    await wrapper.find('#sched-s1-name').setValue('Renamed')
    await clickButton(wrapper, 'Save changes')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledWith('s1', expect.objectContaining({ name: 'Renamed' }))
  })

  it('keeps the new-task draft when a row edit form opens', async () => {
    mocks.update.mockResolvedValue(task())
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'New scheduled task')
    await wrapper.find('#sched-name').setValue('Half-typed')
    // Opening a row's edit form must not disturb the new-task draft.
    await clickButton(wrapper, 'Edit')
    expect(wrapper.find('#sched-name').element.value).toBe('Half-typed')
    expect(wrapper.find('#sched-s1-name').element.value).toBe('Nightly backup')
    await wrapper.find('#sched-s1-name').setValue('Renamed')
    expect(wrapper.find('#sched-name').element.value).toBe('Half-typed')
    // Saving the edit shuts its form but leaves the new-task draft in place.
    await clickButton(wrapper, 'Save changes')
    await flushPromises()
    expect(wrapper.find('#sched-name').element.value).toBe('Half-typed')
  })

  it('keeps each row edit draft when another row is opened', async () => {
    mocks.list.mockResolvedValue([task(), task({ id: 's2', name: 'Other', command: 'echo other' })])
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Edit')
    await wrapper.find('#sched-s1-name').setValue('First edited')
    await clickButton(wrapper, 'Edit')
    await wrapper.find('#sched-s2-name').setValue('Second edited')
    expect(wrapper.find('#sched-s1-name').element.value).toBe('First edited')
    expect(wrapper.find('#sched-s2-name').element.value).toBe('Second edited')
  })

  it('pauses and deletes a task', async () => {
    mocks.update.mockResolvedValue(task({ enabled: false }))
    mocks.remove.mockResolvedValue(null)
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Pause')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledWith('s1', { enabled: false })
    await clickButton(wrapper, 'Delete')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(mocks.remove).toHaveBeenCalledWith('s1')
  })

  it('runs a task now and reloads after the poll', async () => {
    mocks.run.mockResolvedValue({ id: 'r1', status: 'running' })
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Run now')
    await flushPromises()
    expect(mocks.run).toHaveBeenCalledWith('s1')
    expect(mocks.runs).toHaveBeenCalledWith('s1')
    // The poll runs once more (bounded, since the mocked run has finished).
    await new Promise((resolve) => setTimeout(resolve, 1600))
    expect(mocks.list.mock.calls.length).toBeGreaterThan(1)
  })

  it('opens a run history with output', async () => {
    const wrapper = mount(SchedulesView, stub)
    await flushPromises()
    await clickButton(wrapper, 'Run history')
    await flushPromises()
    expect(mocks.runs).toHaveBeenCalledWith('s1')
    expect(wrapper.text()).toContain('backup done')
    expect(wrapper.text()).toContain('exit 0')
  })
})
