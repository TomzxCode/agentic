import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DeadlinePicker from '../components/DeadlinePicker.vue'
import StatusIcon from '../components/StatusIcon.vue'
import PriorityIcon from '../components/PriorityIcon.vue'
import SessionLinks from '../components/SessionLinks.vue'
import TimelinePanel from '../components/TimelinePanel.vue'
import { store } from '../store'

afterEach(() => {
  vi.unstubAllGlobals()
  store.toast = null
})

describe('StatusIcon', () => {
  it('renders the status class and an accessible label', () => {
    const cases = [
      ['done', 'st-done'],
      ['blocked', 'st-blocked'],
      ['in_progress', 'st-in_progress'],
      ['archived', 'st-archived'],
      ['open', 'st-open']
    ]
    for (const [status, cls] of cases) {
      const wrapper = mount(StatusIcon, { props: { status, label: 'L' } })
      expect(wrapper.classes()).toContain(cls)
      expect(wrapper.attributes('title')).toBe('L')
      expect(wrapper.attributes('aria-label')).toBe('L')
    }
  })

  it('defaults to open and uses the status when no label is given', () => {
    const wrapper = mount(StatusIcon)
    expect(wrapper.classes()).toContain('st-open')
    expect(wrapper.attributes('title')).toBe('open')
  })
})

describe('PriorityIcon', () => {
  it('renders the priority class and an accessible label', () => {
    const cases = [
      [0, 'prio-low'],
      [1, 'prio-medium'],
      [2, 'prio-high'],
      [3, 'prio-urgent']
    ]
    for (const [priority, cls] of cases) {
      const wrapper = mount(PriorityIcon, { props: { priority, label: 'L' } })
      expect(wrapper.classes()).toContain(cls)
      expect(wrapper.attributes('title')).toBe('L')
      expect(wrapper.attributes('aria-label')).toBe('L')
    }
  })

  it('defaults to high and uses the level when no label is given', () => {
    const wrapper = mount(PriorityIcon)
    expect(wrapper.classes()).toContain('prio-high')
    expect(wrapper.attributes('title')).toBe('high')
  })
})

describe('SessionLinks', () => {
  it('renders nothing when there are no links', () => {
    const wrapper = mount(SessionLinks, { props: { links: [] } })
    expect(wrapper.find('.session-links').exists()).toBe(false)
  })

  it('renders url links and the copyable command', () => {
    const links = [
      { id: 'openchamber', label: 'Open in OpenChamber', url: 'http://oc/?session=1' },
      { id: 'command', label: 'Resume command', command: 'opencode --session 1' }
    ]
    const wrapper = mount(SessionLinks, { props: { links } })
    expect(wrapper.get('a').attributes('href')).toBe('http://oc/?session=1')
    expect(wrapper.get('.cmd').text()).toContain('opencode --session 1')
  })

  it('copies the resume command and notifies', async () => {
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(SessionLinks, { props: { links: [{ id: 'command', label: 'R', command: 'go' }] } })
    await wrapper.get('button').trigger('click')
    expect(writeText).toHaveBeenCalledWith('go')
    expect(store.toast).toEqual({ message: 'Copied to clipboard', isError: false })
  })

  it('notifies when copying fails', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('nope')) } })
    const wrapper = mount(SessionLinks, { props: { links: [{ id: 'command', label: 'R', command: 'go' }] } })
    await wrapper.get('button').trigger('click')
    expect(store.toast).toEqual({ message: 'Copy failed', isError: true })
  })

  it('hides the command block in compact mode', () => {
    const wrapper = mount(SessionLinks, {
      props: { compact: true, links: [{ id: 'command', label: 'R', command: 'go' }] }
    })
    expect(wrapper.find('.cmd').exists()).toBe(false)
    expect(wrapper.get('button').text()).toContain('Resume')
  })
})

describe('TimelinePanel', () => {
  const event = (over) => ({
    id: 'e1',
    type: 'updated',
    message: 'Updated: title',
    created_at: new Date().toISOString(),
    client: 'web',
    actor: 'human',
    data_json: { changes: { title: { from: 'A', to: 'B' } } },
    ...over
  })

  it('shows an empty state', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [] } })
    expect(wrapper.text()).toContain('Nothing yet')
    expect(wrapper.find('.gantt').exists()).toBe(false)
  })

  it('renders a before/after change', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [event()] } })
    expect(wrapper.text()).toContain('title')
    expect(wrapper.text()).toContain('A')
    expect(wrapper.text()).toContain('B')
  })

  it('draws a one-row gantt with a marker per event', () => {
    const task = {
      id: 't1',
      title: 'Task One',
      status: 'in_progress',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T12:00:00Z'
    }
    const wrapper = mount(TimelinePanel, { props: { events: [event()], task } })
    expect(wrapper.find('.gantt').exists()).toBe(true)
    expect(wrapper.find('.gantt.compact').exists()).toBe(true)
    expect(wrapper.findAll('.gantt-marker')).toHaveLength(1)
    expect(wrapper.find('.gantt-bar').exists()).toBe(true)
  })

  it('jumps to the matching event when its marker is clicked', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    try {
      const task = {
        id: 't1',
        title: 'Task One',
        status: 'in_progress',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T12:00:00Z'
      }
      const wrapper = mount(TimelinePanel, { props: { events: [event()], task } })
      await wrapper.find('button.gantt-marker').trigger('click')
      await flushPromises()
      expect(scroll).toHaveBeenCalled()
      expect(wrapper.find('.timeline li.highlight').exists()).toBe(true)
    } finally {
      delete Element.prototype.scrollIntoView
    }
  })

  it('resolves relationship ids through the store, shows empty values, and truncates long text', () => {
    store.repositories = [{ id: 'r1', name: 'Repo One' }]
    const long = 'x'.repeat(200)
    const wrapper = mount(TimelinePanel, {
      props: {
        events: [
          event({
            data_json: {
              changes: { repository_id: { from: null, to: 'r1' }, summary: { from: '', to: long } }
            }
          })
        ]
      }
    })
    expect(wrapper.text()).toContain('Repo One')
    expect(wrapper.text()).toContain('(empty)')
    expect(wrapper.text()).toContain('…')
  })

  it('shows how the event entered the system', () => {
    const wrapper = mount(TimelinePanel, {
      props: { events: [event({ client: 'cli', actor: 'agent' })] }
    })
    expect(wrapper.text()).toContain('cli · agent')
  })

  it('ignores malformed change data', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [event({ data_json: { changes: 'nope' } })] } })
    expect(wrapper.find('.changes').exists()).toBe(false)
  })
})

describe('DeadlinePicker', () => {
  it('shows the placeholder when no deadline is set', () => {
    const wrapper = mount(DeadlinePicker, { props: { modelValue: null } })
    expect(wrapper.find('.deadline-btn').text()).toContain('Set deadline')
    expect(wrapper.find('.badge').exists()).toBe(false)
  })

  it('shows an overdue state and clears on the clear button', async () => {
    const wrapper = mount(DeadlinePicker, {
      props: { modelValue: new Date(Date.now() - 3_600_000).toISOString() }
    })
    expect(wrapper.find('.badge').text()).toContain('Overdue')

    await wrapper.find('.chip-x').trigger('click')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([null])
  })

  it('opens an input and emits the picked value as ISO', async () => {
    const wrapper = mount(DeadlinePicker, { props: { modelValue: null } })
    await wrapper.find('.deadline-btn').trigger('click')
    const input = wrapper.find('input[type="datetime-local"]')
    expect(input.exists()).toBe(true)

    await input.setValue('2030-01-02T09:30')
    await input.trigger('keydown', { key: 'Enter' })
    const [emitted] = wrapper.emitted('update:modelValue')[0]
    expect(new Date(emitted).toISOString()).toBe(emitted)
    expect(new Date(emitted).getMinutes()).toBe(30)
  })

  it('defaults a new deadline to 17:00 so only the date needs choosing', async () => {
    const wrapper = mount(DeadlinePicker, { props: { modelValue: null } })
    await wrapper.find('.deadline-btn').trigger('click')
    expect(wrapper.find('input[type="datetime-local"]').element.value).toMatch(/T17:00$/)
  })

  it('keeps an existing deadline time when reopening', async () => {
    const iso = new Date(2030, 4, 1, 8, 15).toISOString()
    const wrapper = mount(DeadlinePicker, { props: { modelValue: iso } })
    await wrapper.find('.deadline-btn').trigger('click')
    expect(wrapper.find('input[type="datetime-local"]').element.value).toBe('2030-05-01T08:15')
  })

  it('does not set a deadline when dismissed without a change', async () => {
    const wrapper = mount(DeadlinePicker, { props: { modelValue: null } })
    await wrapper.find('.deadline-btn').trigger('click')
    await wrapper.find('input[type="datetime-local"]').trigger('blur')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
