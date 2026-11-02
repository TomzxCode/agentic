import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { mount } from '@vue/test-utils'
import StatusBar from '../components/StatusBar.vue'
import { debugStats, refreshDebugRequests, clearApiCalls, clearDbQueries } from '../debug.js'

vi.mock('../debug.js', async () => ({
  debugStats: (await import('vue')).reactive({
    requests: [],
    dbRequests: [],
    calls: [],
    apiCalls: 0,
    apiTime: 0,
    dbQueries: 0,
    dbTime: 0,
    lastApiDuration: 0,
    lastDbQueries: 0,
    lastDbTime: 0
  }),
  refreshDebugRequests: vi.fn(),
  clearApiCalls: vi.fn(),
  clearDbQueries: vi.fn()
}))

vi.mock('vue-router', async () => {
  const route = (await import('vue')).reactive({ fullPath: '/' })
  return { useRoute: () => route }
})

vi.mock('../composables/usePageLoadPerformance', () => ({
  usePageLoadPerformance: () => ({ metrics: {} })
}))

beforeEach(async () => {
  localStorage.removeItem('agentic.debugExpanded')
  localStorage.removeItem('agentic.statusBarHeight')
  for (const key of ['agentic.debugTab', 'agentic.debugActiveTab', 'agentic.statusBarTab', 'agentic.activeTab']) {
    localStorage.removeItem(key)
  }
  debugStats.apiCalls = 0
  debugStats.apiTime = 0
  debugStats.dbQueries = 0
  debugStats.dbTime = 0
  debugStats.calls = []
  debugStats.requests = []
  debugStats.dbRequests = []
  useRoute().fullPath = '/'
  await nextTick()
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

it('refreshes the details only while they are expanded, coalescing bursts without polling', async () => {
  vi.useFakeTimers()
  const wrapper = mount(StatusBar)

  try {
    // Collapsed: neither navigation nor API calls touch the debug endpoint.
    useRoute().fullPath = '/tasks'
    await nextTick()
    debugStats.apiCalls += 1
    await nextTick()
    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)

    useRoute().fullPath = '/people'
    await nextTick()
    await vi.advanceTimersByTimeAsync(100)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)

    debugStats.apiCalls += 1
    await nextTick()
    await vi.advanceTimersByTimeAsync(50)
    debugStats.apiCalls += 1
    await nextTick()
    await vi.advanceTimersByTimeAsync(50)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(50)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(3)

    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(3)
  } finally {
    wrapper.unmount()
  }
})

it('summarizes calls locally while collapsed without asking the server', async () => {
  const wrapper = mount(StatusBar)
  try {
    debugStats.apiCalls = 3
    debugStats.apiTime = 42.5
    debugStats.dbQueries = 7
    debugStats.dbTime = 3.25
    debugStats.calls = [{ duration: 4, dbQueries: 1, dbTime: 0.5 }]
    await nextTick()

    expect(wrapper.get('[data-testid="api-calls"]').text()).toBe('API: 3 calls, 42.50 ms')
    expect(wrapper.get('[data-testid="db-queries"]').text()).toBe('DB: 7 queries, 3.25 ms')
    expect(wrapper.get('[data-testid="last-api-call"]').text()).toBe('Last: 4.00 ms (1 queries, 0.50 ms)')
    expect(refreshDebugRequests).not.toHaveBeenCalled()
  } finally {
    wrapper.unmount()
  }
})

it('keeps the page-load timings in the details panel, not the always-visible summary', async () => {
  const wrapper = mount(StatusBar)
  try {
    // Collapsed, the summary carries only the API and DB counts.
    const summary = wrapper.get('.status-bar-summary')
    expect(summary.find('[data-testid="page-load-time"]').exists()).toBe(false)
    expect(summary.find('[data-testid="dom-content-loaded"]').exists()).toBe(false)
    expect(summary.find('[data-testid="ttfb"]').exists()).toBe(false)
    expect(summary.find('[data-testid="first-paint"]').exists()).toBe(false)

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    const details = wrapper.get('[data-testid="status-bar-details"]')
    expect(details.find('[data-testid="page-load-time"]').exists()).toBe(true)
    expect(details.find('[data-testid="dom-content-loaded"]').exists()).toBe(true)
    expect(details.find('[data-testid="ttfb"]').exists()).toBe(true)
    expect(details.find('[data-testid="first-paint"]').exists()).toBe(true)
  } finally {
    wrapper.unmount()
  }
})

it('cancels a scheduled refresh when unmounted', async () => {
  vi.useFakeTimers()
  localStorage.setItem('agentic.debugExpanded', 'true')
  const wrapper = mount(StatusBar)
  debugStats.apiCalls += 1
  await nextTick()
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(100)
  expect(refreshDebugRequests).toHaveBeenCalledTimes(1)
})

it('offers a separate clear action for each tab', async () => {
  const wrapper = mount(StatusBar)
  try {
    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    await wrapper.get('[data-testid="clear-api-calls"]').trigger('click')
    expect(clearApiCalls).toHaveBeenCalledTimes(1)
    expect(clearDbQueries).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="tab-db-queries"]').trigger('click')
    await wrapper.get('[data-testid="clear-db-queries"]').trigger('click')
    expect(clearDbQueries).toHaveBeenCalledTimes(1)
    expect(clearApiCalls).toHaveBeenCalledTimes(1)
  } finally {
    wrapper.unmount()
  }
})

it('places the resize handle on the outer bar and preserves drag resizing', async () => {
  localStorage.removeItem('agentic.statusBarHeight')
  const wrapper = mount(StatusBar)
  try {
    expect(wrapper.find('[data-testid="status-bar-resizer"]').exists()).toBe(false)
    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    const handle = wrapper.get('[data-testid="status-bar-resizer"]')
    expect(handle.element.parentElement).toBe(wrapper.element)
    handle.element.dispatchEvent(Object.assign(new Event('pointerdown'), { clientY: 400 }))
    window.dispatchEvent(Object.assign(new Event('pointermove'), { clientY: 350 }))
    window.dispatchEvent(new Event('pointerup'))
    await nextTick()
    expect(wrapper.get('[data-testid="status-bar-details"]').element.style.height).toBe('290px')
    expect(localStorage.getItem('agentic.statusBarHeight')).toBe('290')
  } finally {
    wrapper.unmount()
    localStorage.removeItem('agentic.statusBarHeight')
  }
})

it('preserves the details height when API and DB entries are cleared', async () => {
  localStorage.setItem('agentic.statusBarHeight', '320')
  localStorage.removeItem('agentic.debugExpanded')
  debugStats.requests = [{ id: 'api', path: '/api/tasks', duration_ms: 1 }]
  debugStats.dbRequests = [{ id: 'db', path: '/api/tasks', queries: [{ sql: 'SELECT 1' }] }]
  clearApiCalls.mockImplementationOnce(() => {
    debugStats.requests = []
  })
  clearDbQueries.mockImplementationOnce(() => {
    debugStats.dbRequests = []
  })
  const wrapper = mount(StatusBar)
  try {
    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    const details = wrapper.get('[data-testid="status-bar-details"]')
    expect(details.element.style.height).toBe('320px')
    await wrapper.get('[data-testid="clear-api-calls"]').trigger('click')
    expect(details.element.style.height).toBe('320px')
    await wrapper.get('[data-testid="tab-db-queries"]').trigger('click')
    await wrapper.get('[data-testid="clear-db-queries"]').trigger('click')
    expect(details.element.style.height).toBe('320px')
  } finally {
    wrapper.unmount()
    localStorage.removeItem('agentic.statusBarHeight')
  }
})

it('reads the details when they open and not again until they reopen', async () => {
  vi.useFakeTimers()
  const wrapper = mount(StatusBar)

  try {
    expect(refreshDebugRequests).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)
  } finally {
    wrapper.unmount()
  }
})
