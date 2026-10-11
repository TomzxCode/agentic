import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusIcon from '../components/StatusIcon.vue'
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
    data_json: { changes: { title: { from: 'A', to: 'B' } } },
    ...over
  })

  it('shows an empty state', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [] } })
    expect(wrapper.text()).toContain('Nothing yet')
  })

  it('renders a before/after change', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [event()] } })
    expect(wrapper.text()).toContain('title')
    expect(wrapper.text()).toContain('A')
    expect(wrapper.text()).toContain('B')
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

  it('ignores malformed change data', () => {
    const wrapper = mount(TimelinePanel, { props: { events: [event({ data_json: { changes: 'nope' } })] } })
    expect(wrapper.find('.changes').exists()).toBe(false)
  })
})
