import { afterEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

import TimelinePanel from '../components/TimelinePanel.vue'

const task = (over = {}) => ({
  id: 't1',
  title: 'A task',
  status: 'done',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T02:00:00Z',
  ...over
})

const statusEvent = (from, to, created_at) => ({
  id: `${from}-${to}`,
  type: 'updated',
  message: `Updated: status`,
  created_at,
  client: 'web',
  actor: 'human',
  data_json: { changes: { status: { from, to } } }
})

describe('TimelinePanel', () => {
  it('shows nothing yet without events', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [], task: task({ status: 'open' }) } })
    expect(wrapper.text()).toContain('Nothing yet.')
    expect(wrapper.find('.status-spans').exists()).toBe(false)
  })

  it('breaks the task span down by status, with icons and shares', () => {
    const events = [
      statusEvent('open', 'in_progress', '2026-01-01T01:00:00Z'),
      statusEvent('in_progress', 'done', '2026-01-01T02:00:00Z')
    ]
    const wrapper = mount(TimelinePanel, { props: { events, task: task() } })
    const spans = wrapper.findAll('.status-span')
    expect(spans.length).toBe(3)
    expect(spans.map((span) => span.find('.task-status').attributes('aria-label'))).toEqual([
      'Open',
      'In progress',
      'Done'
    ])
    expect(spans.every((span) => span.text().includes('%'))).toBe(true)
  })

  it('can label itself and link each event to its task, for a timeline across tasks', () => {
    const events = [
      {
        id: 'e1',
        task_id: 't1',
        task_title: 'A task',
        type: 'run_started',
        message: 'Agent run: do the thing',
        created_at: '2026-01-01T01:00:00Z',
        client: 'cli',
        actor: 'agent',
        data_json: {}
      }
    ]
    const wrapper = mount(TimelinePanel, {
      props: { events, heading: 'Yesterday', showTask: true },
      global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } }
    })
    expect(wrapper.get('.panel-head').text()).toBe('Yesterday')
    expect(wrapper.get('a[href="/task/t1"]').text()).toBe('A task')
  })
})
