import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({ sessionsRemove: vi.fn() }))

vi.mock('../api', () => ({
  api: { sessions: { remove: mocks.sessionsRemove } }
}))

import SessionsPanel from '../components/SessionsPanel.vue'
import SessionLinks from '../components/SessionLinks.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const task = {
  id: 't1',
  sessions: [
    {
      id: 's1',
      session_id: 'ses_1',
      label: 'manual repro',
      harness_id: 'opencode2',
      cwd: '/work',
      created_at: new Date().toISOString(),
      links: [
        { id: 'openchamber', label: 'Open in OpenChamber', url: 'http://oc/?session=ses_1' },
        { id: 'command', label: 'Resume command', command: 'cd /work && opencode2 --session ses_1' }
      ]
    }
  ]
}

describe('SessionsPanel', () => {
  it('renders each session with its links and resume command', () => {
    const wrapper = mount(SessionsPanel, { props: { task } })
    expect(wrapper.text()).toContain('manual repro')
    expect(wrapper.text()).toContain('opencode2')
    expect(wrapper.text()).toContain('ses_1')
    expect(wrapper.text()).toContain('/work')
    expect(wrapper.getComponent(SessionLinks).props('links')).toHaveLength(2)
    expect(wrapper.get('a').attributes('href')).toBe('http://oc/?session=ses_1')
  })

  it('prompts when there is nothing recorded', () => {
    const wrapper = mount(SessionsPanel, { props: { task: { id: 't1', sessions: [] } } })
    expect(wrapper.text()).toContain('No sessions recorded')
    expect(wrapper.text()).toContain('agentic session add t1')
  })

  it('removes a session when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.sessionsRemove.mockResolvedValue(null)
    const wrapper = mount(SessionsPanel, { props: { task } })
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.sessionsRemove).toHaveBeenCalledWith('t1', 's1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('keeps the session when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    const wrapper = mount(SessionsPanel, { props: { task } })
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.sessionsRemove).not.toHaveBeenCalled()
  })

  it('reports a failed removal', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.sessionsRemove.mockRejectedValue(new Error('nope'))
    const wrapper = mount(SessionsPanel, { props: { task } })
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'nope', isError: true })
  })
})
