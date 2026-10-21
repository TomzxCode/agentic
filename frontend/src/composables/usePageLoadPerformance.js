import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'

// Read performance information related to the current page load.
// Returns a reactive object with the measured timings in milliseconds.
export function readPageLoadPerformance(perf = typeof performance !== 'undefined' ? performance : null) {
  const result = {
    loadTime: null,
    domContentLoaded: null,
    ttfb: null,
    firstPaint: null,
    duration: null
  }
  if (!perf) return result

  // Navigation Timing API (Level 2): PerformanceNavigationTiming.
  try {
    const entries = typeof perf.getEntriesByType === 'function' ? perf.getEntriesByType('navigation') : null
    const nav = Array.isArray(entries) && entries.length ? entries[0] : null
    if (nav) {
      const start = nav.startTime || 0
      result.loadTime = Math.round((nav.loadEventEnd || nav.duration || 0) - start)
      result.domContentLoaded = Math.round((nav.domContentLoadedEventEnd || 0) - start)
      result.ttfb = Math.round((nav.responseStart || 0) - (nav.requestStart || 0))
      result.duration = Math.round(nav.duration || 0)
      if (result.loadTime <= 0 && nav.duration) result.loadTime = Math.round(nav.duration)
    }
  } catch {
    // ignore
  }

  // Navigation Timing API (Level 1): performance.timing.
  if (result.loadTime === null) {
    try {
      const timing = perf.timing
      if (timing && typeof timing.navigationStart === 'number') {
        const start = timing.navigationStart || 0
        if (typeof timing.loadEventEnd === 'number' && timing.loadEventEnd > 0) {
          result.loadTime = Math.round(timing.loadEventEnd - start)
        }
        if (typeof timing.domContentLoadedEventEnd === 'number' && timing.domContentLoadedEventEnd > 0) {
          result.domContentLoaded = Math.round(timing.domContentLoadedEventEnd - start)
        }
        if (typeof timing.responseStart === 'number' && typeof timing.requestStart === 'number') {
          result.ttfb = Math.round(timing.responseStart - timing.requestStart)
        }
      }
    } catch {
      // ignore
    }
  }

  // Paint timing (first paint / first contentful paint).
  try {
    if (typeof perf.getEntriesByType === 'function') {
      const paints = perf.getEntriesByType('paint') || []
      const fp = paints.find((p) => p.name === 'first-paint' || p.name === 'first-contentful-paint')
      if (fp) result.firstPaint = Math.round(fp.startTime || 0)
    }
  } catch {
    // ignore
  }

  // Fallback: use performance.now() against a stored origin when nothing else is available.
  if (result.loadTime === null) {
    try {
      if (typeof perf.now === 'function') {
        result.loadTime = Math.round(perf.now())
      }
    } catch {
      // ignore
    }
  }

  if (result.loadTime === null) result.loadTime = 0
  if (result.domContentLoaded === null) result.domContentLoaded = result.loadTime
  if (result.ttfb === null) result.ttfb = 0

  return result
}

export function usePageLoadPerformance() {
  const metrics = ref(readPageLoadPerformance())
  const route = safeUseRoute()

  function update() {
    metrics.value = readPageLoadPerformance()
  }

  onMounted(() => {
    update()
    // Re-read after the window load event fires, in case timings were not ready.
    if (typeof window !== 'undefined') {
      if (document.readyState === 'complete') {
        // Defer slightly to let loadEventEnd populate.
        setTimeout(update, 0)
      } else {
        window.addEventListener('load', () => setTimeout(update, 0), { once: true })
      }
    }
  })

  if (route) {
    watch(
      () => route.fullPath,
      () => {
        setTimeout(update, 0)
      }
    )
  }

  onUnmounted(() => {})

  const loadTime = computed(() => (metrics.value ? metrics.value.loadTime : 0))
  return { metrics, loadTime, update, read: readPageLoadPerformance }
}

function safeUseRoute() {
  try {
    return useRoute()
  } catch {
    return null
  }
}

// Aliases for compatibility with different expected names.
export const usePagePerformance = usePageLoadPerformance
export const usePerformance = usePageLoadPerformance
export const usePageLoad = usePageLoadPerformance
export const useLoadPerformance = usePageLoadPerformance

export function getPageLoadPerformance(...args) {
  return readPageLoadPerformance(...args)
}
export const getPerformance = getPageLoadPerformance
export const measurePageLoad = getPageLoadPerformance
