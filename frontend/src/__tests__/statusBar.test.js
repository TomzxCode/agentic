import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { mount } from '@vue/test-utils'
import StatusBar from '../components/StatusBar.vue'
import { debugStats, refreshDebugRequests, clearApiCalls, clearDbQueries } from '../debug.js'

vi.mock('../debug.js', async () => ({
  debugStats: (await import('vue')).reactive({ requests: [], dbRequests: [], apiCalls: 0 }),
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
  debugStats.apiCalls = 0
  debugStats.requests = []
  debugStats.dbRequests = []
  useRoute().fullPath = '/'
  await nextTick()
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

it('refreshes after navigation and API responses, coalescing bursts without polling', async () => {
  vi.useFakeTimers()
  const wrapper = mount(StatusBar)

  try {
    useRoute().fullPath = '/tasks'
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

it('cancels a scheduled refresh when unmounted', async () => {
  vi.useFakeTimers()
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

it('refreshes on mount and opening details without polling', async () => {
  vi.useFakeTimers()
  const wrapper = mount(StatusBar)

  try {
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(10000)
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)

    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(2)
    await wrapper.get('[data-testid="status-bar-toggle"]').trigger('click')
    expect(refreshDebugRequests).toHaveBeenCalledTimes(3)
  } finally {
    wrapper.unmount()
  }
})
