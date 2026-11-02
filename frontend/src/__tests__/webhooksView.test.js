import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  endpoints: vi.fn(),
  createEndpoint: vi.fn(),
  updateEndpoint: vi.fn(),
  removeEndpoint: vi.fn(),
  subscriptions: vi.fn(),
  createSubscription: vi.fn(),
  updateSubscription: vi.fn(),
  removeSubscription: vi.fn(),
  events: vi.fn(),
  event: vi.fn(),
  replay: vi.fn(),
  test: vi.fn(),
  graphsList: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    webhooks: {
      endpoints: mocks.endpoints,
      createEndpoint: mocks.createEndpoint,
      updateEndpoint: mocks.updateEndpoint,
      removeEndpoint: mocks.removeEndpoint,
      subscriptions: mocks.subscriptions,
      createSubscription: mocks.createSubscription,
      updateSubscription: mocks.updateSubscription,
      removeSubscription: mocks.removeSubscription,
      events: mocks.events,
      event: mocks.event,
      replay: mocks.replay,
      test: mocks.test
    },
    graphs: { list: mocks.graphsList }
  }
}))

import WebhooksView from '../views/WebhooksView.vue'
import { store } from '../store'

function endpoint(overrides = {}) {
  return {
    id: 'e1',
    name: 'GitHub pull requests',
    description: 'Triage new PRs',
    kind: 'github',
    secret: 's3cret',
    enabled: true,
    subscription_count: 1,
    event_count: 2,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...overrides
  }
}

function webhookEvent(overrides = {}) {
  return {
    id: 'ev1',
    endpoint_id: 'e1',
    endpoint_name: 'GitHub pull requests',
    source: 'github',
    event_type: 'pull_request',
    delivery_id: 'abc',
    payload: { action: 'opened', pull_request: { title: 'Fix' } },
    headers: {},
    delivery_count: 1,
    created_at: '2026-11-01T00:00:00Z',
    ...overrides
  }
}

function button(wrapper, text) {
  return wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.endpoints.mockResolvedValue([endpoint()])
  mocks.events.mockResolvedValue([webhookEvent()])
  mocks.graphsList.mockResolvedValue([{ id: 'g1', name: 'Triage PR', enabled: true }])
  mocks.subscriptions.mockResolvedValue([])
  mocks.createEndpoint.mockResolvedValue(endpoint({ id: 'e2' }))
  mocks.createSubscription.mockResolvedValue({ id: 's1' })
})

describe('WebhooksView', () => {
  it('shows each endpoint with its inbound URL and kind', async () => {
    const wrapper = mount(WebhooksView)
    await flushPromises()

    expect(wrapper.text()).toContain('GitHub pull requests')
    expect(wrapper.text()).toContain('/api/hooks/github/e1')
    expect(wrapper.text()).toContain('1 workflow(s)')
    expect(wrapper.text()).toContain('secret set')
  })

  it('creates an endpoint from the form', async () => {
    const wrapper = mount(WebhooksView)
    await flushPromises()

    await button(wrapper, 'New endpoint').trigger('click')
    await wrapper.get('#hook-name').setValue('Inbound service')
    await wrapper.get('#hook-secret').setValue('tok')
    await button(wrapper, 'Create endpoint').trigger('click')
    await flushPromises()

    expect(mocks.createEndpoint).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Inbound service', secret: 'tok', kind: 'generic' })
    )
  })

  it('marks a subscription owned by an event trigger node as managed', async () => {
    mocks.subscriptions.mockResolvedValue([
      {
        id: 's-node',
        endpoint_id: 'e1',
        graph_id: 'g1',
        graph_name: 'Triage PR',
        node_id: 't1',
        name: 'Event trigger',
        events: ['pull_request'],
        filters: [],
        enabled: true,
        created_at: '2026-11-01T00:00:00Z',
        updated_at: '2026-11-01T00:00:00Z'
      }
    ])
    const wrapper = mount(WebhooksView)
    await flushPromises()
    await button(wrapper, 'Workflows').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('from graph')
    expect(wrapper.text()).toContain('Managed by its event trigger node')
    expect(button(wrapper, 'Remove')).toBeUndefined()
  })

  it('wires a graph to an endpoint with event types and a payload filter', async () => {
    const wrapper = mount(WebhooksView)
    await flushPromises()

    await button(wrapper, 'Workflows').trigger('click')
    await flushPromises()
    await wrapper.get('#sub-graph-e1').setValue('g1')
    await wrapper.get('#sub-events-e1').setValue('pull_request, issues')
    await button(wrapper, '+ Filter').trigger('click')
    const path = wrapper.findAll('.webhook-filter-row input')[0]
    await path.setValue('action')
    const value = wrapper.findAll('.webhook-filter-row input')[1]
    await value.setValue('opened')
    await button(wrapper, 'Wire workflow').trigger('click')
    await flushPromises()

    expect(mocks.createSubscription).toHaveBeenCalledWith('e1', {
      graph_id: 'g1',
      name: '',
      events: ['pull_request', 'issues'],
      filters: [{ path: 'action', equals: 'opened' }],
      enabled: true
    })
  })

  it('expands an event into its payload and delivery outcome', async () => {
    mocks.event.mockResolvedValue({
      ...webhookEvent(),
      deliveries: [
        {
          id: 'd1',
          event_id: 'ev1',
          subscription_id: 's1',
          subscription_name: 'PR opened',
          graph_id: 'g1',
          graph_name: 'Triage PR',
          graph_execution_id: 'x1',
          status: 'started',
          error: '',
          created_at: '2026-11-01T00:00:00Z'
        }
      ]
    })
    const wrapper = mount(WebhooksView)
    await flushPromises()

    await button(wrapper, 'Events').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('pull_request')
    await button(wrapper, 'Payload').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('"title": "Fix"')
    expect(wrapper.text()).toContain('started')
    expect(wrapper.text()).toContain('Triage PR')
    expect(wrapper.text()).toContain('execution x1')
  })
})
